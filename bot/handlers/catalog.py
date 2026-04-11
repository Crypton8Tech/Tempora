"""Catalog — browse, search, filter products with photo cards."""

import os, logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, InputMediaPhoto, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from app.database import get_db_session
from app.models import Product, Category, User, CartItem
from app.config import settings
from bot.keyboards import (
    categories_kb, product_card_kb, product_detail_kb,
    price_filter_kb, search_cancel_kb, main_menu_kb,
)

router = Router()
log = logging.getLogger(__name__)

_APP_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "app")


class Search(StatesGroup):
    query = State()


# ── helpers ───────────────────────────────────────────────────────────────

def _fmt(p: float) -> str:
    return f"{p:,.0f}".replace(",", " ")


def _photo(product) -> FSInputFile | None:
    """Get FSInputFile for the first image of a product (from disk)."""
    if product.images:
        rel = product.images[0].url.lstrip("/")          # static/uploads/xxx.jpg
        path = os.path.join(_APP_DIR, rel)
        if os.path.isfile(path):
            return FSInputFile(path)
    return None


def _caption(product, short=True) -> str:
    p = _fmt(product.price)
    cat = product.category.name if product.category else ""
    if short:
        t = f"<b>{product.brand} {product.name}</b>\n"
        if product.model:
            t += f"Модель: {product.model}\n"
        t += f"\n💰 <b>{p} ₽</b>"
        if cat:
            t += f"\n📂 {cat}"
        if product.description:
            d = product.description[:200]
            if len(product.description) > 200:
                d += "…"
            t += f"\n\n{d}"
        return t
    # detailed
    t = f"<b>{product.brand} {product.name}</b>\n"
    if product.model:
        t += f"Модель: {product.model}\n"
    t += f"SKU: <code>{product.sku}</code>\n\n💰 <b>{p} ₽</b>"
    if cat:
        t += f"\n📂 {cat}"
    if product.description:
        t += f"\n\n{product.description}"
    if product.characteristics:
        t += "\n\n<b>Характеристики:</b>\n"
        for k, v in product.characteristics.items():
            t += f"• {k}: {v}\n"
    return t[:1024]


def _in_cart(db, tg_id: int, pid: int) -> bool:
    u = db.query(User).filter(User.telegram_id == str(tg_id)).first()
    if u:
        return db.query(CartItem).filter(CartItem.user_id == u.id, CartItem.product_id == pid).first() is not None
    return False


def _load_products(state_data, db, slug: str):
    """Load product list from FSM cache or DB."""
    ids = state_data.get("pids")
    if ids:
        by_id = {p.id: p for p in db.query(Product).filter(Product.id.in_(ids)).all()}
        prods = [by_id[i] for i in ids if i in by_id]
        if prods:
            return prods
    q = db.query(Product).filter(Product.is_active == True)
    if slug != "all":
        cat = db.query(Category).filter(Category.slug == slug).first()
        if cat:
            q = q.filter(Product.category_id == cat.id)
    return q.order_by(Product.created_at.desc()).all()


# ── send / edit helpers ───────────────────────────────────────────────────

async def _send_card(target, product, idx, total, slug, ic, photo):
    """Send a NEW photo message (initial card). target = Message or CallbackQuery.message"""
    cap = _caption(product)
    kb = product_card_kb(product, idx, total, slug, ic)
    if photo:
        return await target.answer_photo(photo=photo, caption=cap, reply_markup=kb)
    return await target.answer(cap, reply_markup=kb)


async def _edit_card(msg, product, idx, total, slug, ic, photo):
    """Edit existing message in place (no flicker)."""
    cap = _caption(product)
    kb = product_card_kb(product, idx, total, slug, ic)
    if photo:
        try:
            await msg.edit_media(
                media=InputMediaPhoto(media=photo, caption=cap),
                reply_markup=kb,
            )
            return
        except Exception:
            pass
    # photo-less or edit_media failed — try edit_caption then edit_text
    try:
        await msg.edit_caption(caption=cap, reply_markup=kb)
        return
    except Exception:
        pass
    try:
        await msg.edit_text(cap, reply_markup=kb)
        return
    except Exception:
        pass
    # last resort: delete & resend
    try:
        await msg.delete()
    except Exception:
        pass
    if photo:
        await msg.answer_photo(photo=photo, caption=cap, reply_markup=kb)
    else:
        await msg.answer(cap, reply_markup=kb)


async def _to_text(cb: CallbackQuery, text, kb=None):
    """Switch current message to plain text."""
    try:
        await cb.message.edit_text(text, reply_markup=kb)
    except Exception:
        try:
            await cb.message.delete()
        except Exception:
            pass
        await cb.message.answer(text, reply_markup=kb)


# ── Categories ────────────────────────────────────────────────────────────

