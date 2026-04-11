"""Admin panel — stats, product CRUD, order management."""

import uuid, logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

from app.database import get_db_session
from app.models import Product, Category, Order, User
from app.config import settings
from bot.keyboards import (
    admin_menu_kb, admin_products_kb, admin_product_kb,
    admin_del_confirm_kb, admin_orders_kb, admin_order_kb,
    admin_order_del_confirm_kb, admin_cancel_kb, main_menu_kb,
)

router = Router()
log = logging.getLogger(__name__)

STATUS_MAP = {
    "pending": "⏳ В обработке", "paid": "💳 Оплачен",
    "shipped": "🚚 Отправлен", "delivered": "✅ Доставлен",
    "cancelled": "❌ Отменён",
}


class AddProduct(StatesGroup):
    name = State()
    brand = State()
    price = State()
    category = State()
    description = State()


class EditField(StatesGroup):
    value = State()


class TrackInput(StatesGroup):
    number = State()


def _admin(uid: int) -> bool:
    return uid in settings.BOT_ADMIN_IDS


def _fmt(v: float) -> str:
    return f"{v:,.0f}".replace(",", " ")


async def _edit(cb: CallbackQuery, text, kb=None):
    try:
        await cb.message.edit_text(text, reply_markup=kb)
    except Exception:
        try:
            await cb.message.delete()
        except Exception:
            pass
        await cb.message.answer(text, reply_markup=kb)


def _prod_text(p) -> str:
    st = "✅ Активен" if p.is_active else "⬜ Скрыт"
    cat = p.category.name if p.category else "—"
    imgs = len(p.images) if p.images else 0
    t = (
        f"📦 <b>{p.brand} {p.name}</b>\n\n"
        f"SKU: <code>{p.sku}</code>\n"
        f"Модель: {p.model or '—'}\n"
        f"Цена: <b>{_fmt(p.price)} ₽</b>\n"
        f"Категория: {cat}\n"
        f"Статус: {st}\n"
        f"Фото: {imgs}\n"
    )
    if p.description:
        d = p.description[:300]
        if len(p.description) > 300:
            d += "…"
        t += f"\n{d}"
    return t


