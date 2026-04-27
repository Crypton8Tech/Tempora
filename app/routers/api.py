"""API-маршруты корзины, заказов, платежей и AJAX-эндпоинтов."""

from fastapi import APIRouter, Request, Depends, Form, HTTPException, Query
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, Product, CartItem, Order, OrderItem, SiteSetting
from app.auth import decode_session_token
from app.config import settings
from app.payments import create_checkout, handle_webhook, sync_order_status
from app.security import InMemoryRateLimiter, client_ip, is_safe_category_slug

import uuid
import datetime
import logging
import re
import ipaddress
from types import SimpleNamespace

logger = logging.getLogger(__name__)

router = APIRouter()
# Защищаем quick-order от спама и массовых автоматических запросов.
quick_order_limiter = InMemoryRateLimiter()
checkout_limiter = InMemoryRateLimiter()

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$")
_POSTAL_RE = re.compile(r"^[A-Za-z0-9\-\s]{3,12}$")

_COUNTRY_NAMES: dict[str, str] = {
    "US": "United States",
    "CA": "Canada",
    "GB": "United Kingdom",
    "DE": "Germany",
    "FR": "France",
    "IT": "Italy",
    "ES": "Spain",
    "CH": "Switzerland",
    "PL": "Poland",
    "NL": "Netherlands",
    "BE": "Belgium",
    "AT": "Austria",
    "SE": "Sweden",
    "NO": "Norway",
    "DK": "Denmark",
    "CZ": "Czech Republic",
    "UA": "Ukraine",
    "TR": "Turkey",
    "AE": "United Arab Emirates",
}


# ── Internal helpers ──────────────────────────────────────────────────────────

def _get_user(request: Request, db: Session) -> User | None:
    # Получаем текущего пользователя из session-токена.
    token = request.session.get("token")
    if not token:
        return None
    uid = decode_session_token(token)
    if uid is None:
        return None
    return db.query(User).filter(User.id == uid).first()


def _get_currency(request: Request) -> str:
    # Валюта берётся из cookie, но ограничивается только поддерживаемыми значениями.
    cur = request.cookies.get("currency", "eur")
    from app.translations import SUPPORTED_CURRENCIES
    return cur if cur in SUPPORTED_CURRENCIES else "eur"


def _make_order_number(prefix: str = "TS") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"


def _build_checkout_products_from_order(order: Order) -> list[tuple]:
    """Reconstruct checkout items from saved order lines for payment retry."""
    cart_products: list[tuple] = []
    for item in order.items:
        product_like = SimpleNamespace(name=item.product_name, price=item.price)
        cart_products.append((product_like, item.quantity, None))
    return cart_products


def _start_checkout_with_retries(db: Session, order: Order, cart_products: list, attempts: int = 2) -> str | None:
    """Try to create provider checkout URL with limited retries for transient failures."""
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            redirect_url = create_checkout(db, order, cart_products)
            if redirect_url:
                return redirect_url
            logger.warning("Checkout URL is empty for order %s (attempt %s/%s)", order.order_number, attempt, attempts)
        except Exception as exc:
            last_error = exc
            logger.error("Checkout attempt %s/%s failed for order %s: %s", attempt, attempts, order.order_number, exc)
    if last_error:
        logger.error("Checkout permanently failed for order %s: %s", order.order_number, last_error)
    return None


def _clean_text(value: str | None, limit: int = 255) -> str:
    return " ".join((value or "").strip().split())[:limit]


def _normalize_phone(value: str | None) -> str:
    raw = (value or "").strip()
    normalized = "".join(ch for ch in raw if ch.isdigit() or ch in "+-() ")
    digits = "".join(ch for ch in normalized if ch.isdigit())
    if raw.startswith("+") and normalized and not normalized.startswith("+"):
        normalized = "+" + normalized
    if len(digits) < 7 or len(digits) > 15:
        raise HTTPException(status_code=422, detail="Invalid phone number format")
    return normalized[:32]


