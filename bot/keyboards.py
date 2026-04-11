"""Inline keyboards for TemporaShop bot (aiogram 3)."""

from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

STATUS_EMOJI = {"pending": "⏳", "paid": "💳", "shipped": "🚚", "delivered": "✅", "cancelled": "❌"}
CAT_EMOJI = {"watches": "⌚", "bags": "👜", "clothing": "👔", "shoes": "👟", "accessories": "💍"}


def _price(v: float) -> str:
    return f"{v:,.0f}".replace(",", " ")


# ── Main ──────────────────────────────────────────────────────────────────

def main_menu_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🛍 Каталог", callback_data="catalog"))
    b.row(
        InlineKeyboardButton(text="🛒 Корзина", callback_data="cart"),
        InlineKeyboardButton(text="📦 Заказы", callback_data="orders"),
    )
    b.row(
        InlineKeyboardButton(text="📍 Отследить", callback_data="track"),
        InlineKeyboardButton(text="💬 Помощь", callback_data="help"),
    )
    b.row(InlineKeyboardButton(text="🌐 Сайт", callback_data="site"))
    return b.as_markup()


# ── Catalog ───────────────────────────────────────────────────────────────

def categories_kb(categories, counts=None) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for c in categories:
        e = CAT_EMOJI.get(c.slug, "📦")
        n = f" ({counts[c.id]})" if counts and c.id in counts else ""
        b.row(InlineKeyboardButton(text=f"{e} {c.name}{n}", callback_data=f"cat:{c.slug}"))
    b.row(InlineKeyboardButton(text="📋 Все товары", callback_data="cat:all"))
    b.row(
        InlineKeyboardButton(text="🔍 Поиск", callback_data="search"),
        InlineKeyboardButton(text="💰 По цене", callback_data="price_filter"),
    )
    b.row(InlineKeyboardButton(text="🔙 Главное меню", callback_data="main"))
    return b.as_markup()


def product_card_kb(product, idx: int, total: int, slug: str, in_cart=False) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    nav = []
    if idx > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"page:{slug}:{idx - 1}"))
    nav.append(InlineKeyboardButton(text=f"{idx + 1}/{total}", callback_data="noop"))
    if idx < total - 1:
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"page:{slug}:{idx + 1}"))
    b.row(*nav)

    if in_cart:
        b.row(InlineKeyboardButton(text="✅ В корзине", callback_data="noop"))
    else:
        b.row(InlineKeyboardButton(text="🛒 В корзину", callback_data=f"add:{product.id}:{slug}:{idx}"))

    b.row(InlineKeyboardButton(text="📄 Подробнее", callback_data=f"detail:{product.id}:{slug}:{idx}"))
    b.row(
        InlineKeyboardButton(text="🔙 Категории", callback_data="catalog"),
        InlineKeyboardButton(text="🏠 Меню", callback_data="main"),
    )
    return b.as_markup()


def product_detail_kb(product, slug: str, idx: int, in_cart=False) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if in_cart:
        b.row(InlineKeyboardButton(text="✅ В корзине", callback_data="noop"))
    else:
        b.row(InlineKeyboardButton(text="🛒 В корзину", callback_data=f"add:{product.id}:{slug}:{idx}"))
    b.row(InlineKeyboardButton(text="🔙 Назад к списку", callback_data=f"page:{slug}:{idx}"))
    b.row(InlineKeyboardButton(text="🏠 Меню", callback_data="main"))
    return b.as_markup()


def price_filter_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="До 50 тыс", callback_data="fp:0:50000"),
        InlineKeyboardButton(text="50‑150 тыс", callback_data="fp:50000:150000"),
    )
    b.row(
        InlineKeyboardButton(text="150‑500 тыс", callback_data="fp:150000:500000"),
        InlineKeyboardButton(text="500 тыс+", callback_data="fp:500000:0"),
    )
    b.row(InlineKeyboardButton(text="🔙 Категории", callback_data="catalog"))
    return b.as_markup()


def search_cancel_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="❌ Отмена", callback_data="catalog"))
    return b.as_markup()


# ── Cart ──────────────────────────────────────────────────────────────────

