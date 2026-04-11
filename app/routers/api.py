"""API routes for cart, orders, Stripe checkout, and AJAX endpoints."""

from fastapi import APIRouter, Request, Depends, Form, Header
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, Product, CartItem, Order, OrderItem, SiteSetting
from app.auth import decode_session_token
from app.config import settings

import uuid
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_user(request: Request, db: Session) -> User | None:
    token = request.session.get("token")
    if not token:
        return None
    uid = decode_session_token(token)
    if uid is None:
        return None
    return db.query(User).filter(User.id == uid).first()


def _get_stripe_keys(db: Session) -> tuple[str, str, str]:
    """Return (public_key, secret_key, webhook_secret) from DB settings or env."""
    keys = {}
    for row in db.query(SiteSetting).filter(
        SiteSetting.key.in_(["stripe_public_key", "stripe_secret_key", "stripe_webhook_secret"])
    ).all():
        keys[row.key] = row.value or ""
    pk = keys.get("stripe_public_key") or settings.STRIPE_PUBLIC_KEY
    sk = keys.get("stripe_secret_key") or settings.STRIPE_SECRET_KEY
    wh = keys.get("stripe_webhook_secret") or settings.STRIPE_WEBHOOK_SECRET
    return pk, sk, wh


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
        item = db.query(CartItem).filter(CartItem.id == item_id, CartItem.user_id == user.id).first()
        if not item:
            return JSONResponse({"error": "not_found"}, status_code=404)
        if quantity <= 0:
            db.delete(item)
        else:
            item.quantity = quantity
        db.commit()
    else:
        cart = _guest_cart_get(request)
        cart = [i for i in cart if not (i["product_id"] == item_id and quantity <= 0)]
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
        item = db.query(CartItem).filter(CartItem.id == item_id, CartItem.user_id == user.id).first()
        if item:
            db.delete(item)
            db.commit()
    else:
        cart = _guest_cart_get(request)
        cart = [i for i in cart if i["product_id"] != item_id]
        _guest_cart_set(request, cart)

    return JSONResponse({"ok": True})


# ── Checkout / Orders ─────────────────────────────────────────────────────────

@router.post("/checkout")
async def checkout(
    request: Request,
    address: str = Form(""),
    phone: str = Form(""),
    note: str = Form(""),
    guest_name: str = Form(""),
    guest_email: str = Form(""),
    db: Session = Depends(get_db),
):
    user = _get_user(request, db)

    # Build items list
    cart_products = []
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
    order_number = f"TS-{uuid.uuid4().hex[:8].upper()}"

    order = Order(
        order_number=order_number,
        user_id=user.id if user else None,
        guest_name=guest_name.strip() if not user else None,
        guest_email=guest_email.strip().lower() if not user else None,
        status="pending",
        total=total,
        currency="rub",
        address=address,
        phone=phone,
        note=note,
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

    # Clear cart
    if user:
        for _, _, ci in cart_products:
            if ci:
                db.delete(ci)
    else:
        _guest_cart_set(request, [])

    db.commit()

    # Try Stripe checkout
    _, stripe_sk, _ = _get_stripe_keys(db)
    if stripe_sk:
        try:
            import stripe
            stripe.api_key = stripe_sk

            line_items = []
            for product, qty, _ in cart_products:
                line_items.append({
                    "price_data": {
                        "currency": "rub",
                        "product_data": {"name": product.name},
                        "unit_amount": int(product.price * 100),
                    },
                    "quantity": qty,
                })

            site_url = settings.SITE_URL.rstrip("/")
            session = stripe.checkout.Session.create(
                payment_method_types=["card"],
                line_items=line_items,
                mode="payment",
                success_url=f"{site_url}/order-success/{order_number}?paid=1",
                cancel_url=f"{site_url}/cart",
                metadata={"order_number": order_number},
            )
            order.stripe_session_id = session.id
            db.commit()
            return RedirectResponse(session.url, status_code=303)
        except Exception as e:
            logger.error(f"Stripe error: {e}")
            # Fall through to regular success page

    return RedirectResponse(f"/order-success/{order_number}", status_code=302)


# ── Stripe Webhook ────────────────────────────────────────────────────────────

@router.post("/stripe/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    import stripe

    _, stripe_sk, webhook_secret = _get_stripe_keys(db)
    if not stripe_sk:
        return JSONResponse({"error": "stripe not configured"}, status_code=400)

    stripe.api_key = stripe_sk
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        if webhook_secret:
            event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
        else:
            import json
            event = json.loads(payload)
    except Exception as e:
        logger.error(f"Stripe webhook error: {e}")
        return JSONResponse({"error": "invalid payload"}, status_code=400)

    if event.get("type") == "checkout.session.completed":
        session_data = event["data"]["object"]
        order_number = session_data.get("metadata", {}).get("order_number")
        if order_number:
            order = db.query(Order).filter(Order.order_number == order_number).first()
            if order:
                order.status = "paid"
                order.stripe_payment_intent = session_data.get("payment_intent", "")
                db.commit()

    return JSONResponse({"ok": True})


# ── JSON API for products (for AJAX) ─────────────────────────────────────────

@router.get("/products")
async def api_products(
    category: str | None = None,
    brand: str | None = None,
    db: Session = Depends(get_db),
):
    from app.models import Category
    query = db.query(Product).filter(Product.is_active == True)
    if category:
        cat = db.query(Category).filter(Category.slug == category).first()
        if cat:
            query = query.filter(Product.category_id == cat.id)
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