def _ord_text(o) -> str:
    st = STATUS_MAP.get(o.status, o.status)
    dt = o.created_at.strftime("%d.%m.%Y %H:%M") if o.created_at else ""
    ui = ""
    if o.user:
        ui = f"👤 {o.user.name}"
        if o.user.email:
            ui += f" ({o.user.email})"
        ui += "\n"
    t = (
        f"🛒 <b>Заказ #{o.order_number}</b>\n\n"
        f"{ui}Статус: {st}\nДата: {dt}\n"
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


# ── Entry ─────────────────────────────────────────────────────────────────

@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not _admin(message.from_user.id):
        return await message.answer("⛔ Нет доступа.")
    await message.answer("⚙️ <b>Админ-панель</b>", reply_markup=admin_menu_kb())


@router.callback_query(F.data == "adm:menu")
async def cb_admin_menu(cb: CallbackQuery, state: FSMContext):
    if not _admin(cb.from_user.id):
        return await cb.answer("⛔", show_alert=True)
    await cb.answer()
    await state.clear()
    await _edit(cb, "⚙️ <b>Админ-панель</b>", admin_menu_kb())


# ── Stats ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "adm:stats")
async def cb_stats(cb: CallbackQuery):
    if not _admin(cb.from_user.id):
        return await cb.answer("⛔", show_alert=True)
    await cb.answer()
    db = get_db_session()
    try:
        pc = db.query(Product).count()
        ac = db.query(Product).filter(Product.is_active == True).count()
        ords = db.query(Order).all()
        uc = db.query(User).count()
        rev = sum(o.total for o in ords)
        by_st = {}
        for o in ords:
            by_st[o.status] = by_st.get(o.status, 0) + 1
        text = (
            f"📊 <b>Статистика</b>\n\n"
            f"📦 Товаров: {pc} (активных: {ac})\n"
            f"👥 Пользователей: {uc}\n\n"
            f"🛒 <b>Заказы ({len(ords)}):</b>\n"
            f"  ⏳ В обработке: {by_st.get('pending', 0)}\n"
            f"  💳 Оплачено: {by_st.get('paid', 0)}\n"
            f"  🚚 Отправлено: {by_st.get('shipped', 0)}\n"
            f"  ✅ Доставлено: {by_st.get('delivered', 0)}\n\n"
            f"💰 <b>Выручка: {_fmt(rev)} ₽</b>"
        )
        await _edit(cb, text, admin_menu_kb())
    finally:
        db.close()


# ── Products list ─────────────────────────────────────────────────────────

@router.callback_query(F.data.regexp(r"^adm:prods:\d+$"))
async def cb_products(cb: CallbackQuery):
    if not _admin(cb.from_user.id):
        return await cb.answer("⛔", show_alert=True)
    await cb.answer()
    page = int(cb.data.split(":")[2])
    db = get_db_session()
    try:
        prods = db.query(Product).order_by(Product.created_at.desc()).all()
        if not prods:
            return await _edit(cb, "📦 Товаров нет.", admin_menu_kb())
        await _edit(cb, f"📦 <b>Товары ({len(prods)}):</b>", admin_products_kb(prods, page))
    finally:
        db.close()


# ── Product detail ────────────────────────────────────────────────────────

@router.callback_query(F.data.regexp(r"^adm:p:\d+$"))
async def cb_product(cb: CallbackQuery):
    if not _admin(cb.from_user.id):
        return await cb.answer("⛔", show_alert=True)
    await cb.answer()
    pid = int(cb.data.split(":")[2])
    db = get_db_session()
    try:
        p = db.query(Product).get(pid)
        if not p:
            return await _edit(cb, "Товар не найден.", admin_menu_kb())
        await _edit(cb, _prod_text(p), admin_product_kb(p))
    finally:
        db.close()


# ── Toggle active ─────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("adm:tog:"))
async def cb_toggle(cb: CallbackQuery):
    if not _admin(cb.from_user.id):
        return await cb.answer("⛔", show_alert=True)
    pid = int(cb.data.split(":")[2])
    db = get_db_session()
    try:
        p = db.query(Product).get(pid)
        if not p:
            return await cb.answer("Не найден", show_alert=True)
        p.is_active = not p.is_active
        db.commit()
        db.refresh(p)
        await cb.answer("✅ Активен" if p.is_active else "⬜ Скрыт", show_alert=True)
        await _edit(cb, _prod_text(p), admin_product_kb(p))
    finally:
        db.close()


# ── Delete product ────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("adm:del:"))
async def cb_del(cb: CallbackQuery):
    if not _admin(cb.from_user.id):
        return await cb.answer("⛔", show_alert=True)
    await cb.answer()
    pid = int(cb.data.split(":")[2])
    db = get_db_session()
    try:
        p = db.query(Product).get(pid)
        if not p:
            return await _edit(cb, "Не найден.", admin_menu_kb())
        await _edit(cb, f"🗑 Удалить <b>{p.brand} {p.name}</b>?\n\n⚠️ Необратимо!", admin_del_confirm_kb(pid))
    finally:
        db.close()


@router.callback_query(F.data.startswith("adm:delok:"))
async def cb_delok(cb: CallbackQuery):
    if not _admin(cb.from_user.id):
        return await cb.answer("⛔", show_alert=True)
    await cb.answer()
    pid = int(cb.data.split(":")[2])
    db = get_db_session()
    try:
        p = db.query(Product).get(pid)
        if p:
            nm = f"{p.brand} {p.name}"
            db.delete(p)
            db.commit()
            await _edit(cb, f"✅ «{nm}» удалён.", admin_menu_kb())
        else:
            await _edit(cb, "Не найден.", admin_menu_kb())
    finally:
        db.close()


# ── Edit field ────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("adm:ed:"))
async def cb_edit_field(cb: CallbackQuery, state: FSMContext):
    if not _admin(cb.from_user.id):
        return await cb.answer("⛔", show_alert=True)
    await cb.answer()
    parts = cb.data.split(":")
    field, pid = parts[2], int(parts[3])
    await state.update_data(ef_field=field, ef_pid=pid)
    await state.set_state(EditField.value)
    labels = {"price": "цену", "desc": "описание"}
    await _edit(cb, f"✏️ Введите новую <b>{labels.get(field, field)}</b>:", admin_cancel_kb())


@router.message(EditField.value)
async def msg_edit_value(message: Message, state: FSMContext):
    data = await state.get_data()
    field, pid = data.get("ef_field"), data.get("ef_pid")
    await state.clear()
    if not field or not pid:
        return
    db = get_db_session()
    try:
        p = db.query(Product).get(pid)
        if not p:
            return await message.answer("Не найден.", reply_markup=admin_menu_kb())
        if field == "price":
            try:
                p.price = float(message.text.strip().replace(" ", "").replace(",", "."))
            except ValueError:
                await state.update_data(ef_field=field, ef_pid=pid)
                await state.set_state(EditField.value)
                return await message.answer("❌ Неверная цена.", reply_markup=admin_cancel_kb())
        elif field == "desc":
            p.description = message.text.strip()
        db.commit()
        db.refresh(p)
        await message.answer(f"✅ Обновлено!\n\n{_prod_text(p)}", reply_markup=admin_product_kb(p))
    finally:
        db.close()


# ── Add product ───────────────────────────────────────────────────────────

@router.callback_query(F.data == "adm:addprod")
async def cb_addprod(cb: CallbackQuery, state: FSMContext):
    if not _admin(cb.from_user.id):
        return await cb.answer("⛔", show_alert=True)
    await cb.answer()
    await state.set_state(AddProduct.name)
    await state.update_data(ap={})
    await _edit(cb, "➕ <b>Новый товар</b>\n\n📝 Название:", admin_cancel_kb())


@router.message(AddProduct.name)
async def msg_ap_name(message: Message, state: FSMContext):
    d = (await state.get_data()).get("ap", {})
    d["name"] = message.text.strip()
    await state.update_data(ap=d)
    await state.set_state(AddProduct.brand)
    await message.answer("Бренд:", reply_markup=admin_cancel_kb())


@router.message(AddProduct.brand)
async def msg_ap_brand(message: Message, state: FSMContext):
    d = (await state.get_data()).get("ap", {})
    d["brand"] = message.text.strip()
    await state.update_data(ap=d)
    await state.set_state(AddProduct.price)
    await message.answer("Цена (число):", reply_markup=admin_cancel_kb())


@router.message(AddProduct.price)
async def msg_ap_price(message: Message, state: FSMContext):
    try:
        price = float(message.text.strip().replace(" ", "").replace(",", "."))
    except ValueError:
        return await message.answer("❌ Введите число:")
    d = (await state.get_data()).get("ap", {})
    d["price"] = price
    await state.update_data(ap=d)
    await state.set_state(AddProduct.category)
    db = get_db_session()
    try:
        cats = db.query(Category).all()
        ct = "\n".join(f"<code>{c.id}</code>. {c.name}" for c in cats)
    finally:
        db.close()
    await message.answer(f"Категория (номер):\n\n{ct}", reply_markup=admin_cancel_kb())


@router.message(AddProduct.category)
async def msg_ap_cat(message: Message, state: FSMContext):
    try:
        cid = int(message.text.strip())
    except ValueError:
        return await message.answer("❌ Введите номер:")
    d = (await state.get_data()).get("ap", {})
    d["cat"] = cid
    await state.update_data(ap=d)
    await state.set_state(AddProduct.description)
    await message.answer("Описание (или <code>-</code> чтобы пропустить):", reply_markup=admin_cancel_kb())


@router.message(AddProduct.description)
async def msg_ap_desc(message: Message, state: FSMContext):
    desc = message.text.strip()
    if desc == "-":
        desc = ""
    d = (await state.get_data()).get("ap", {})
    sku = f"{d.get('brand', 'x').lower().replace(' ', '-')}-{uuid.uuid4().hex[:6]}"
    db = get_db_session()
    try:
        p = Product(
            sku=sku, brand=d.get("brand", ""), model="", name=d.get("name", ""),
            description=desc, price=d.get("price", 0), category_id=d.get("cat", 1),
        )
        db.add(p)
        db.commit()
        await message.answer(
            f"✅ <b>Товар добавлен!</b>\n\n"
            f"<b>{p.brand} {p.name}</b>\n"
            f"Цена: {_fmt(p.price)} ₽\nSKU: <code>{sku}</code>",
            reply_markup=admin_menu_kb(),
        )
    finally:
        db.close()
    await state.clear()


# ── Admin orders ──────────────────────────────────────────────────────────

@router.callback_query(F.data.regexp(r"^adm:ords:\d+$"))
async def cb_orders(cb: CallbackQuery):
    if not _admin(cb.from_user.id):
        return await cb.answer("⛔", show_alert=True)
    await cb.answer()
    page = int(cb.data.split(":")[2])
    db = get_db_session()
    try:
        ords = db.query(Order).order_by(Order.created_at.desc()).all()
        if not ords:
            return await _edit(cb, "🛒 Заказов нет.", admin_menu_kb())
        await _edit(cb, f"🛒 <b>Заказы ({len(ords)}):</b>", admin_orders_kb(ords, page))
    finally:
        db.close()


@router.callback_query(F.data.regexp(r"^adm:o:\d+$"))
async def cb_order(cb: CallbackQuery):
    if not _admin(cb.from_user.id):
        return await cb.answer("⛔", show_alert=True)
    await cb.answer()
    oid = int(cb.data.split(":")[2])
    db = get_db_session()
    try:
        o = db.query(Order).get(oid)
        if not o:
            return await _edit(cb, "Не найден.", admin_menu_kb())
        await _edit(cb, _ord_text(o), admin_order_kb(o))
    finally:
        db.close()


@router.callback_query(F.data.startswith("adm:ost:"))
async def cb_order_status(cb: CallbackQuery):
    if not _admin(cb.from_user.id):
        return await cb.answer("⛔", show_alert=True)
    parts = cb.data.split(":")
    oid, ns = int(parts[2]), parts[3]
    db = get_db_session()
    try:
        o = db.query(Order).get(oid)
        if not o:
            return await cb.answer("Не найден", show_alert=True)
        o.status = ns
        db.commit()
        db.refresh(o)
        await cb.answer(STATUS_MAP.get(ns, ns), show_alert=True)
        await _edit(cb, _ord_text(o), admin_order_kb(o))
    finally:
        db.close()


@router.callback_query(F.data.startswith("adm:otrk:"))
async def cb_order_trk(cb: CallbackQuery, state: FSMContext):
    if not _admin(cb.from_user.id):
        return await cb.answer("⛔", show_alert=True)
    await cb.answer()
    oid = int(cb.data.split(":")[2])
    await state.update_data(trk_oid=oid)
    await state.set_state(TrackInput.number)
    await _edit(cb, "📦 Введите трек-номер:", admin_cancel_kb())


@router.message(TrackInput.number)
async def msg_track(message: Message, state: FSMContext):
    data = await state.get_data()
    oid = data.get("trk_oid")
    await state.clear()
    if not oid:
        return
    db = get_db_session()
    try:
        o = db.query(Order).get(oid)
        if not o:
            return await message.answer("Не найден.", reply_markup=admin_menu_kb())
        o.tracking_number = message.text.strip()
        db.commit()
        db.refresh(o)
        await message.answer(f"✅ Трек сохранён!\n\n{_ord_text(o)}", reply_markup=admin_order_kb(o))
    finally:
        db.close()


@router.callback_query(F.data.startswith("adm:odel:"))
async def cb_order_del(cb: CallbackQuery):
    if not _admin(cb.from_user.id):
        return await cb.answer("⛔", show_alert=True)
    await cb.answer()
    oid = int(cb.data.split(":")[2])
    db = get_db_session()
    try:
        o = db.query(Order).get(oid)
        if not o:
            return await _edit(cb, "Не найден.", admin_menu_kb())
        await _edit(cb, f"🗑 Удалить заказ <b>#{o.order_number}</b>?", admin_order_del_confirm_kb(oid))
    finally:
        db.close()


@router.callback_query(F.data.startswith("adm:odelok:"))
async def cb_order_delok(cb: CallbackQuery):
    if not _admin(cb.from_user.id):
        return await cb.answer("⛔", show_alert=True)
    await cb.answer()
    oid = int(cb.data.split(":")[2])
    db = get_db_session()
    try:
        o = db.query(Order).get(oid)
        if o:
            n = o.order_number
            db.delete(o)
            db.commit()
            await _edit(cb, f"✅ Заказ #{n} удалён.", admin_menu_kb())
        else:
            await _edit(cb, "Не найден.", admin_menu_kb())
    finally:
        db.close()
