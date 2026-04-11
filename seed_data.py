"""Seed database with sample products (from temp_data_watch and additional demo data)."""

from app.database import init_db, get_db_session
from app.models import Category, Product, ProductImage


SAMPLE_PRODUCTS = [
    # ── Часы ──────────────────────────────────────────────────────────────
    {
        "category_slug": "watches",
        "sku": "rolex-day-date-001",
        "brand": "Rolex",
        "model": "Day-Date 36",
        "name": "Day-Date 36",
        "name_en": "Day-Date 36",
        "description": (
            "Rolex Day-Date — воплощение престижа и элегантности. "
            "Эти часы, впервые представленные в 1956 году, стали символом успеха и влияния.\n\n"
            "• Механизм: Calibre 3255, автоматический\n"
            "• Корпус: 36 мм, жёлтое золото 18 карат\n"
            "• Водонепроницаемость: 100 м\n"
            "• Браслет: President\n"
            "• Стекло: сапфировое с антибликовым покрытием"
        ),
        "description_en": (
            "Rolex Day-Date — the epitome of prestige and elegance. "
            "First introduced in 1956, these watches have become a symbol of success and influence.\n\n"
            "• Movement: Calibre 3255, automatic\n"
            "• Case: 36 mm, 18k yellow gold\n"
            "• Water resistance: 100 m\n"
            "• Bracelet: President\n"
            "• Crystal: sapphire with anti-reflective coating"
        ),
        "price": 4_250_000,
    },
    {
        "category_slug": "watches",
        "sku": "rolex-gmt-master-2-001",
        "brand": "Rolex",
        "model": "GMT-Master II",
        "name": "GMT-Master II «Pepsi»",
        "name_en": "GMT-Master II \u2018Pepsi\u2019",
        "description": (
            "Rolex GMT-Master II — легендарные часы путешественников. "
            "Двухцветный безель \u00abPepsi\u00bb в красно-синей гамме стал одним из самых узнаваемых дизайнов в часовой индустрии.\n\n"
            "• Механизм: Calibre 3285, автоподзавод\n"
            "• Корпус: 40 мм, Oystersteel\n"
            "• Безель: двунаправленный вращающийся, Cerachrom\n"
            "• Водонепроницаемость: 100 м\n"
            "• Функция двух часовых поясов"
        ),
        "description_en": (
            "Rolex GMT-Master II — legendary traveller\u2019s watch. "
            "The two-tone \u2018Pepsi\u2019 bezel in red-blue colorway is one of the most recognizable designs in watch-making.\n\n"
            "• Movement: Calibre 3285, self-winding\n"
            "• Case: 40 mm, Oystersteel\n"
            "• Bezel: bidirectional rotating, Cerachrom\n"
            "• Water resistance: 100 m\n"
            "• Dual time zone function"
        ),
        "price": 2_890_000,
    },
    {
        "category_slug": "watches",
        "sku": "rolex-submariner-001",
        "brand": "Rolex",
        "model": "Submariner Date",
        "name": "Submariner Date",
        "name_en": "Submariner Date",
        "description": (
            "Rolex Submariner — культовые дайверские часы, ставшие эталоном спортивной элегантности. "
            "Надёжные, точные, стильные.\n\n"
            "• Механизм: Calibre 3235, автоподзавод\n"
            "• Корпус: 41 мм, Oystersteel\n"
            "• Водонепроницаемость: 300 м\n"
            "• Безель: однонаправленный, Cerachrom\n"
            "• Запас хода: ~70 часов"
        ),
        "description_en": (
            "Rolex Submariner — iconic dive watch that became the benchmark for sporty elegance. "
            "Reliable, precise, stylish.\n\n"
            "• Movement: Calibre 3235, self-winding\n"
            "• Case: 41 mm, Oystersteel\n"
            "• Water resistance: 300 m\n"
            "• Bezel: unidirectional, Cerachrom\n"
            "• Power reserve: ~70 hours"
        ),
        "price": 1_750_000,
    },
    {
        "category_slug": "watches",
        "sku": "ap-royal-oak-001",
        "brand": "Audemars Piguet",
        "model": "Royal Oak",
        "name": "Royal Oak 41mm",
        "name_en": "Royal Oak 41mm",
        "description": (
            "Audemars Piguet Royal Oak — икона часового дизайна, созданная легендарным Джеральдом Джента.\n\n"
            "• Механизм: Calibre 4302, автоподзавод\n"
            "• Корпус: 41 мм, нержавеющая сталь\n"
            "• Циферблат: \u00abGrande Tapisserie\u00bb\n"
            "• Водонепроницаемость: 50 м"
        ),
        "description_en": (
            "Audemars Piguet Royal Oak — an icon of watch design, created by the legendary G\u00e9rald Genta.\n\n"
            "• Movement: Calibre 4302, self-winding\n"
            "• Case: 41 mm, stainless steel\n"
            "• Dial: \u2018Grande Tapisserie\u2019\n"
            "• Water resistance: 50 m"
        ),
        "price": 5_400_000,
    },
    {
        "category_slug": "watches",
        "sku": "patek-nautilus-001",
        "brand": "Patek Philippe",
        "model": "Nautilus 5711",
        "name": "Nautilus 5711/1A",
        "name_en": "Nautilus 5711/1A",
        "description": (
            "Patek Philippe Nautilus — одни из самых вожделенных спортивно-элегантных часов в мире.\n\n"
            "• Механизм: Calibre 26\u201130 S C, автоподзавод\n"
            "• Корпус: 40 мм, нержавеющая сталь\n"
            "• Запас хода: 45 часов\n"
            "• Водонепроницаемость: 120 м"
        ),
        "description_en": (
            "Patek Philippe Nautilus — one of the most coveted sports-elegant watches in the world.\n\n"
            "• Movement: Calibre 26\u201130 S C, self-winding\n"
            "• Case: 40 mm, stainless steel\n"
            "• Power reserve: 45 hours\n"
            "• Water resistance: 120 m"
        ),
        "price": 12_500_000,
    },

    # ── Сумки ─────────────────────────────────────────────────────────────
    {
        "category_slug": "bags",
        "sku": "hermes-birkin-001",
        "brand": "Hermès",
        "model": "Birkin 30",
        "name": "Birkin 30 Togo",
        "name_en": "Birkin 30 Togo",
        "description": (
            "Herm\u00e8s Birkin — самая знаменитая сумка в мире, символ роскоши и недоступности.\n\n"
            "• Размер: 30 см\n"
            "• Кожа: Togo (телячья, зернистая)\n"
            "• Фурнитура: палладий\n"
            "• Ручная работа французских мастеров"
        ),
        "description_en": (
            "Herm\u00e8s Birkin — the most famous bag in the world, a symbol of luxury and exclusivity.\n\n"
            "• Size: 30 cm\n"
            "• Leather: Togo (calf, grained)\n"
            "• Hardware: palladium\n"
            "• Handcrafted by French artisans"
        ),
        "price": 3_200_000,
    },
    {
        "category_slug": "bags",
        "sku": "chanel-classic-001",
        "brand": "Chanel",
        "model": "Classic Flap",
        "name": "Classic Flap Medium",
        "name_en": "Classic Flap Medium",
        "description": (
            "Chanel Classic Flap — вечная классика, созданная Карлом Лагерфельдом.\n\n"
            "• Стёганая кожа ягнёнка\n"
            "• Цепочка с кожаным переплётом\n"
            "• Замок CC turn-lock\n"
            "• Размер: Medium 25.5 см"
        ),
        "description_en": (
            "Chanel Classic Flap — timeless classic created by Karl Lagerfeld.\n\n"
            "• Quilted lambskin leather\n"
            "• Chain with leather interlace\n"
            "• CC turn-lock closure\n"
            "• Size: Medium 25.5 cm"
        ),
        "price": 1_450_000,
    },
    {
        "category_slug": "bags",
        "sku": "lv-neverfull-001",
        "brand": "Louis Vuitton",
        "model": "Neverfull MM",
        "name": "Neverfull MM Monogram",
        "name_en": "Neverfull MM Monogram",
        "description": (
            "Louis Vuitton Neverfull — универсальная и вместительная сумка с узнаваемым монограммом.\n\n"
            "• Канва Monogram с натуральной кожей\n"
            "• Размер: MM (31\u00d728\u00d714 см)\n"
            "• Съёмный внутренний чехол\n"
            "• Сделано во Франции"
        ),
        "description_en": (
            "Louis Vuitton Neverfull — versatile and spacious bag with the iconic monogram.\n\n"
            "• Monogram canvas with natural leather\n"
            "• Size: MM (31\u00d728\u00d714 cm)\n"
            "• Removable inner pouch\n"
            "• Made in France"
        ),
        "price": 280_000,
    },

    # ── Одежда ────────────────────────────────────────────────────────────
    {
        "category_slug": "clothing",
        "sku": "gucci-jacket-001",
        "brand": "Gucci",
        "model": "GG Monogram Jacket",
        "name": "Куртка GG Monogram",
        "name_en": "GG Monogram Jacket",
        "description": (
            "Gucci GG Monogram Jacket — стильная куртка с фирменным принтом дома Gucci.\n\n"
            "• Ткань: хлопок с принтом GG\n"
            "• Застёжка на молнию\n"
            "• Два боковых кармана\n"
            "• Сделано в Италии"
        ),
        "description_en": (
            "Gucci GG Monogram Jacket — a stylish jacket featuring the iconic Gucci print.\n\n"
            "• Fabric: cotton with GG print\n"
            "• Zip closure\n"
            "• Two side pockets\n"
            "• Made in Italy"
        ),
        "price": 340_000,
    },
    {
        "category_slug": "clothing",
        "sku": "balenciaga-hoodie-001",
        "brand": "Balenciaga",
        "model": "Logo Hoodie",
        "name": "Худи с логотипом",
        "name_en": "Logo Hoodie",
        "description": (
            "Balenciaga Logo Hoodie — оверсайз худи с минималистичным логотипом.\n\n"
            "• 100% хлопок\n"
            "• Оверсайз крой\n"
            "• Принт логотипа на груди\n"
            "• Размеры: S\u2013XL"
        ),
        "description_en": (
            "Balenciaga Logo Hoodie — oversized hoodie with minimalist logo.\n\n"
            "• 100% cotton\n"
            "• Oversized fit\n"
            "• Logo print on chest\n"
            "• Sizes: S\u2013XL"
        ),
        "price": 145_000,
    },
    {
        "category_slug": "clothing",
        "sku": "prada-shirt-001",
        "brand": "Prada",
        "model": "Re-Nylon Shirt",
        "name": "Рубашка Re-Nylon",
        "name_en": "Re-Nylon Shirt",
        "description": (
            "Prada Re-Nylon Shirt — рубашка из переработанного нейлона, сочетающая стиль и экологичность.\n\n"
            "• Переработанный нейлон ECONYL\u00ae\n"
            "• Треугольный логотип Prada\n"
            "• Сделано в Италии"
        ),
        "description_en": (
            "Prada Re-Nylon Shirt — a shirt made from recycled nylon, combining style and sustainability.\n\n"
            "• Recycled ECONYL\u00ae nylon\n"
            "• Prada triangle logo\n"
            "• Made in Italy"
        ),
        "price": 185_000,
    },
]


def seed():
    """Seed the database with sample data."""
    init_db()
    db = get_db_session()
    try:
        # Ensure categories exist
        for slug, name, name_en in [("watches", "Часы", "Watches"), ("bags", "Сумки", "Bags"), ("clothing", "Одежда", "Clothing")]:
            existing = db.query(Category).filter(Category.slug == slug).first()
            if not existing:
                db.add(Category(slug=slug, name=name, name_en=name_en))
            elif not existing.name_en:
                existing.name_en = name_en
        db.commit()

        # Add products
        added = 0
        for item in SAMPLE_PRODUCTS:
            existing = db.query(Product).filter(Product.sku == item["sku"]).first()
            if existing:
                continue

            cat = db.query(Category).filter(Category.slug == item["category_slug"]).first()
            if not cat:
                continue

            product = Product(
                sku=item["sku"],
                brand=item["brand"],
                model=item.get("model", ""),
                name=item["name"],
                name_en=item.get("name_en"),
                description=item["description"],
                description_en=item.get("description_en"),
                price=item["price"],
                category_id=cat.id,
                is_active=True,
            )
            db.add(product)
            added += 1

        db.commit()
        print(f"✅ Seeded {added} products (skipped existing)")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
