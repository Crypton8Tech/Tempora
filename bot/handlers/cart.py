"""Cart & checkout handler."""

import uuid, logging
from aiogram import Router, F
from aiogram.types import CallbackQuery, Message
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from app.database import get_db_session
from app.models import Product, User, CartItem, Order, OrderItem
from bot.keyboards import cart_kb, checkout_kb, checkout_back_kb, main_menu_kb

router = Router()
log = logging.getLogger(__name__)


class Checkout(StatesGroup):
    address = State()
    phone = State()
    note = State()


def _fmt(v: float) -> str:
    return f"{v:,.0f}".replace(",", " ")


def _get_or_create_user(db, tg_user) -> User:
    u = db.query(User).filter(User.telegram_id == str(tg_user.id)).first()
    if not u:
        u = User(
            email=f"tg_{tg_user.id}@tempora.bot",
            password_hash="",
            name=tg_user.full_name or "Telegram User",
            telegram_id=str(tg_user.id),
        )
        db.add(u)
        db.commit()
        db.refresh(u)
    return u


async def _edit(cb: CallbackQuery, text, kb=None):
    try:
        await cb.message.edit_text(text, reply_markup=kb)
    except Exception:
        try:
            await cb.message.delete()
        except Exception:
            pass
        await cb.message.answer(text, reply_markup=kb)


def _cart_text(items) -> str:
    if not items:
        return "🛒 Ваша корзина пуста."
    total = 0
    lines = ["🛒 <b>Ваша корзина:</b>\n"]
    for it in items:
        if not it.product:
            continue
        s = it.product.price * it.quantity
        total += s
        lines.append(f"• {it.product.brand} {it.product.name} ×{it.quantity} — {_fmt(s)} ₽")
    lines.append(f"\n<b>Итого: {_fmt(total)} ₽</b>")
    return "\n".join(lines)


# ── Show cart ─────────────────────────────────────────────────────────────

