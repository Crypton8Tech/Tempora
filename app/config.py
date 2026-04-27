"""Конфигурация веб-приложения TemporaShop."""

import os
from dotenv import load_dotenv

load_dotenv()


def _env_bool(name: str, default: bool) -> bool:
    # Преобразует строковое значение из env в булевый флаг.
    # Пример: "true", "1", "yes" -> True.
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    # Публичный username бота, который показывается на сайте.
    BOT_USERNAME: str = os.getenv("BOT_USERNAME", "TemporaShopBot")

    # Основной секрет для подписи сессий и токенов.
    SECRET_KEY: str = os.getenv("SECRET_KEY", "change-me")

    # Логин/пароль админ-панели.
    ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "admin123")

    # Базовый URL сайта для callback-ов и ссылок.
    SITE_URL: str = os.getenv("SITE_URL", "http://localhost:8000")

    # Строка подключения к базе данных.
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./data/tempora.db")

    # Физический путь, где хранятся загруженные изображения товаров.
    UPLOAD_DIR: str = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "uploads")

    # Ключи платёжных провайдеров.
    STRIPE_PUBLIC_KEY: str = os.getenv("STRIPE_PUBLIC_KEY", "")
    STRIPE_SECRET_KEY: str = os.getenv("STRIPE_SECRET_KEY", "")
    STRIPE_WEBHOOK_SECRET: str = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    CSSCAPITAL_API_KEY: str = os.getenv("CSSCAPITAL_API_KEY", "api_gf3Bi3tt9gZHBCe5")

    # Необязательный ключ для AI-интеграции.
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")

    # Включает флаг Secure у cookie в production по HTTPS.
    SESSION_COOKIE_SECURE: bool = _env_bool("SESSION_COOKIE_SECURE", False)


settings = Settings()