def cart_kb(items) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for it in items:
        if not it.product:
            continue
        nm = it.product.name[:25]
        b.row(
            InlineKeyboardButton(text="➖", callback_data=f"cq:{it.id}:-1"),
            InlineKeyboardButton(text=f"{nm} ×{it.quantity}", callback_data="noop"),
            InlineKeyboardButton(text="➕", callback_data=f"cq:{it.id}:1"),
        )
        b.row(InlineKeyboardButton(text=f"❌ Убрать {nm}", callback_data=f"cdel:{it.id}"))
    if items:
        b.row(InlineKeyboardButton(text="🗑 Очистить", callback_data="cclear"))
        b.row(InlineKeyboardButton(text="✅ Оформить заказ", callback_data="co:start"))
    b.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="main"))
    return b.as_markup()


def checkout_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="📍 Адрес", callback_data="co:address"))
    b.row(InlineKeyboardButton(text="📞 Телефон", callback_data="co:phone"))
    b.row(InlineKeyboardButton(text="📝 Комментарий", callback_data="co:note"))
    b.row(InlineKeyboardButton(text="✅ Подтвердить заказ", callback_data="co:confirm"))
    b.row(InlineKeyboardButton(text="🔙 Корзина", callback_data="cart"))
    return b.as_markup()


def checkout_back_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🔙 К оформлению", callback_data="co:start"))
    return b.as_markup()


# ── Orders ────────────────────────────────────────────────────────────────

def orders_kb(orders, page=0, per_page=5) -> InlineKeyboardMarkup:
    s, e = page * per_page, (page + 1) * per_page
    tp = max(1, -(-len(orders) // per_page))
    b = InlineKeyboardBuilder()
    for o in orders[s:e]:
        em = STATUS_EMOJI.get(o.status, "📦")
        b.row(InlineKeyboardButton(
            text=f"{em} #{o.order_number[-8:]} — {_price(o.total)} ₽",
            callback_data=f"ord:{o.id}",
        ))
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"ordp:{page - 1}"))
    if tp > 1:
        nav.append(InlineKeyboardButton(text=f"{page + 1}/{tp}", callback_data="noop"))
    if page < tp - 1:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"ordp:{page + 1}"))
    if nav:
        b.row(*nav)
    b.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="main"))
    return b.as_markup()


def order_detail_kb(order) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if order.status == "pending":
        b.row(InlineKeyboardButton(text="❌ Отменить", callback_data=f"ordcancel:{order.id}"))
    b.row(InlineKeyboardButton(text="🔙 Заказы", callback_data="orders"))
    b.row(InlineKeyboardButton(text="🏠 Меню", callback_data="main"))
    return b.as_markup()


def track_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🔙 Главное меню", callback_data="main"))
    return b.as_markup()


def track_result_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🔍 Другой заказ", callback_data="track"))
    b.row(InlineKeyboardButton(text="🏠 Меню", callback_data="main"))
    return b.as_markup()


def help_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="❓ FAQ", callback_data="faq"))
    b.row(InlineKeyboardButton(text="📧 Поддержка", callback_data="contact"))
    b.row(InlineKeyboardButton(text="🌐 Сайт", callback_data="site"))
    b.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="main"))
    return b.as_markup()


def faq_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🔙 Помощь", callback_data="help"))
    b.row(InlineKeyboardButton(text="🏠 Меню", callback_data="main"))
    return b.as_markup()


def site_kb(url: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if url.startswith("https://"):
        b.row(InlineKeyboardButton(text="🌐 Открыть сайт", url=url))
    b.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="main"))
    return b.as_markup()


# ── Admin ─────────────────────────────────────────────────────────────────

def admin_menu_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="📊 Статистика", callback_data="adm:stats"))
    b.row(InlineKeyboardButton(text="📦 Товары", callback_data="adm:prods:0"))
    b.row(InlineKeyboardButton(text="🛒 Заказы", callback_data="adm:ords:0"))
    b.row(InlineKeyboardButton(text="➕ Добавить товар", callback_data="adm:addprod"))
    b.row(InlineKeyboardButton(text="🏠 Главное меню", callback_data="main"))
    return b.as_markup()


