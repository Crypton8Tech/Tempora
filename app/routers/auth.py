"""Auth routes: login, register, logout."""

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

import os

from app.database import get_db
from app.models import User, CartItem
from app.auth import hash_password, verify_password, create_session_token
from app.security import InMemoryRateLimiter, client_ip, normalize_currency, normalize_lang
from app.translations import t as _t, format_price as _fp, loc as _loc

router = APIRouter()
auth_limiter = InMemoryRateLimiter()
templates = Jinja2Templates(
    directory=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates")
)
templates.env.globals["t"] = _t
templates.env.globals["format_price"] = _fp
templates.env.globals["loc"] = _loc


def _base_ctx(request: Request) -> dict:
    lang = normalize_lang(request.cookies.get("lang"), default="en")
    currency = normalize_currency(request.cookies.get("currency"), default="eur")
    cart_count = sum(i.get("quantity", 1) for i in request.session.get("guest_cart", []))
    return {"request": request, "user": None, "cart_count": cart_count, "lang": lang, "currency": currency}


def _merge_guest_cart(request: Request, user: User, db: Session):
    """Merge session guest cart into user's DB cart after login/register."""
    guest_cart = request.session.get("guest_cart", [])
    if not guest_cart:
        return
    for entry in guest_cart:
        existing = db.query(CartItem).filter(
            CartItem.user_id == user.id, CartItem.product_id == entry["product_id"]
        ).first()
        if existing:
            existing.quantity += entry["quantity"]
        else:
            db.add(CartItem(user_id=user.id, product_id=entry["product_id"], quantity=entry["quantity"]))
    db.commit()
    request.session.pop("guest_cart", None)


@router.get("/login")
async def login_page(request: Request):
    ctx = _base_ctx(request)
    ctx["error"] = ""
    return templates.TemplateResponse("login.html", ctx)


@router.post("/login")
async def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    ctx = _base_ctx(request)
    lang = ctx["lang"]
    ip = client_ip(request)
    if not auth_limiter.allowed(f"auth-login:{ip}", limit=12, window_seconds=60):
        ctx["error"] = "Too many attempts. Please retry in a minute."
        return templates.TemplateResponse("login.html", ctx, status_code=429)

    user = db.query(User).filter(User.email == email.lower().strip()).first()
    if not user or not verify_password(password, user.password_hash):
        ctx["error"] = _t("err_wrong_credentials", lang)
        return templates.TemplateResponse("login.html", ctx)

    token = create_session_token(user.id)
    request.session["token"] = token
    _merge_guest_cart(request, user, db)
    return RedirectResponse("/account", status_code=302)


@router.get("/register")
async def register_page(request: Request):
    ctx = _base_ctx(request)
    ctx["error"] = ""
    return templates.TemplateResponse("register.html", ctx)


@router.post("/register")
async def register_submit(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    password2: str = Form(...),
    db: Session = Depends(get_db),
):
    ctx = _base_ctx(request)
    lang = ctx["lang"]
    email = email.lower().strip()

    if password != password2:
        ctx["error"] = _t("err_password_mismatch", lang)
        return templates.TemplateResponse("register.html", ctx)

    if len(password) < 6:
        ctx["error"] = _t("err_password_short", lang)
        return templates.TemplateResponse("register.html", ctx)

    existing = db.query(User).filter(User.email == email).first()
    if existing:
        ctx["error"] = _t("err_email_exists", lang)
        return templates.TemplateResponse("register.html", ctx)

    user = User(
        email=email,
        password_hash=hash_password(password),
        name=name.strip(),
        is_verified=True,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_session_token(user.id)
    request.session["token"] = token
    _merge_guest_cart(request, user, db)
    return RedirectResponse("/account", status_code=302)


@router.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/", status_code=302)
