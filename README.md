# TemporaShop

Премиальный магазин часов, сумок и одежды с веб-сайтом и Telegram-ботом.

## Технологии

- **Backend**: Python, FastAPI, SQLAlchemy
- **Frontend**: Jinja2, HTML/CSS/JS
- **Database**: SQLite (общая для сайта и бота)
- **Bot**: python-telegram-bot

## Установка

```bash
# 1. Установить зависимости
pip install -r requirements.txt

# 2. Настроить .env (скопировать из .env.example)
cp .env.example .env
# Отредактировать .env — указать TELEGRAM_BOT_TOKEN и BOT_ADMIN_IDS

# 3. Заполнить базу данных
python run.py seed

# 4. Запустить
python run.py web   # только сайт (http://localhost:8000)
python run.py bot   # только бот
python run.py all   # сайт + бот
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
├── bot/                   # Telegram bot
│   ├── main.py           # Bot entry point
│   ├── keyboards.py      # Keyboard layouts
│   └── handlers/         # Message/callback handlers
├── data/                  # SQLite database
├── seed_data.py          # Database seeder
├── run.py                # Entry point
└── requirements.txt
```

## Админ-панель

- **Сайт**: http://localhost:8000/admin (логин/пароль из .env)
- **Бот**: команда `/admin` (для ID из BOT_ADMIN_IDS)

## TODO

- [ ] Интеграция оплаты (Stripe/YooKassa)
- [ ] Email-верификация
- [ ] Уведомления о заказах в Telegram
