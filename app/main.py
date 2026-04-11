"""FastAPI main application."""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.database import init_db
from app.translations import t as _t, format_price as _format_price, loc as _loc
from app.routers import pages, auth, api, admin


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Startup / shutdown events."""
    init_db()
    # Seed default categories
    from app.database import get_db_session
    from app.models import Category
    db = get_db_session()
    try:
        if db.query(Category).count() == 0:
            db.add_all([
                Category(slug="watches", name="Часы"),
                Category(slug="bags", name="Сумки"),
                Category(slug="clothing", name="Одежда"),
            ])
            db.commit()
    finally:
        db.close()
    yield


app = FastAPI(title="TemporaShop", lifespan=lifespan)

# Middleware
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

# Static files
static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Templates
templates_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
templates = Jinja2Templates(directory=templates_dir)

# Add i18n / currency globals to Jinja2
templates.env.globals["t"] = _t
templates.env.globals["format_price"] = _format_price
templates.env.globals["loc"] = _loc


# ── Language / Currency cookie endpoints ──────────────────────────────────────

@app.get("/set-lang/{lang}")
async def set_language(lang: str, request: Request):
    if lang not in ("ru", "en"):
        lang = "ru"
    referer = request.headers.get("referer", "/")
    response = Response(status_code=302, headers={"Location": referer})
    response.set_cookie("lang", lang, max_age=365 * 86400, samesite="lax")
    return response


@app.get("/set-currency/{cur}")
async def set_currency(cur: str, request: Request):
    if cur not in ("rub", "usd", "eur"):
        cur = "rub"
    referer = request.headers.get("referer", "/")
    response = Response(status_code=302, headers={"Location": referer})
    response.set_cookie("currency", cur, max_age=365 * 86400, samesite="lax")
    return response


# Routers
app.include_router(pages.router)
app.include_router(auth.router, prefix="/auth")
app.include_router(api.router, prefix="/api")
app.include_router(admin.router, prefix="/admin")
