"""Orders, tracking, help, site handlers."""

import logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from app.database import get_db_session
from app.models import Order, User
from app.config import settings
from bot.keyboards import (
    orders_kb, order_detail_kb, track_kb, track_result_kb,
    help_kb, faq_kb, site_kb, main_menu_kb,
)

router = Router()
log = logging.getLogger(__name__)

STATUS_MAP = {
    "pending": "⏳ В обработке", "paid": "💳 Оплачен",
    "shipped": "🚚 Отправлен", "delivered": "✅ Доставлен",
    "cancelled": "❌ Отменён",
}


class Track(StatesGroup):
    number = State()


def _fmt(v: float) -> str:
    return f"{v:,.0f}".replace(",", " ")


def _get_user(db, tg_id: int):
    return db.query(User).filter(User.telegram_id == str(tg_id)).first()


async def _edit(cb: CallbackQuery, text, kb=None):
    try:
        await cb.message.edit_text(text, reply_markup=kb)
    except Exception:
        pass


def _order_text(o: Order) -> str:
    st = STATUS_MAP.get(o.status, o.status)
    dt = o.created_at.strftime("%d.%m.%Y %H:%M") if o.created_at else ""
    t = (
        f"📦 <b>Заказ #{o.order_number}</b>\n\n"
        f"Статус: {st}\n"
        f"Дата: {dt}\n"
        f"Сумма: <b>{_fmt(o.total)} ₽</b>\n"
    )
    if o.address:
        t += f"📍 {o.address}\n"
    if o.phone:
        t += f"📞 {o.phone}\n"
    if o.tracking_number:
        t += f"📦 Трек: <code>{o.tracking_number}</code>\n"
    if o.note:
        t += f"📝 {o.note}\n"
    t += "\n<b>Состав:</b>\n"
    for it in o.items:
        t += f"• {it.product_name} ×{it.quantity} — {_fmt(it.price * it.quantity)} ₽\n"
    return t


# ── Orders list ───────────────────────────────────────────────────────────

@router.callback_query(F.data == "orders")
async def cb_orders(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.clear()
    db = get_db_session()
    try:
        u = _get_user(db, cb.from_user.id)
        if not u:
            await _edit(cb, "📦 У вас пока нет заказов.", main_menu_kb())
            return
        ords = db.query(Order).filter(Order.user_id == u.id).order_by(Order.created_at.desc()).all()
        if not ords:
            await _edit(cb, "📦 У вас пока нет заказов.", main_menu_kb())
            return
        await _edit(cb, f"📦 <b>Ваши заказы ({len(ords)}):</b>", orders_kb(ords))
    finally:
        db.close()


@router.callback_query(F.data.startswith("ordp:"))
async def cb_orders_page(cb: CallbackQuery):
    await cb.answer()
    page = int(cb.data.split(":")[1])
    db = get_db_session()
    try:
        u = _get_user(db, cb.from_user.id)
        ords = db.query(Order).filter(Order.user_id == u.id).order_by(Order.created_at.desc()).all() if u else []
        await _edit(cb, f"📦 <b>Ваши заказы ({len(ords)}):</b>", orders_kb(ords, page))
    finally:
        db.close()


@router.callback_query(F.data.startswith("ord:"))
async def cb_order(cb: CallbackQuery):
    await cb.answer()
    oid = int(cb.data.split(":")[1])
    db = get_db_session()
    try:
        o = db.query(Order).filter(Order.id == oid).first()
        if not o:
            await _edit(cb, "Заказ не найден.", main_menu_kb())
            return
        await _edit(cb, _order_text(o), order_detail_kb(o))
    finally:
        db.close()


@router.callback_query(F.data.startswith("ordcancel:"))
async def cb_order_cancel(cb: CallbackQuery):
    oid = int(cb.data.split(":")[1])
    db = get_db_session()
    try:
        o = db.query(Order).filter(Order.id == oid).first()
        if o and o.status == "pending":
            o.status = "cancelled"
            db.commit()
            db.refresh(o)
            await cb.answer("Заказ отменён", show_alert=True)
            await _edit(cb, _order_text(o), order_detail_kb(o))
        else:
            await cb.answer("Невозможно отменить", show_alert=True)
    finally:
        db.close()


# ── Tracking ──────────────────────────────────────────────────────────────

@router.callback_query(F.data == "track")
async def cb_track(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.set_state(Track.number)
    await _edit(cb, "📍 <b>Трекинг</b>\n\nВведите номер заказа или трек-номер:", track_kb())


@router.message(Track.number)
async def msg_track(message: Message, state: FSMContext):
    await state.clear()
    q = message.text.strip()
    db = get_db_session()
    try:
        o = db.query(Order).filter(
            (Order.order_number == q) | (Order.tracking_number == q)
        ).first()
        if not o:
            await message.answer(f"❌ Заказ «{q}» не найден.", reply_markup=track_result_kb())
            return
        st = STATUS_MAP.get(o.status, o.status)
        text = f"📦 <b>Заказ #{o.order_number}</b>\n\nСтатус: {st}\n"
        if o.tracking_number:
            text += f"Трек: <code>{o.tracking_number}</code>\n"
        text += f"Сумма: {_fmt(o.total)} ₽"
        await message.answer(text, reply_markup=track_result_kb())
    finally:
        db.close()


# ── Help ──────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "help")
async def cb_help(cb: CallbackQuery):
    await cb.answer()
    await _edit(cb, "💬 <b>Помощь TemporaShop</b>\n\nВыберите раздел:", help_kb())


@router.callback_query(F.data == "faq")
async def cb_faq(cb: CallbackQuery):
    await cb.answer()
    text = (
        "❓ <b>FAQ</b>\n\n"
        "<b>Как оформить заказ?</b>\nВыберите товар → В корзину → Оформить.\n\n"
        "<b>Способы оплаты?</b>\nПеревод, карта, криптовалюта.\n\n"
        "<b>Сроки доставки?</b>\n3–7 рабочих дней по России.\n\n"
        "<b>Возврат?</b>\n14 дней с момента получения."
    )
    await _edit(cb, text, faq_kb())


@router.callback_query(F.data == "contact")
async def cb_contact(cb: CallbackQuery):
    await cb.answer()
    await _edit(
        cb,
        "📧 <b>Связь с нами</b>\n\n"
        "Email: support@temporashop.ru\n"
        "Telegram: @TemporaSupport\n\n"
        "Ответим в течение 24 часов.",
        faq_kb(),
    )


# ── Site ──────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "site")
async def cb_site(cb: CallbackQuery):
    await cb.answer()
    url = settings.SITE_URL
    await _edit(cb, f"🌐 <b>TemporaShop</b>\n\nНаш сайт: {url}", site_kb(url))