@router.callback_query(F.data == "catalog")
async def cb_catalog(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.clear()
    db = get_db_session()
    try:
        cats = db.query(Category).all()
        cnt = {c.id: db.query(Product).filter(Product.category_id == c.id, Product.is_active == True).count() for c in cats}
        await _to_text(cb, "📂 <b>Выберите категорию:</b>", categories_kb(cats, cnt))
    finally:
        db.close()


# ── Pick category → first card ───────────────────────────────────────────

@router.callback_query(F.data.startswith("cat:"))
async def cb_category(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    slug = cb.data.split(":")[1]
    db = get_db_session()
    try:
        q = db.query(Product).filter(Product.is_active == True)
        if slug != "all":
            cat = db.query(Category).filter(Category.slug == slug).first()
            if cat:
                q = q.filter(Product.category_id == cat.id)
        prods = q.order_by(Product.created_at.desc()).all()
        if not prods:
            await _to_text(cb, "😔 В этой категории пока нет товаров.", categories_kb(db.query(Category).all()))
            return
        await state.update_data(pids=[p.id for p in prods], slug=slug)
        p = prods[0]
        ph = _photo(p)
        ic = _in_cart(db, cb.from_user.id, p.id)
        # Transition text→photo: delete old, send new
        try:
            await cb.message.delete()
        except Exception:
            pass
        await _send_card(cb.message, p, 0, len(prods), slug, ic, ph)
    finally:
        db.close()


# ── Browse (prev/next arrows) ────────────────────────────────────────────

@router.callback_query(F.data.startswith("page:"))
async def cb_page(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    parts = cb.data.split(":")
    slug = parts[1]
    idx = int(parts[2])
    db = get_db_session()
    try:
        data = await state.get_data()
        prods = _load_products(data, db, slug)
        if not prods:
            await _to_text(cb, "Товары не найдены.", main_menu_kb())
            return
        if not data.get("pids"):
            await state.update_data(pids=[p.id for p in prods], slug=slug)
        idx = max(0, min(idx, len(prods) - 1))
        p = prods[idx]
        ic = _in_cart(db, cb.from_user.id, p.id)
        ph = _photo(p)
        await _edit_card(cb.message, p, idx, len(prods), slug, ic, ph)
    finally:
        db.close()


# ── Product detail ────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("detail:"))
async def cb_detail(cb: CallbackQuery):
    await cb.answer()
    parts = cb.data.split(":")
    pid, slug, idx = int(parts[1]), parts[2], int(parts[3])
    db = get_db_session()
    try:
        p = db.query(Product).filter(Product.id == pid).first()
        if not p:
            await _to_text(cb, "Товар не найден.", main_menu_kb())
            return
        ic = _in_cart(db, cb.from_user.id, p.id)
        cap = _caption(p, short=False)
        kb = product_detail_kb(p, slug, idx, ic)
        # We're on a photo message — edit caption
        try:
            await cb.message.edit_caption(caption=cap, reply_markup=kb)
            return
        except Exception:
            pass
        ph = _photo(p)
        if ph:
            try:
                await cb.message.edit_media(
                    media=InputMediaPhoto(media=ph, caption=cap), reply_markup=kb)
                return
            except Exception:
                pass
        await _to_text(cb, cap, kb)
    finally:
        db.close()


# ── Search ────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "search")
async def cb_search(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.set_state(Search.query)
    await _to_text(cb, "🔍 <b>Поиск</b>\n\nВведите название, бренд или модель:", search_cancel_kb())


@router.message(Search.query)
async def msg_search(message: Message, state: FSMContext):
    await state.clear()
    q = message.text.strip()
    db = get_db_session()
    try:
        prods = db.query(Product).filter(
            Product.is_active == True,
            (Product.name.ilike(f"%{q}%")) |
            (Product.brand.ilike(f"%{q}%")) |
            (Product.model.ilike(f"%{q}%"))
        ).order_by(Product.created_at.desc()).all()
        if not prods:
            await message.answer(f"🔍 По «{q}» ничего не найдено.", reply_markup=main_menu_kb())
            return
        await state.update_data(pids=[p.id for p in prods], slug="all")
        p = prods[0]
        ic = _in_cart(db, message.from_user.id, p.id)
        ph = _photo(p)
        await _send_card(message, p, 0, len(prods), "all", ic, ph)
    finally:
        db.close()


# ── Brand filter ──────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("fbrand:"))
async def cb_brand(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    brand = cb.data.split(":", 1)[1]
    db = get_db_session()
    try:
        prods = db.query(Product).filter(Product.is_active == True, Product.brand.ilike(f"%{brand}%")).order_by(Product.created_at.desc()).all()
        if not prods:
            await _to_text(cb, f"По бренду «{brand}» ничего не найдено.", main_menu_kb())
            return
        await state.update_data(pids=[p.id for p in prods], slug="all")
        p = prods[0]
        ic = _in_cart(db, cb.from_user.id, p.id)
        ph = _photo(p)
        try:
            await cb.message.delete()
        except Exception:
            pass
        await _send_card(cb.message, p, 0, len(prods), "all", ic, ph)
    finally:
        db.close()


# ── Price filter ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "price_filter")
async def cb_price_menu(cb: CallbackQuery):
    await cb.answer()
    await _to_text(cb, "💰 <b>Фильтр по цене:</b>", price_filter_kb())


@router.callback_query(F.data.startswith("fp:"))
async def cb_price_range(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    parts = cb.data.split(":")
    lo, hi = int(parts[1]), int(parts[2])
    db = get_db_session()
    try:
        q = db.query(Product).filter(Product.is_active == True)
        if lo > 0:
            q = q.filter(Product.price >= lo)
        if hi > 0:
            q = q.filter(Product.price <= hi)
        prods = q.order_by(Product.price.asc()).all()
        if not prods:
            await _to_text(cb, "Ничего не найдено в этом диапазоне.", main_menu_kb())
            return
        await state.update_data(pids=[p.id for p in prods], slug="all")
        p = prods[0]
        ic = _in_cart(db, cb.from_user.id, p.id)
        ph = _photo(p)
        try:
            await cb.message.delete()
        except Exception:
            pass
        await _send_card(cb.message, p, 0, len(prods), "all", ic, ph)
    finally:
        db.close()