def admin_products_kb(products, page=0, per_page=8) -> InlineKeyboardMarkup:
    s, e = page * per_page, (page + 1) * per_page
    tp = max(1, -(-len(products) // per_page))
    b = InlineKeyboardBuilder()
    for p in products[s:e]:
        st = "✅" if p.is_active else "⬜"
        b.row(InlineKeyboardButton(
            text=f"{st} {p.brand} {p.name[:20]} — {_price(p.price)}₽",
            callback_data=f"adm:p:{p.id}",
        ))
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"adm:prods:{page - 1}"))
    if tp > 1:
        nav.append(InlineKeyboardButton(text=f"{page + 1}/{tp}", callback_data="noop"))
    if page < tp - 1:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"adm:prods:{page + 1}"))
    if nav:
        b.row(*nav)
    b.row(InlineKeyboardButton(text="➕ Добавить товар", callback_data="adm:addprod"))
    b.row(InlineKeyboardButton(text="🔙 Админ", callback_data="adm:menu"))
    return b.as_markup()


def admin_product_kb(product) -> InlineKeyboardMarkup:
    tog = "🔴 Скрыть" if product.is_active else "🟢 Включить"
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text=tog, callback_data=f"adm:tog:{product.id}"),
        InlineKeyboardButton(text="🗑 Удалить", callback_data=f"adm:del:{product.id}"),
    )
    b.row(InlineKeyboardButton(text="✏️ Цену", callback_data=f"adm:ed:price:{product.id}"))
    b.row(InlineKeyboardButton(text="✏️ Описание", callback_data=f"adm:ed:desc:{product.id}"))
    b.row(InlineKeyboardButton(text="🔙 Товары", callback_data="adm:prods:0"))
    b.row(InlineKeyboardButton(text="🔙 Админ", callback_data="adm:menu"))
    return b.as_markup()


def admin_del_confirm_kb(pid: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="✅ Да", callback_data=f"adm:delok:{pid}"),
        InlineKeyboardButton(text="❌ Нет", callback_data=f"adm:p:{pid}"),
    )
    return b.as_markup()


def admin_orders_kb(orders, page=0, per_page=8) -> InlineKeyboardMarkup:
    s, e = page * per_page, (page + 1) * per_page
    tp = max(1, -(-len(orders) // per_page))
    b = InlineKeyboardBuilder()
    for o in orders[s:e]:
        em = STATUS_EMOJI.get(o.status, "📦")
        dt = o.created_at.strftime("%d.%m") if o.created_at else ""
        b.row(InlineKeyboardButton(
            text=f"{em} #{o.order_number[-8:]} {dt} — {_price(o.total)}₽",
            callback_data=f"adm:o:{o.id}",
        ))
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="◀️", callback_data=f"adm:ords:{page - 1}"))
    if tp > 1:
        nav.append(InlineKeyboardButton(text=f"{page + 1}/{tp}", callback_data="noop"))
    if page < tp - 1:
        nav.append(InlineKeyboardButton(text="▶️", callback_data=f"adm:ords:{page + 1}"))
    if nav:
        b.row(*nav)
    b.row(InlineKeyboardButton(text="🔙 Админ", callback_data="adm:menu"))
    return b.as_markup()


def admin_order_kb(order) -> InlineKeyboardMarkup:
    labels = {"pending": "⏳", "paid": "💳", "shipped": "🚚", "delivered": "✅", "cancelled": "❌"}
    b = InlineKeyboardBuilder()
    row = []
    for s in ("pending", "paid", "shipped", "delivered", "cancelled"):
        if s != order.status:
            row.append(InlineKeyboardButton(text=labels[s], callback_data=f"adm:ost:{order.id}:{s}"))
            if len(row) == 3:
                b.row(*row)
                row = []
    if row:
        b.row(*row)
    b.row(InlineKeyboardButton(text="📦 Трек-номер", callback_data=f"adm:otrk:{order.id}"))
    b.row(InlineKeyboardButton(text="🗑 Удалить", callback_data=f"adm:odel:{order.id}"))
    b.row(InlineKeyboardButton(text="🔙 Заказы", callback_data="adm:ords:0"))
    b.row(InlineKeyboardButton(text="🔙 Админ", callback_data="adm:menu"))
    return b.as_markup()


def admin_order_del_confirm_kb(oid: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="✅ Да", callback_data=f"adm:odelok:{oid}"),
        InlineKeyboardButton(text="❌ Нет", callback_data=f"adm:o:{oid}"),
    )
    return b.as_markup()


def admin_cancel_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="❌ Отмена", callback_data="adm:menu"))
    return b.as_markup()