def _normalize_country(value: str | None) -> str:
    code = (value or "").strip().upper()
    if code not in _COUNTRY_NAMES:
        raise HTTPException(status_code=422, detail="Unsupported country")
    return code


def _validate_checkout_payload(
    full_name: str,
    email: str,
    phone: str,
    country: str,
    address_line1: str,
    address_line2: str,
    city: str,
    state_region: str,
    postal_code: str,
    delivery_notes: str,
    company_name: str,
    door_code: str,
) -> dict[str, str]:
    name = _clean_text(full_name, 120)
    email_clean = _clean_text(email, 180).lower()
    country_code = _normalize_country(country)
    line1 = _clean_text(address_line1, 180)
    line2 = _clean_text(address_line2, 180)
    city_clean = _clean_text(city, 120)
    state_clean = _clean_text(state_region, 120)
    postal = _clean_text(postal_code, 24).upper()
    notes = _clean_text(delivery_notes, 600)
    company = _clean_text(company_name, 160)
    door = _clean_text(door_code, 120)

    if len(name) < 3:
        raise HTTPException(status_code=422, detail="Full name is required")
    if not _EMAIL_RE.fullmatch(email_clean):
        raise HTTPException(status_code=422, detail="Invalid email format")
    phone_clean = _normalize_phone(phone)
    if not line1:
        raise HTTPException(status_code=422, detail="Address line 1 is required")
    if not city_clean:
        raise HTTPException(status_code=422, detail="City is required")
    if postal and not _POSTAL_RE.fullmatch(postal):
        raise HTTPException(status_code=422, detail="Invalid ZIP / postal code")
    if country_code in {"US", "CA"} and not state_clean:
        raise HTTPException(status_code=422, detail="State / region is required for this country")
    if country_code in {"US", "CA"} and not postal:
        raise HTTPException(status_code=422, detail="ZIP / postal code is required for this country")

    return {
        "full_name": name,
        "email": email_clean,
        "phone": phone_clean,
        "country": country_code,
        "address_line1": line1,
        "address_line2": line2,
        "city": city_clean,
        "state_region": state_clean,
        "postal_code": postal,
        "delivery_notes": notes,
        "company_name": company,
        "door_code": door,
    }


def _compose_shipping_address(data: dict[str, str]) -> str:
    parts: list[str] = [
        f"Country: {_COUNTRY_NAMES.get(data['country'], data['country'])}",
        f"Address line 1: {data['address_line1']}",
    ]
    if data["address_line2"]:
        parts.append(f"Address line 2: {data['address_line2']}")
    parts.append(f"City: {data['city']}")
    if data["state_region"]:
        parts.append(f"State/Region: {data['state_region']}")
    if data["postal_code"]:
        parts.append(f"ZIP/Postal: {data['postal_code']}")
    if data["company_name"]:
        parts.append(f"Company: {data['company_name']}")
    if data["door_code"]:
        parts.append(f"Door/Floor: {data['door_code']}")
    return "\n".join(parts)


def _infer_country_from_accept_language(request: Request) -> str | None:
    header = (request.headers.get("accept-language") or "").split(",")[0].strip().upper()
    if "-" in header:
        code = header.split("-")[-1]
        if code in _COUNTRY_NAMES:
            return code
    return None


def _is_public_ip(value: str) -> bool:
    try:
        ip = ipaddress.ip_address(value)
        return not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast)
    except ValueError:
        return False


# ── Guest cart helpers ────────────────────────────────────────────────────────

def _guest_cart_get(request: Request) -> list:
    return request.session.get("guest_cart", [])


def _guest_cart_set(request: Request, cart: list):
    request.session["guest_cart"] = cart


# ── Cart API ──────────────────────────────────────────────────────────────────

