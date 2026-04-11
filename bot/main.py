"""Bot entry point — creates Bot, Dispatcher, includes routers."""

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from app.config import settings
from app.database import init_db

from bot.handlers import admin, start, catalog, cart, orders

log = logging.getLogger(__name__)


def create_bot() -> Bot:
    return Bot(
        token=settings.TELEGRAM_BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def create_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    # admin first — its FSM states must match before generic handlers
    dp.include_router(admin.router)
    dp.include_router(start.router)
    dp.include_router(catalog.router)
    dp.include_router(cart.router)
    dp.include_router(orders.router)
    return dp


async def run_bot_async():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    init_db()
    bot = create_bot()
    dp = create_dispatcher()
    await bot.delete_webhook(drop_pending_updates=True)
    log.info("Bot started polling")
    await dp.start_polling(bot, drop_pending_updates=True)


def run_bot():
    asyncio.run(run_bot_async())