@router.callback_query(F.data == "cart")
async def cb_cart(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.clear()
    db = get_db_session()
    try:
        u = _get_or_create_user(db, cb.from_user)
        items = db.query(CartItem).filter(CartItem.user_id == u.id).all()
        await _edit(cb, _cart_text(items), cart_kb(items))
    finally:
        db.close()


# ── Add to cart ───────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("add:"))
async def cb_add(cb: CallbackQuery):
    parts = cb.data.split(":")
    pid = int(parts[1])
    db = get_db_session()
    try:
        u = _get_or_create_user(db, cb.from_user)
        existing = db.query(CartItem).filter(CartItem.user_id == u.id, CartItem.product_id == pid).first()
        if existing:
            existing.quantity += 1
        else:
            db.add(CartItem(user_id=u.id, product_id=pid, quantity=1))
        db.commit()
        await cb.answer("✅ Добавлено в корзину!", show_alert=False)
    finally:
        db.close()


# ── Qty ±1 ────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("cq:"))
async def cb_qty(cb: CallbackQuery):
    await cb.answer()
    parts = cb.data.split(":")
    item_id, delta = int(parts[1]), int(parts[2])
    db = get_db_session()
    try:
        it = db.query(CartItem).get(item_id)
        if it:
            it.quantity = max(1, it.quantity + delta)
            db.commit()
        u = _get_or_create_user(db, cb.from_user)
        items = db.query(CartItem).filter(CartItem.user_id == u.id).all()
        await _edit(cb, _cart_text(items), cart_kb(items))
    finally:
        db.close()


# ── Remove item ───────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("cdel:"))
async def cb_del(cb: CallbackQuery):
    await cb.answer()
    item_id = int(cb.data.split(":")[1])
    db = get_db_session()
    try:
        it = db.query(CartItem).get(item_id)
        if it:
            db.delete(it)
            db.commit()
        u = _get_or_create_user(db, cb.from_user)
        items = db.query(CartItem).filter(CartItem.user_id == u.id).all()
        await _edit(cb, _cart_text(items), cart_kb(items))
    finally:
        db.close()


# ── Clear ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "cclear")
async def cb_clear(cb: CallbackQuery):
    await cb.answer()
    db = get_db_session()
    try:
        u = _get_or_create_user(db, cb.from_user)
        db.query(CartItem).filter(CartItem.user_id == u.id).delete()
        db.commit()
        await _edit(cb, "🛒 Корзина очищена.", main_menu_kb())
    finally:
        db.close()


# ── Checkout flow ─────────────────────────────────────────────────────────

@router.callback_query(F.data == "co:start")
async def cb_co_start(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    data = await state.get_data()
    addr = data.get("co_addr", "—")
    phone = data.get("co_phone", "—")
    note = data.get("co_note", "—")
    text = (
        "📋 <b>Оформление заказа</b>\n\n"
        f"📍 Адрес: {addr}\n"
        f"📞 Телефон: {phone}\n"
        f"📝 Комментарий: {note}\n\n"
        "Заполните данные или подтвердите:"
    )
    await _edit(cb, text, checkout_kb())


@router.callback_query(F.data == "co:address")
async def cb_co_addr(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.set_state(Checkout.address)
    await _edit(cb, "📍 Введите адрес доставки:", checkout_back_kb())


@router.message(Checkout.address)
async def msg_addr(message: Message, state: FSMContext):
    await state.update_data(co_addr=message.text.strip())
    await state.set_state(None)
    await message.answer("✅ Адрес сохранён.", reply_markup=checkout_kb())


@router.callback_query(F.data == "co:phone")
async def cb_co_phone(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.set_state(Checkout.phone)
    await _edit(cb, "📞 Введите номер телефона:", checkout_back_kb())


@router.message(Checkout.phone)
async def msg_phone(message: Message, state: FSMContext):
    await state.update_data(co_phone=message.text.strip())
    await state.set_state(None)
    await message.answer("✅ Телефон сохранён.", reply_markup=checkout_kb())


@router.callback_query(F.data == "co:note")
async def cb_co_note(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    await state.set_state(Checkout.note)
    await _edit(cb, "📝 Введите комментарий к заказу:", checkout_back_kb())


@router.message(Checkout.note)
async def msg_note(message: Message, state: FSMContext):
    await state.update_data(co_note=message.text.strip())
    await state.set_state(None)
    await message.answer("✅ Комментарий сохранён.", reply_markup=checkout_kb())


@router.callback_query(F.data == "co:confirm")
async def cb_co_confirm(cb: CallbackQuery, state: FSMContext):
    await cb.answer()
    data = await state.get_data()
    db = get_db_session()
    try:
        u = _get_or_create_user(db, cb.from_user)
        items = db.query(CartItem).filter(CartItem.user_id == u.id).all()
        if not items:
            await _edit(cb, "🛒 Корзина пуста — нечего оформлять.", main_menu_kb())
            return

        total = sum((it.product.price * it.quantity) for it in items if it.product)
        order = Order(
            order_number=uuid.uuid4().hex[:12].upper(),
            user_id=u.id,
            status="pending",
            total=total,
            address=data.get("co_addr"),
            phone=data.get("co_phone"),
            note=data.get("co_note"),
        )
        db.add(order)
        db.flush()

        for it in items:
            if not it.product:
                continue
            img = it.product.images[0].url if it.product.images else None
            db.add(OrderItem(
                order_id=order.id,
                product_id=it.product_id,
                product_name=f"{it.product.brand} {it.product.name}",
                product_sku=it.product.sku,
                price=it.product.price,
                quantity=it.quantity,
                image_url=img,
            ))

        db.query(CartItem).filter(CartItem.user_id == u.id).delete()
        db.commit()

        await state.clear()
        await _edit(
            cb,
            f"✅ <b>Заказ оформлен!</b>\n\n"
            f"Номер: <code>{order.order_number}</code>\n"
            f"Сумма: {_fmt(total)} ₽\n\n"
            f"Мы свяжемся с вами для подтверждения.",
            main_menu_kb(),
        )
    finally:
        db.close()
