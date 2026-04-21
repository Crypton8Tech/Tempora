"""TemporaShop web application configuration."""

import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    BOT_USERNAME: str = os.getenv("BOT_USERNAME", "TemporaShopBot")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "change-me")
    ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "admin123")
    SITE_URL: str = os.getenv("SITE_URL", "http://localhost:8000")
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./data/tempora.db")
    UPLOAD_DIR: str = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "uploads")
    STRIPE_PUBLIC_KEY: str = os.getenv("STRIPE_PUBLIC_KEY", "")
    STRIPE_SECRET_KEY: str = os.getenv("STRIPE_SECRET_KEY", "")
    STRIPE_WEBHOOK_SECRET: str = os.getenv("STRIPE_WEBHOOK_SECRET", "")
    CSSCAPITAL_API_KEY: str = os.getenv("CSSCAPITAL_API_KEY", "api_gf3Bi3tt9gZHBCe5")
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")


settings = Settings()