@router.post("/cart/add")
async def cart_add(
    request: Request,
    product_id: int = Form(...),
    quantity: int = Form(1),
    db: Session = Depends(get_db),
):
    # Добавляем товар в корзину БД для пользователя или в session-корзину для гостя.
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        return JSONResponse({"error": "product_not_found"}, status_code=404)

    user = _get_user(request, db)

    if user:
        existing = db.query(CartItem).filter(
            CartItem.user_id == user.id, CartItem.product_id == product_id
        ).first()
        if existing:
            existing.quantity += quantity
        else:
            db.add(CartItem(user_id=user.id, product_id=product_id, quantity=quantity))
        db.commit()
        cart_count = db.query(CartItem).filter(CartItem.user_id == user.id).count()
    else:
        cart = _guest_cart_get(request)
        found = False
        for item in cart:
            if item["product_id"] == product_id:
                item["quantity"] += quantity
                found = True
                break
        if not found:
            cart.append({"product_id": product_id, "quantity": quantity})
        _guest_cart_set(request, cart)
        cart_count = len(cart)

    return JSONResponse({"ok": True, "cart_count": cart_count})


@router.post("/cart/update")
async def cart_update(
    request: Request,
    item_id: int = Form(...),
    quantity: int = Form(...),
    db: Session = Depends(get_db),
):
    user = _get_user(request, db)

    if user:
        item = db.query(CartItem).filter(
            CartItem.id == item_id, CartItem.user_id == user.id
        ).first()
        if not item:
            return JSONResponse({"error": "not_found"}, status_code=404)
        if quantity <= 0:
            db.delete(item)
        else:
            item.quantity = quantity
        db.commit()
    else:
        cart = _guest_cart_get(request)
        if quantity <= 0:
            cart = [i for i in cart if i["product_id"] != item_id]
        else:
            for i in cart:
                if i["product_id"] == item_id:
                    i["quantity"] = quantity
        _guest_cart_set(request, cart)

    return JSONResponse({"ok": True})


@router.post("/cart/remove")
async def cart_remove(
    request: Request,
    item_id: int = Form(...),
    db: Session = Depends(get_db),
):
    user = _get_user(request, db)

    if user:
        item = db.query(CartItem).filter(
            CartItem.id == item_id, CartItem.user_id == user.id
        ).first()
        if item:
            db.delete(item)
            db.commit()
    else:
        cart = _guest_cart_get(request)
        cart = [i for i in cart if i["product_id"] != item_id]
        _guest_cart_set(request, cart)

    return JSONResponse({"ok": True})


# ── Cart checkout ─────────────────────────────────────────────────────────────

