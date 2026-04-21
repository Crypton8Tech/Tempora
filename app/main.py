"""FastAPI main application."""

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

from app.config import settings
from app.database import init_db
from app.translations import t as _t, format_price as _format_price, loc as _loc, SUPPORTED_LANGS, SUPPORTED_CURRENCIES
from app.routers import pages, auth, api, admin


# ── Locale detection helpers ──────────────────────────────────────────────────

# Map full BCP-47 tag → preferred currency
_TAG_CURRENCY: dict[str, str] = {
    "en-gb": "gbp",
    "en-ie": "eur",
    "en-us": "usd",
    "en-ca": "usd",
    "en-au": "usd",
    "de-ch": "chf",
    "fr-ch": "chf",
    "it-ch": "chf",
    "de-at": "eur",
    "de-de": "eur",
    "de-lu": "eur",
    "fr-fr": "eur",
    "fr-be": "eur",
    "fr-lu": "eur",
    "it-it": "eur",
    "es-es": "eur",
}

# Map 2-letter lang → default currency
_LANG_CURRENCY: dict[str, str] = {
    "en": "eur",
    "ru": "eur",
    "de": "eur",
    "fr": "eur",
    "it": "eur",
    "es": "eur",
}


def _detect_lang(accept_language: str) -> str:
    """Parse Accept-Language header and return the best supported language code."""
    if not accept_language:
        return "en"
    # e.g. "de-DE,de;q=0.9,en;q=0.8,ru;q=0.7"
    for part in accept_language.split(","):
        tag = part.split(";")[0].strip().lower()
        lang2 = tag[:2]
        if lang2 in SUPPORTED_LANGS:
            return lang2
    return "en"


def _detect_currency(lang: str, accept_language: str) -> str:
    """Detect best currency from Accept-Language header."""
    if not accept_language:
        return _LANG_CURRENCY.get(lang, "eur")
    first_tag = accept_language.split(",")[0].strip().lower()
    if first_tag in _TAG_CURRENCY:
        return _TAG_CURRENCY[first_tag]
    return _LANG_CURRENCY.get(lang, "eur")


# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(application: FastAPI):
    """Startup / shutdown events."""
    init_db()
    from app.database import get_db_session
    from app.models import Category
    db = get_db_session()
    try:
        if db.query(Category).count() == 0:
            db.add_all([
                Category(slug="watches", name="Watches"),
                Category(slug="bags",    name="Bags"),
                Category(slug="clothing", name="Clothing"),
            ])
            db.commit()
    finally:
        db.close()
    yield


# ── App setup ─────────────────────────────────────────────────────────────────

app = FastAPI(title="TemporaShop", lifespan=lifespan)

app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)

static_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

templates_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
templates = Jinja2Templates(directory=templates_dir)
templates.env.globals["t"] = _t
templates.env.globals["format_price"] = _format_price
templates.env.globals["loc"] = _loc


# ── Auto-detect locale middleware ─────────────────────────────────────────────

@app.middleware("http")
async def auto_detect_locale(request: Request, call_next):
    """
    On the very first visit (no lang/currency cookie set) parse Accept-Language
    and set sensible defaults so the user immediately sees their language + currency.
    """
    response = await call_next(request)

    has_lang = request.cookies.get("lang")
    has_cur  = request.cookies.get("currency")

    if not has_lang or not has_cur:
        accept_lang = request.headers.get("accept-language", "")
        lang     = has_lang or _detect_lang(accept_lang)
        currency = has_cur  or _detect_currency(lang, accept_lang)

        if not has_lang:
            response.set_cookie("lang",     lang,     max_age=365 * 86400, samesite="lax")
        if not has_cur:
            response.set_cookie("currency", currency, max_age=365 * 86400, samesite="lax")

    return response


# ── Language / Currency cookie endpoints ──────────────────────────────────────

@app.get("/set-lang/{lang}")
async def set_language(lang: str, request: Request):
    if lang not in SUPPORTED_LANGS:
        lang = "en"
    referer = request.headers.get("referer", "/")
    response = Response(status_code=302, headers={"Location": referer})
    response.set_cookie("lang", lang, max_age=365 * 86400, samesite="lax")
    return response


@app.get("/set-currency/{cur}")
async def set_currency(cur: str, request: Request):
    if cur not in SUPPORTED_CURRENCIES:
        cur = "eur"
    referer = request.headers.get("referer", "/")
    response = Response(status_code=302, headers={"Location": referer})
    response.set_cookie("currency", cur, max_age=365 * 86400, samesite="lax")
    return response


# ── Routers ───────────────────────────────────────────────────────────────────

app.include_router(pages.router)
app.include_router(auth.router,  prefix="/auth")
app.include_router(api.router,   prefix="/api")
app.include_router(admin.router, prefix="/admin")
