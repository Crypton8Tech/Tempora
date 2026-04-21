"""Admin panel routes."""

import os
import uuid
import json
import time
import logging
import urllib.request
import urllib.parse

from fastapi import APIRouter, Request, Depends, Form, UploadFile, File
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Product, ProductImage, Category, Order, SiteSetting
from app.translations import t as _t, format_price as _fp, loc as _loc

logger = logging.getLogger(__name__)
router = APIRouter()

templates = Jinja2Templates(
    directory=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates")
)
templates.env.globals["t"] = _t
templates.env.globals["format_price"] = _fp
templates.env.globals["loc"] = _loc

LANGS = ["en", "de", "fr", "it", "es"]

LANG_MAP = {
    "en": "en-US",
    "de": "de-DE",
    "fr": "fr-FR",
    "it": "it-IT",
    "es": "es-ES",
}


# ── Free translation via MyMemory ─────────────────────────────────────────────

def _translate_text(text: str, lang: str) -> str:
    """Translate a single text from RU to target lang using MyMemory (free, no key)."""
    if not text or not text.strip():
        return text
    try:
        params = urllib.parse.urlencode({
            "q": text[:450],
            "langpair": f"ru|{LANG_MAP[lang]}",
        })
        url = f"https://api.mymemory.translated.net/get?{params}"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        result = data.get("responseData", {}).get("translatedText", "")
        # MyMemory returns error string when quota exceeded
        if result and "MYMEMORY WARNING" not in result:
            return result
        return text
    except Exception as e:
        logger.error(f"MyMemory error [{lang}]: {e}")
        return text


def _auto_translate(product: Product) -> None:
    """
    Fill empty name_XX / description_XX fields using MyMemory free API.
    Only translates fields that are currently empty — never overwrites existing.
    """
    needs = [l for l in LANGS if not getattr(product, f"name_{l}", None)]
    if not needs:
        return

    logger.info(f"Auto-translating product {product.sku} → {needs}")

    for lang in needs:
        try:
            name_t = _translate_text(product.name, lang)
            desc_t = _translate_text(product.description or "", lang)
            setattr(product, f"name_{lang}",        name_t)
            setattr(product, f"description_{lang}", desc_t)
            logger.info(f"  ✓ {lang}: {name_t}")
            time.sleep(0.6)  # respect rate limit
        except Exception as e:
            logger.error(f"  ✗ {lang}: {e}")
            # Fallback — copy original so field is never null
            setattr(product, f"name_{lang}",        product.name)
            setattr(product, f"description_{lang}", product.description or "")


# ── Auth helpers ──────────────────────────────────────────────────────────────

def _is_admin(request: Request) -> bool:
    return request.session.get("is_admin") is True


def _admin_ctx(request: Request) -> dict:
    return {"request": request, "is_admin": True}


# ── Login ─────────────────────────────────────────────────────────────────────

@router.get("/login")
async def admin_login_page(request: Request):
    return templates.TemplateResponse("admin/login.html", {"request": request, "error": ""})


@router.post("/login")
async def admin_login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    if username == settings.ADMIN_USERNAME and password == settings.ADMIN_PASSWORD:
        request.session["is_admin"] = True
        return RedirectResponse("/admin", status_code=302)
    return templates.TemplateResponse("admin/login.html", {"request": request, "error": "Неверные данные"})


@router.get("/logout")
async def admin_logout(request: Request):
    request.session.pop("is_admin", None)
    return RedirectResponse("/admin/login", status_code=302)


# ── Dashboard ─────────────────────────────────────────────────────────────────

@router.get("")
async def admin_dashboard(request: Request, db: Session = Depends(get_db)):
    if not _is_admin(request):
        return RedirectResponse("/admin/login", status_code=302)
    ctx = _admin_ctx(request)
    orders = db.query(Order).order_by(Order.created_at.desc()).all()
    ctx.update({
        "orders":         orders,
        "products_count": db.query(Product).count(),
        "orders_count":   len(orders),
        "total_revenue":  sum(o.total for o in orders),
    })
    return templates.TemplateResponse("admin/dashboard.html", ctx)


# ── Products ──────────────────────────────────────────────────────────────────

@router.get("/products")
async def admin_products(request: Request, db: Session = Depends(get_db)):
    if not _is_admin(request):
        return RedirectResponse("/admin/login", status_code=302)
    ctx = _admin_ctx(request)
    ctx["products"] = db.query(Product).order_by(Product.created_at.desc()).all()
    return templates.TemplateResponse("admin/products.html", ctx)


