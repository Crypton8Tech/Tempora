"""Admin panel routes."""

import os
import uuid
import shutil

from fastapi import APIRouter, Request, Depends, Form, UploadFile, File
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Product, ProductImage, Category, Order, SiteSetting

from app.translations import t as _t, format_price as _fp, loc as _loc

router = APIRouter()
templates = Jinja2Templates(
    directory=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates")
)
templates.env.globals["t"] = _t
templates.env.globals["format_price"] = _fp
templates.env.globals["loc"] = _loc


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
    products_count = db.query(Product).count()
    orders_count = len(orders)
    total_revenue = sum(o.total for o in orders)

    ctx.update({
        "orders": orders,
        "products_count": products_count,
        "orders_count": orders_count,
        "total_revenue": total_revenue,
    })
    return templates.TemplateResponse("admin/dashboard.html", ctx)


# ── Products ──────────────────────────────────────────────────────────────────

@router.get("/products")
async def admin_products(request: Request, db: Session = Depends(get_db)):
    if not _is_admin(request):
        return RedirectResponse("/admin/login", status_code=302)
    ctx = _admin_ctx(request)
    products = db.query(Product).order_by(Product.created_at.desc()).all()
    ctx["products"] = products
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
    name_en: str = Form(""),
    sku: str = Form(...),
    brand: str = Form(""),
    model: str = Form(""),
    description: str = Form(""),
    description_en: str = Form(""),
    price: float = Form(...),
    category_id: int = Form(...),
    db: Session = Depends(get_db),
):
    if not _is_admin(request):
        return RedirectResponse("/admin/login", status_code=302)

    # Check duplicate SKU
    existing = db.query(Product).filter(Product.sku == sku).first()
    if existing:
        ctx = _admin_ctx(request)
        ctx["categories"] = db.query(Category).all()
        ctx["error"] = "SKU уже существует"
        return templates.TemplateResponse("admin/add_product.html", ctx)

    product = Product(
        sku=sku.strip(),
        brand=brand.strip(),
        model=model.strip(),
        name=name.strip(),
        name_en=name_en.strip() or None,
        description=description.strip(),
        description_en=description_en.strip() or None,
        price=price,
        category_id=category_id,
    )
    db.add(product)
    db.flush()

    # Handle file uploads
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
    ctx = _admin_ctx(request)
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        return RedirectResponse("/admin/products", status_code=302)
    ctx["product"] = product
    ctx["categories"] = db.query(Category).all()
    ctx["error"] = ""
    return templates.TemplateResponse("admin/edit_product.html", ctx)


@router.post("/products/edit/{product_id}")
async def admin_edit_product_submit(
    product_id: int,
    request: Request,
    name: str = Form(...),
    name_en: str = Form(""),
    sku: str = Form(...),
    brand: str = Form(""),
    model: str = Form(""),
    description: str = Form(""),
    description_en: str = Form(""),
    price: float = Form(...),
    category_id: int = Form(...),
    is_active: bool = Form(True),
    db: Session = Depends(get_db),
):
    if not _is_admin(request):
        return RedirectResponse("/admin/login", status_code=302)

    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
        return RedirectResponse("/admin/products", status_code=302)

    product.name = name.strip()
    product.name_en = name_en.strip() or None
    product.sku = sku.strip()
    product.brand = brand.strip()
    product.model = model.strip()
    product.description = description.strip()
    product.description_en = description_en.strip() or None
    product.price = price
    product.category_id = category_id
    product.is_active = is_active

    # Handle new images
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
        # Delete image files too
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
    orders = db.query(Order).order_by(Order.created_at.desc()).all()
    ctx["orders"] = orders
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