@router.post("/checkout")
async def checkout(
    request: Request,
    full_name:   str = Form(""),
    email:       str = Form(""),
    phone:       str = Form(""),
    country:     str = Form(""),
    address_line1: str = Form(""),
    address_line2: str = Form(""),
    city:        str = Form(""),
    state_region: str = Form(""),
    postal_code: str = Form(""),
    company_name: str = Form(""),
    door_code:   str = Form(""),
    delivery_notes: str = Form(""),

    # Legacy fields for backward compatibility.
    address:     str = Form(""),
    note:        str = Form(""),
    guest_name:  str = Form(""),
    guest_email: str = Form(""),
    db: Session = Depends(get_db),
):
    # Создаём заказ из текущей корзины и отправляем пользователя к платёжному провайдеру.
    ip = client_ip(request)
    if not checkout_limiter.allowed(f"checkout:{ip}", limit=30, window_seconds=60):
        raise HTTPException(status_code=429, detail="Too many checkout requests. Please retry later.")

    # Fallback for clients that still submit old field names.
    if not full_name and guest_name:
        full_name = guest_name
    if not email and guest_email:
        email = guest_email
    if not address_line1 and address:
        address_line1 = address
    if not delivery_notes and note:
        delivery_notes = note

    checkout_data = _validate_checkout_payload(
        full_name=full_name,
        email=email,
        phone=phone,
        country=country,
        address_line1=address_line1,
        address_line2=address_line2,
        city=city,
        state_region=state_region,
        postal_code=postal_code,
        delivery_notes=delivery_notes,
        company_name=company_name,
        door_code=door_code,
    )

    user = _get_user(request, db)
    currency = _get_currency(request)

    # Формируем список товаров из корзины
    cart_products: list[tuple[Product, int, CartItem | None]] = []
    if user:
        db_items = db.query(CartItem).filter(CartItem.user_id == user.id).all()
        for ci in db_items:
            if ci.product:
                cart_products.append((ci.product, ci.quantity, ci))
    else:
        guest_cart = _guest_cart_get(request)
        for entry in guest_cart:
            product = db.query(Product).filter(Product.id == entry["product_id"]).first()
            if product:
                cart_products.append((product, entry["quantity"], None))

    if not cart_products:
        return RedirectResponse("/cart", status_code=302)

    total = sum(p.price * q for p, q, _ in cart_products)
    order_number = _make_order_number("TS")

    order = Order(
        order_number=order_number,
        user_id=user.id if user else None,
        guest_name=checkout_data["full_name"],
        guest_email=checkout_data["email"],
        status="pending",
        total=total,
        currency=currency,
        address=_compose_shipping_address(checkout_data),
        phone=checkout_data["phone"],
        note=checkout_data["delivery_notes"],
    )
    db.add(order)
    db.flush()

    for product, qty, _ in cart_products:
        img_url = product.images[0].url if product.images else ""
        db.add(OrderItem(
            order_id=order.id,
            product_id=product.id,
            product_name=product.name,
            product_sku=product.sku,
            price=product.price,
            quantity=qty,
            image_url=img_url,
        ))

    # Очищаем корзину после создания заказа
    if user:
        for _, _, ci in cart_products:
            if ci:
                db.delete(ci)
    else:
        _guest_cart_set(request, [])

    db.commit()

    # Сначала пробуем сразу открыть страницу провайдера оплаты.
    redirect_url = _start_checkout_with_retries(db, order, cart_products, attempts=2)
    if redirect_url:
        return RedirectResponse(redirect_url, status_code=303)

    # Если провайдер временно не отдал URL, уводим на внутреннюю страницу с повтором.
    return RedirectResponse(f"/payment/{order_number}?payment_error=1", status_code=303)


# ── Быстрый заказ (напрямую со страницы товара, без корзины) ──────────────────

