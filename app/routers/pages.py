"""Public page routes."""

from fastapi import APIRouter, Request, Depends
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Product, Category, User
from app.auth import decode_session_token
from app.config import settings
from app.translations import t as _t, format_price as _fp, loc as _loc

import os

router = APIRouter()
templates = Jinja2Templates(
    directory=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates")
)
templates.env.globals["t"] = _t
templates.env.globals["format_price"] = _fp
templates.env.globals["loc"] = _loc


def get_current_user(request: Request, db: Session) -> User | None:
    token = request.session.get("token")
    if not token:
        return None
    uid = decode_session_token(token)
    if uid is None:
        return None
    return db.query(User).filter(User.id == uid).first()


def _get_lang(request: Request) -> str:
    return request.cookies.get("lang", "ru")


def _get_currency(request: Request) -> str:
    return request.cookies.get("currency", "rub")


def _guest_cart(request: Request) -> list:
    return request.session.get("guest_cart", [])


def _guest_cart_count(request: Request) -> int:
    return sum(i.get("quantity", 1) for i in _guest_cart(request))


def _base_ctx(request: Request, db: Session) -> dict:
    user = get_current_user(request, db)
    lang = _get_lang(request)
    currency = _get_currency(request)
    cart_count = 0
    if user:
        from app.models import CartItem
        cart_count = db.query(CartItem).filter(CartItem.user_id == user.id).count()
    else:
        cart_count = _guest_cart_count(request)
    return {
        "request": request,
        "user": user,
        "cart_count": cart_count,
        "bot_username": settings.BOT_USERNAME,
        "lang": lang,
        "currency": currency,
    }


@router.get("/")
async def home(request: Request, db: Session = Depends(get_db)):
    ctx = _base_ctx(request, db)
    featured = db.query(Product).filter(Product.is_active == True).order_by(Product.created_at.desc()).limit(6).all()
    categories = db.query(Category).all()
    ctx.update({"featured": featured, "categories": categories})
    return templates.TemplateResponse("home.html", ctx)


@router.get("/catalog")
async def catalog(
    request: Request,
    db: Session = Depends(get_db),
    category: str | None = None,
    brand: str | None = None,
    min_price: str | None = None,
    max_price: str | None = None,
    q: str | None = None,
):
    ctx = _base_ctx(request, db)
    query = db.query(Product).filter(Product.is_active == True)
    categories = db.query(Category).all()

    # Parse price filters (empty string -> None)
    min_price_val = None
    max_price_val = None
    try:
        if min_price and min_price.strip():
            min_price_val = float(min_price)
    except (ValueError, TypeError):
        pass
    try:
        if max_price and max_price.strip():
            max_price_val = float(max_price)
    except (ValueError, TypeError):
        pass

    if category:
        cat = db.query(Category).filter(Category.slug == category).first()
        if cat:
            query = query.filter(Product.category_id == cat.id)

    if brand:
        query = query.filter(Product.brand.ilike(f"%{brand}%"))

    if min_price_val is not None:
        query = query.filter(Product.price >= min_price_val)
    if max_price_val is not None:
        query = query.filter(Product.price <= max_price_val)

    if q:
        query = query.filter(
            (Product.name.ilike(f"%{q}%")) | (Product.brand.ilike(f"%{q}%")) | (Product.model.ilike(f"%{q}%"))
        )

    products = query.order_by(Product.created_at.desc()).all()

    # Collect unique brands for filter
    all_brands = (
        db.query(Product.brand)
        .filter(Product.is_active == True)
        .distinct()
        .all()
    )
    brands_list = sorted(set(b[0] for b in all_brands if b[0]))

    ctx.update({
        "products": products,
        "categories": categories,
        "brands": brands_list,
        "selected_category": category or "",
        "selected_brand": brand or "",
        "min_price": min_price or "",
        "max_price": max_price or "",
        "q": q or "",
    })
    return templates.TemplateResponse("catalog.html", ctx)


@router.get("/product/{sku}")
async def product_detail(sku: str, request: Request, db: Session = Depends(get_db)):
    ctx = _base_ctx(request, db)
    product = db.query(Product).filter(Product.sku == sku, Product.is_active == True).first()
    if not product:
        from fastapi.responses import RedirectResponse
        return RedirectResponse("/catalog", status_code=302)
    # Related products
    related = (
        db.query(Product)
        .filter(Product.category_id == product.category_id, Product.id != product.id, Product.is_active == True)
        .limit(4)
        .all()
    )
    ctx.update({"product": product, "related": related})
    return templates.TemplateResponse("product_detail.html", ctx)