@router.get("/products/add")
async def admin_add_product_page(request: Request, db: Session = Depends(get_db)):
    if not _is_admin(request):
        return RedirectResponse("/admin/login", status_code=302)
    ctx = _admin_ctx(request)
    ctx["categories"] = db.query(Category).all()
    ctx["error"] = ""
    return templates.TemplateResponse("admin/add_product.html", ctx)


@router.post("/products/add")
async def admin_add_product_submit(
    request: Request,
    name: str = Form(...),
    sku: str = Form(...),
    brand: str = Form(""),
    model: str = Form(""),
    description: str = Form(""),
    price: float = Form(...),
    category_id: int = Form(...),
    db: Session = Depends(get_db),
):
    if not _is_admin(request):
        return RedirectResponse("/admin/login", status_code=302)

    if db.query(Product).filter(Product.sku == sku).first():
        ctx = _admin_ctx(request)
        ctx["categories"] = db.query(Category).all()
        ctx["error"] = "SKU уже существует"
        return templates.TemplateResponse("admin/add_product.html", ctx)

    product = Product(
        sku=sku.strip(),
        brand=brand.strip(),
        model=model.strip(),
        name=name.strip(),
        description=description.strip(),
        price=price,
        category_id=category_id,
    )
    db.add(product)
    db.flush()

    # Auto-translate into all 5 languages
    _auto_translate(product)

    # Handle image uploads
    form = await request.form()
    files = form.getlist("images")
    sort_order = 0
    for file in files:
        if hasattr(file, "filename") and file.filename:
            ext = os.path.splitext(file.filename)[1]
            filename = f"{uuid.uuid4().hex}{ext}"
            filepath = os.path.join(settings.UPLOAD_DIR, filename)
            os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
            content = await file.read()
            with open(filepath, "wb") as f:
                f.write(content)
            db.add(ProductImage(
                product_id=product.id,
                url=f"/static/uploads/{filename}",
                sort_order=sort_order,
            ))
            sort_order += 1

    db.commit()
    return RedirectResponse("/admin/products", status_code=302)


@router.get("/products/edit/{product_id}")
async def admin_edit_product_page(product_id: int, request: Request, db: Session = Depends(get_db)):
    if not _is_admin(request):
        return RedirectResponse("/admin/login", status_code=302)
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        return RedirectResponse("/admin/products", status_code=302)
    ctx = _admin_ctx(request)
    ctx["product"] = product
    ctx["categories"] = db.query(Category).all()
    ctx["error"] = ""
    return templates.TemplateResponse("admin/edit_product.html", ctx)


@router.post("/products/edit/{product_id}")
async def admin_edit_product_submit(
    product_id: int,
    request: Request,
    name: str = Form(...),
    sku: str = Form(...),
    brand: str = Form(""),
    model: str = Form(""),
    description: str = Form(""),
    price: float = Form(...),
    category_id: int = Form(...),
    is_active: bool = Form(True),
    retranslate: bool = Form(False),
    db: Session = Depends(get_db),
):
    if not _is_admin(request):
        return RedirectResponse("/admin/login", status_code=302)

    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        return RedirectResponse("/admin/products", status_code=302)

    name_changed = product.name != name.strip()
    desc_changed = product.description != description.strip()

    product.name        = name.strip()
    product.sku         = sku.strip()
    product.brand       = brand.strip()
    product.model       = model.strip()
    product.description = description.strip()
    product.price       = price
    product.category_id = category_id
    product.is_active   = is_active

    # Clear translations if content changed or retranslate requested
    if retranslate or name_changed or desc_changed:
        for lang in LANGS:
            setattr(product, f"name_{lang}",        None)
            setattr(product, f"description_{lang}", None)

    _auto_translate(product)

    # Handle new image uploads
    form = await request.form()
    files = form.getlist("images")
    max_sort = max((img.sort_order for img in product.images), default=-1) + 1
    for file in files:
        if hasattr(file, "filename") and file.filename:
            ext = os.path.splitext(file.filename)[1]
            filename = f"{uuid.uuid4().hex}{ext}"
            filepath = os.path.join(settings.UPLOAD_DIR, filename)
            os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
            content = await file.read()
            with open(filepath, "wb") as f:
                f.write(content)
            db.add(ProductImage(
                product_id=product.id,
                url=f"/static/uploads/{filename}",
                sort_order=max_sort,
            ))
            max_sort += 1

    db.commit()
    return RedirectResponse("/admin/products", status_code=302)