@router.post("/quick-order")
async def quick_order(
    request: Request,
    product_id:  int = Form(...),
    full_name:   str = Form(""),
    email:       str = Form(""),
    phone:       str = Form(""),
    country:     str = Form(""),
    address_line1: str = Form(""),
    address_line2: str = Form(""),
    city:        str = Form(""),
    state_region: str = Form(""),
    postal_code: str = Form(""),
    company_name: str = Form(""),
    door_code:   str = Form(""),
    delivery_notes: str = Form(""),

    # Legacy fields for backward compatibility.
    guest_name:  str = Form(""),
    guest_email: str = Form(""),
    address:     str = Form(""),
    note:        str = Form(""),
    quantity:    int = Form(1),
    db: Session = Depends(get_db),
):
    """
    Create an order for a single product without going through the cart.
    Accessible to both authenticated users and guests.
    """
    ip = client_ip(request)
    limiter_key = f"quick-order:{ip}"
    # Лимитер блокирует массовые фейковые заказы с одного источника.
    if not quick_order_limiter.allowed(limiter_key, limit=20, window_seconds=60):
        raise HTTPException(status_code=429, detail="Too many quick-order requests. Please retry later.")

    # Fallback for clients that still submit old field names.
    if not full_name and guest_name:
        full_name = guest_name
    if not email and guest_email:
        email = guest_email
    if not address_line1 and address:
        address_line1 = address
    if not delivery_notes and note:
        delivery_notes = note

    checkout_data = _validate_checkout_payload(
        full_name=full_name,
        email=email,
        phone=phone,
        country=country,
        address_line1=address_line1,
        address_line2=address_line2,
        city=city,
        state_region=state_region,
        postal_code=postal_code,
        delivery_notes=delivery_notes,
        company_name=company_name,
        door_code=door_code,
    )

    product = db.query(Product).filter(Product.id == product_id, Product.is_active == True).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    if quantity < 1:
        quantity = 1

    user = _get_user(request, db)
    currency = _get_currency(request)
    total = product.price * quantity
    order_number = _make_order_number("QO")

    order = Order(
        order_number=order_number,
        user_id=user.id if user else None,
        guest_name=checkout_data["full_name"],
        guest_email=checkout_data["email"],
        status="pending",
        total=total,
        currency=currency,
        address=_compose_shipping_address(checkout_data),
        phone=checkout_data["phone"],
        note=checkout_data["delivery_notes"],
        created_at=datetime.datetime.utcnow(),
    )
    db.add(order)
    db.flush()

    img_url = product.images[0].url if product.images else ""
    db.add(OrderItem(
        order_id=order.id,
        product_id=product.id,
        product_name=product.name,
        product_sku=product.sku,
        price=product.price,
        quantity=quantity,
        image_url=img_url,
    ))
    db.commit()

    # Сначала пробуем сразу открыть страницу провайдера оплаты.
    redirect_url = _start_checkout_with_retries(db, order, [(product, quantity, None)], attempts=2)
    if redirect_url:
        return RedirectResponse(redirect_url, status_code=303)

    # Если провайдер временно не отдал URL, уводим на внутреннюю страницу с повтором.
    return RedirectResponse(f"/payment/{order_number}?payment_error=1", status_code=303)


# ── Payment webhooks & status ────────────────────────────────────────────────

@router.post("/{provider}/webhook")
async def provider_webhook(provider: str, request: Request, db: Session = Depends(get_db)):
    # Webhook — это server-to-server callback от платёжного провайдера.
    payload = await request.body()
    sig_header = (
        request.headers.get("stripe-signature", "")
        or request.headers.get("x-signature", "")
        or request.headers.get("signature", "")
    )
    ok = handle_webhook(provider, db, payload, sig_header)
    if ok:
        return JSONResponse({"ok": True})
    return JSONResponse({"ok": False}, status_code=400)