# ── Settings (Payment providers) ──────────────────────────────────────────────

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

    from app.payments import (
        PROVIDERS, PROVIDER_FIELDS, PROVIDER_INSTRUCTIONS,
        get_active_provider, get_provider_settings,
        get_custom_providers, get_custom_provider_fields,
    )

    ctx = _admin_ctx(request)
    active = get_active_provider(db)
    custom_providers = get_custom_providers(db)

    all_providers = dict(PROVIDERS)
    all_providers.update(custom_providers)
    ctx["providers"] = all_providers
    ctx["builtin_providers"] = list(PROVIDERS.keys())
    ctx["active_provider"] = active

    # Merge built-in + custom fields
    all_fields = dict(PROVIDER_FIELDS)
    for slug in custom_providers:
        all_fields[slug] = get_custom_provider_fields(db, slug)
    ctx["provider_fields"] = all_fields
    ctx["provider_instructions"] = PROVIDER_INSTRUCTIONS
    ctx["site_url"] = settings.SITE_URL.rstrip("/")

    # Load saved values for all providers
    provider_values = {}
    for slug in all_providers:
        provider_values[slug] = get_provider_settings(db, slug)
    ctx["provider_values"] = provider_values

    ctx["success"] = request.query_params.get("success", "")
    ctx["custom_providers"] = custom_providers
    return templates.TemplateResponse("admin/settings.html", ctx)


@router.post("/settings")
async def admin_settings_save(
    request: Request,
    db: Session = Depends(get_db),
):
    if not _is_admin(request):
        return RedirectResponse("/admin/login", status_code=302)

    from app.payments import (
        PROVIDERS, PROVIDER_FIELDS,
        get_custom_providers, get_custom_provider_fields,
    )

    form = await request.form()
    provider = form.get("payment_provider", "stripe")

    all_providers = dict(PROVIDERS)
    all_providers.update(get_custom_providers(db))

    if provider not in all_providers:
        provider = "stripe"

    _set_setting(db, "payment_provider", provider)

    # Save fields for the selected provider
    if provider in PROVIDER_FIELDS:
        fields = PROVIDER_FIELDS[provider]
    else:
        fields = get_custom_provider_fields(db, provider)

    for fdef in fields:
        key = fdef[0]
        val = form.get(key, "")
        _set_setting(db, key, str(val).strip())

    db.commit()
    return RedirectResponse("/admin/settings?success=1", status_code=302)


@router.post("/settings/add-provider")
async def admin_add_custom_provider(
    request: Request,
    db: Session = Depends(get_db),
):
    """Add a new custom payment provider."""
    if not _is_admin(request):
        return RedirectResponse("/admin/login", status_code=302)

    from app.payments import (
        PROVIDERS, get_custom_providers, save_custom_providers,
        save_custom_provider_fields, _default_custom_fields,
    )
    import re

    form = await request.form()
    name = form.get("new_provider_name", "").strip()
    if not name:
        return RedirectResponse("/admin/settings", status_code=302)

    # Generate slug from name
    slug = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")
    if not slug or slug in PROVIDERS:
        slug = f"custom_{slug}"

    customs = get_custom_providers(db)
    customs[slug] = name
    save_custom_providers(db, customs)

    # Parse custom fields from form
    field_names = form.getlist("field_name")
    field_types = form.getlist("field_type")
    field_placeholders = form.getlist("field_placeholder")

    if field_names and any(n.strip() for n in field_names):
        fields = []
        for i, fname in enumerate(field_names):
            fname = fname.strip()
            if not fname:
                continue
            fkey = f"custom_{slug}_{re.sub(r'[^a-z0-9]+', '_', fname.lower()).strip('_')}"
            ftype = field_types[i].strip() if i < len(field_types) else "text"
            if ftype not in ("text", "password"):
                ftype = "text"
            fplaceholder = field_placeholders[i].strip() if i < len(field_placeholders) else ""
            fields.append({"key": fkey, "label": fname, "type": ftype, "placeholder": fplaceholder})
        if fields:
            save_custom_provider_fields(db, slug, fields)
    else:
        # Use default fields
        defaults = _default_custom_fields(slug)
        fields = [{"key": f[0], "label": f[1], "type": f[2], "placeholder": f[3]} for f in defaults]
        save_custom_provider_fields(db, slug, fields)

    db.commit()
    return RedirectResponse("/admin/settings?success=1", status_code=302)


@router.post("/settings/delete-provider/{slug}")
async def admin_delete_custom_provider(
    slug: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """Delete a custom payment provider."""
    if not _is_admin(request):
        return RedirectResponse("/admin/login", status_code=302)

    from app.payments import PROVIDERS, delete_custom_provider

    if slug in PROVIDERS:
        return RedirectResponse("/admin/settings", status_code=302)

    delete_custom_provider(db, slug)
    db.commit()
    return RedirectResponse("/admin/settings?success=1", status_code=302)
