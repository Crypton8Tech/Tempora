"""API routes for cart, orders, payment checkout, and AJAX endpoints."""

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
    date_of_birth: str = Form(""),
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

    # Payment checkout via active provider
    from app.payments import create_checkout
    metadata = {}
    if date_of_birth.strip():
        metadata["date_of_birth"] = date_of_birth.strip()
    redirect_url = create_checkout(db, order, cart_products, metadata)
    if redirect_url:
        return RedirectResponse(redirect_url, status_code=303)

    # No external payment URL — show local payment page with instructions
    return RedirectResponse(f"/payment/{order_number}", status_code=302)


# ── Payment Webhooks ──────────────────────────────────────────────────────────

@router.post("/stripe/webhook")
async def stripe_webhook(request: Request, db: Session = Depends(get_db)):
    from app.payments import handle_webhook
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    ok = handle_webhook("stripe", db, payload, sig_header)
    if not ok:
        return JSONResponse({"error": "failed"}, status_code=400)
    return JSONResponse({"ok": True})


@router.post("/yookassa/webhook")
async def yookassa_webhook(request: Request, db: Session = Depends(get_db)):
    from app.payments import handle_webhook
    payload = await request.body()
    ok = handle_webhook("yookassa", db, payload, "")
    if not ok:
        return JSONResponse({"error": "failed"}, status_code=400)
    return JSONResponse({"ok": True})


@router.post("/cloudpayments/webhook")
async def cloudpayments_webhook(request: Request, db: Session = Depends(get_db)):
    from app.payments import handle_webhook
    payload = await request.body()
    ok = handle_webhook("cloudpayments", db, payload, "")
    if not ok:
        return JSONResponse({"error": "failed"}, status_code=400)
    return JSONResponse({"ok": True})


@router.post("/paypal/webhook")
async def paypal_webhook(request: Request, db: Session = Depends(get_db)):
    from app.payments import handle_webhook
    payload = await request.body()
    ok = handle_webhook("paypal", db, payload, "")
    if not ok:
        return JSONResponse({"error": "failed"}, status_code=400)
    return JSONResponse({"ok": True})


@router.post("/csscapital/webhook")
async def csscapital_webhook(request: Request, db: Session = Depends(get_db)):
    from app.payments import handle_webhook
    payload = await request.body()
    sig_header = request.headers.get("x-signature", request.headers.get("x-webhook-signature", ""))
    ok = handle_webhook("csscapital", db, payload, sig_header)
    if not ok:
        return JSONResponse({"error": "failed"}, status_code=400)
    return JSONResponse({"ok": True})


@router.post("/custom-webhook/{provider_slug}")
async def custom_provider_webhook(provider_slug: str, request: Request, db: Session = Depends(get_db)):
    from app.payments import handle_webhook
    payload = await request.body()
    sig_header = request.headers.get("x-signature", request.headers.get("x-webhook-signature", ""))
    ok = handle_webhook(provider_slug, db, payload, sig_header)
    if not ok:
        return JSONResponse({"error": "failed"}, status_code=400)
    return JSONResponse({"ok": True})


# ── Payment status check (for auto-refresh on payment page) ──────────────────

@router.get("/payment-status/{order_number}")
async def payment_status(order_number: str, db: Session = Depends(get_db)):
    order = db.query(Order).filter(Order.order_number == order_number).first()
    if not order:
        return JSONResponse({"error": "not_found"}, status_code=404)
    from app.payments import sync_order_status
    sync_order_status(db, order)
    db.refresh(order)
    return JSONResponse({"status": order.status, "order_number": order.order_number})


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