@router.post("/custom-webhook/{provider_slug}")
async def custom_provider_webhook(provider_slug: str, request: Request, db: Session = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get("x-signature", "") or request.headers.get("signature", "")
    ok = handle_webhook(provider_slug, db, payload, sig_header)
    if ok:
        return JSONResponse({"ok": True})
    return JSONResponse({"ok": False}, status_code=400)


@router.get("/payment-status/{order_number}")
async def payment_status(order_number: str, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.order_number == order_number).first()
    if not order:
        return JSONResponse({"error": "order_not_found"}, status_code=404)
    try:
        sync_order_status(db, order)
        db.refresh(order)
    except Exception as e:
        logger.error(f"Payment status sync error ({order_number}): {e}")
    return {
        "order_number": order.order_number,
        "status": order.status,
        "total": order.total,
        "currency": order.currency,
    }


@router.post("/payment/retry/{order_number}")
async def payment_retry(order_number: str, db: Session = Depends(get_db)):
    """Retry checkout session creation for an existing pending order."""
    order = db.query(Order).filter(Order.order_number == order_number).first()
    if not order:
        return RedirectResponse("/", status_code=303)

    if order.status == "paid":
        return RedirectResponse(f"/order-success/{order.order_number}", status_code=303)

    cart_products = _build_checkout_products_from_order(order)
    if not cart_products:
        return RedirectResponse(f"/payment/{order.order_number}?payment_error=1", status_code=303)

    redirect_url = _start_checkout_with_retries(db, order, cart_products, attempts=2)
    if redirect_url:
        return RedirectResponse(redirect_url, status_code=303)

    return RedirectResponse(f"/payment/{order.order_number}?payment_error=1", status_code=303)


@router.get("/geo-country")
async def geo_country(request: Request):
    """Best-effort country auto-detection by client IP with safe fallbacks."""
    ip = client_ip(request)
    if _is_public_ip(ip):
        try:
            import httpx

            resp = httpx.get(f"https://ipapi.co/{ip}/json/", timeout=3)
            if resp.status_code == 200:
                data = resp.json()
                code = str(data.get("country_code", "")).upper()
                if code in _COUNTRY_NAMES:
                    return {"country": code, "source": "ip"}
        except Exception:
            pass

    fallback = _infer_country_from_accept_language(request)
    if fallback:
        return {"country": fallback, "source": "accept-language"}
    return {"country": "", "source": "none"}


@router.get("/address/autocomplete")
async def address_autocomplete(
    request: Request,
    q: str = Query("", min_length=1, max_length=200),
    city: str = Query("", min_length=0, max_length=120),
    country: str = Query("", min_length=0, max_length=2),
):
    """Address autocomplete via OSM Nominatim with city/state/postal extraction."""
    query = (q or "").strip()
    if len(query) < 2:
        return {"items": []}

    city_value = _clean_text(city, 120)
    if city_value:
        query = f"{query}, {city_value}"

    params = {
        "q": query,
        "format": "jsonv2",
        "addressdetails": 1,
        "limit": 6,
    }
    country_code = (country or "").strip().lower()
    if len(country_code) == 2 and country_code.upper() in _COUNTRY_NAMES:
        params["countrycodes"] = country_code

    try:
        import httpx

        headers = {
            "User-Agent": "TemporaShop/1.0 (checkout autocomplete)",
            "Accept-Language": request.headers.get("accept-language", "en"),
        }
        resp = httpx.get("https://nominatim.openstreetmap.org/search", params=params, headers=headers, timeout=6)
        resp.raise_for_status()
        data = resp.json()
    except Exception:
        return {"items": []}

    items = []
    for row in data:
        addr = row.get("address", {}) or {}
        road = addr.get("road") or addr.get("pedestrian") or addr.get("footway") or addr.get("street") or ""
        house = addr.get("house_number") or ""
        line1 = " ".join(p for p in [road, house] if p).strip() or (row.get("name") or "")
        city = addr.get("city") or addr.get("town") or addr.get("village") or addr.get("hamlet") or ""
        state = addr.get("state") or addr.get("region") or ""
        postal = addr.get("postcode") or ""
        ccode = str(addr.get("country_code") or "").upper()

        items.append({
            "display_name": row.get("display_name", ""),
            "address_line1": line1,
            "city": city,
            "state_region": state,
            "postal_code": postal,
            "country": ccode if ccode in _COUNTRY_NAMES else "",
            "lat": row.get("lat", ""),
            "lon": row.get("lon", ""),
        })

    return {"items": items}


# ── JSON API for products (AJAX) ──────────────────────────────────────────────

@router.get("/products")
async def api_products(
    category: str | None = None,
    brand: str | None = None,
    db: Session = Depends(get_db),
):
    from app.models import Category
    # Публичный AJAX-эндпоинт с той же защитной валидацией категории, что и в каталоге.
    query = db.query(Product).filter(Product.is_active == True)
    if category:
        if is_safe_category_slug(category):
            cat = db.query(Category).filter(Category.slug == category).first()
            if cat:
                query = query.filter(Product.category_id == cat.id)
            else:
                query = query.filter(Product.id == -1)
        else:
            query = query.filter(Product.id == -1)
    if brand:
        query = query.filter(Product.brand.ilike(f"%{brand}%"))
    products = query.order_by(Product.created_at.desc()).all()
    return [
        {
            "id": p.id,
            "sku": p.sku,
            "name": p.name,
            "brand": p.brand,
            "price": p.price,
            "image": p.images[0].url if p.images else "",
        }
        for p in products
    ]