@router.post("/products/delete/{product_id}")
async def admin_delete_product(product_id: int, request: Request, db: Session = Depends(get_db)):
    if not _is_admin(request):
        return RedirectResponse("/admin/login", status_code=302)
    product = db.query(Product).filter(Product.id == product_id).first()
    if product:
        for img in product.images:
            if img.url.startswith("/static/uploads/"):
                fpath = os.path.join(
                    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    img.url.lstrip("/")
                )
                if os.path.exists(fpath):
                    os.remove(fpath)
        db.delete(product)
        db.commit()
    return RedirectResponse("/admin/products", status_code=302)


@router.post("/products/delete-image/{image_id}")
async def admin_delete_image(image_id: int, request: Request, db: Session = Depends(get_db)):
    if not _is_admin(request):
        return RedirectResponse("/admin/login", status_code=302)
    img = db.query(ProductImage).filter(ProductImage.id == image_id).first()
    product_id = img.product_id if img else None
    if img:
        if img.url.startswith("/static/uploads/"):
            fpath = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                img.url.lstrip("/")
            )
            if os.path.exists(fpath):
                os.remove(fpath)
        db.delete(img)
        db.commit()
    if product_id:
        return RedirectResponse(f"/admin/products/edit/{product_id}", status_code=302)
    return RedirectResponse("/admin/products", status_code=302)


# ── Orders ────────────────────────────────────────────────────────────────────

@router.get("/orders")
async def admin_orders(request: Request, db: Session = Depends(get_db)):
    if not _is_admin(request):
        return RedirectResponse("/admin/login", status_code=302)
    ctx = _admin_ctx(request)
    ctx["orders"] = db.query(Order).order_by(Order.created_at.desc()).all()
    return templates.TemplateResponse("admin/orders.html", ctx)


@router.post("/orders/update/{order_id}")
async def admin_update_order(
    order_id: int,
    request: Request,
    status: str = Form(...),
    tracking_number: str = Form(""),
    db: Session = Depends(get_db),
):
    if not _is_admin(request):
        return RedirectResponse("/admin/login", status_code=302)
    order = db.query(Order).filter(Order.id == order_id).first()
    if order:
        order.status = status
        order.tracking_number = tracking_number.strip()
        db.commit()
    return RedirectResponse("/admin/orders", status_code=302)


@router.post("/orders/delete/{order_id}")
async def admin_delete_order(order_id: int, request: Request, db: Session = Depends(get_db)):
    if not _is_admin(request):
        return RedirectResponse("/admin/login", status_code=302)
    order = db.query(Order).filter(Order.id == order_id).first()
    if order:
        db.delete(order)
        db.commit()
    return RedirectResponse("/admin/orders", status_code=302)


# ── Settings ──────────────────────────────────────────────────────────────────

def _get_setting(db: Session, key: str) -> str:
    row = db.query(SiteSetting).filter(SiteSetting.key == key).first()
    return row.value if row else ""


def _set_setting(db: Session, key: str, value: str):
    row = db.query(SiteSetting).filter(SiteSetting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(SiteSetting(key=key, value=value))


@router.get("/settings")
async def admin_settings_page(request: Request, db: Session = Depends(get_db)):
    if not _is_admin(request):
        return RedirectResponse("/admin/login", status_code=302)
    ctx = _admin_ctx(request)
    ctx["stripe_public_key"]     = _get_setting(db, "stripe_public_key")
    ctx["stripe_secret_key"]     = _get_setting(db, "stripe_secret_key")
    ctx["stripe_webhook_secret"] = _get_setting(db, "stripe_webhook_secret")
    ctx["success"] = request.query_params.get("success", "")
    return templates.TemplateResponse("admin/settings.html", ctx)


@router.post("/settings")
async def admin_settings_save(
    request: Request,
    stripe_public_key:     str = Form(""),
    stripe_secret_key:     str = Form(""),
    stripe_webhook_secret: str = Form(""),
    db: Session = Depends(get_db),
):
    if not _is_admin(request):
        return RedirectResponse("/admin/login", status_code=302)
    _set_setting(db, "stripe_public_key",     stripe_public_key.strip())
    _set_setting(db, "stripe_secret_key",     stripe_secret_key.strip())
    _set_setting(db, "stripe_webhook_secret", stripe_webhook_secret.strip())
    db.commit()
    return RedirectResponse("/admin/settings?success=1", status_code=302)
