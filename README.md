# TemporaShop

Премиальный магазин часов, сумок и одежды.

## Технологии

- **Backend**: Python, FastAPI, SQLAlchemy
- **Frontend**: Jinja2, HTML/CSS/JS
- **Database**: SQLite

## Установка

```bash
# 1. Установить зависимости
pip install -r requirements.txt

# 2. Настроить .env (скопировать из .env.example)
cp .env.example .env

# 3. Заполнить базу данных
python run.py seed

# 4. Запустить
python run.py web   # http://localhost:8000
python run.py       # то же самое
```

## Структура проекта

```
├── app/                    # Web application (FastAPI)
│   ├── main.py            # FastAPI entry point
│   ├── config.py          # Settings from .env
│   ├── database.py        # SQLAlchemy setup
│   ├── models.py          # ORM models
│   ├── auth.py            # Auth helpers
│   ├── routers/           # Route handlers
│   │   ├── pages.py       # Public pages
│   │   ├── auth.py        # Login/register
│   │   ├── api.py         # Cart/checkout API
│   │   └── admin.py       # Admin panel
│   ├── static/            # CSS, JS, images
│   └── templates/         # Jinja2 templates
├── data/                  # SQLite database
├── seed_data.py          # Database seeder
├── run.py                # Entry point
└── requirements.txt
```

## Админ-панель

- http://localhost:8000/admin (логин/пароль из .env)

## TODO

- [ ] Интеграция оплаты (Stripe/YooKassa)
- [ ] Email-верификация