@router.get("/cart")
async def cart_page(request: Request, db: Session = Depends(get_db)):
    ctx = _base_ctx(request, db)
    items = []
    total = 0.0

    if ctx["user"]:
        from app.models import CartItem
        db_items = db.query(CartItem).filter(CartItem.user_id == ctx["user"].id).all()
        for ci in db_items:
            if ci.product:
                items.append({
                    "id": ci.id,
                    "product": ci.product,
                    "quantity": ci.quantity,
                })
                total += ci.product.price * ci.quantity
    else:
        guest_cart = _guest_cart(request)
        for entry in guest_cart:
            product = db.query(Product).filter(Product.id == entry["product_id"]).first()
            if product:
                items.append({
                    "id": entry["product_id"],
                    "product": product,
                    "quantity": entry["quantity"],
                })
                total += product.price * entry["quantity"]

    # Get active payment provider info for frontend
    from app.models import SiteSetting
    from app.payments import get_active_provider, get_provider_display_name
    active_provider = get_active_provider(db)
    provider_name = get_provider_display_name(db, active_provider)

    stripe_pk = ""
    if active_provider == "stripe":
        s = db.query(SiteSetting).filter(SiteSetting.key == "stripe_public_key").first()
        if s and s.value:
            stripe_pk = s.value
        elif settings.STRIPE_PUBLIC_KEY:
            stripe_pk = settings.STRIPE_PUBLIC_KEY

    ctx.update({
        "items": items,
        "total": total,
        "stripe_pk": stripe_pk,
        "is_guest": ctx["user"] is None,
        "active_provider": active_provider,
        "provider_name": provider_name,
    })
    return templates.TemplateResponse("cart.html", ctx)


@router.get("/account")
async def account_page(request: Request, db: Session = Depends(get_db)):
    ctx = _base_ctx(request, db)
    if not ctx["user"]:
        from fastapi.responses import RedirectResponse
        return RedirectResponse("/auth/login", status_code=302)
    from app.models import Order
    orders = db.query(Order).filter(Order.user_id == ctx["user"].id).order_by(Order.created_at.desc()).all()
    ctx.update({"orders": orders})
    return templates.TemplateResponse("account.html", ctx)


@router.get("/help")
async def help_page(request: Request, db: Session = Depends(get_db)):
    ctx = _base_ctx(request, db)
    return templates.TemplateResponse("help.html", ctx)


@router.get("/track")
async def track_page(request: Request, db: Session = Depends(get_db)):
    ctx = _base_ctx(request, db)
    return templates.TemplateResponse("track.html", ctx)


@router.get("/track/result")
async def track_result(request: Request, order_number: str = "", db: Session = Depends(get_db)):
    ctx = _base_ctx(request, db)
    from app.models import Order
    order = db.query(Order).filter(Order.order_number == order_number).first()
    ctx.update({"order": order, "order_number": order_number})
    return templates.TemplateResponse("track_result.html", ctx)


@router.get("/order-success/{order_number}")
async def order_success(order_number: str, request: Request, db: Session = Depends(get_db)):
    ctx = _base_ctx(request, db)
    from app.models import Order
    order = db.query(Order).filter(Order.order_number == order_number).first()
    if order and order.status != "paid":
        from app.payments import sync_order_status
        sync_order_status(db, order)
        db.refresh(order)
    ctx.update({"order": order})
    return templates.TemplateResponse("order_success.html", ctx)


@router.get("/payment/{order_number}")
async def payment_page(order_number: str, request: Request, db: Session = Depends(get_db)):
    ctx = _base_ctx(request, db)
    from app.models import Order
    from app.payments import get_active_provider, get_payment_instructions, get_provider_display_name, sync_order_status

    order = db.query(Order).filter(Order.order_number == order_number).first()
    if order and order.status != "paid":
        sync_order_status(db, order)
        db.refresh(order)

    provider = get_active_provider(db)
    ctx.update({
        "order": order,
        "payment_instructions": get_payment_instructions(db, provider),
        "provider_name": get_provider_display_name(db, provider),
    })
    return templates.TemplateResponse("payment.html", ctx)
