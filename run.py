"""Run both the web server and Telegram bot."""

import sys
import threading
import asyncio
import uvicorn

from app.config import settings


def run_web():
    """Run FastAPI web server."""
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)


def run_bot():
    """Run Telegram bot (blocking)."""
    from bot.main import run_bot as _run_bot
    _run_bot()


def run_bot_in_thread():
    """Run the Telegram bot in a separate thread with its own event loop."""
    def _bot_thread():
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        import logging
        logger = logging.getLogger("bot.runner")
        logger.info("Starting Telegram bot in background thread...")

        from bot.main import create_bot, create_dispatcher
        from app.database import init_db

        init_db()
        bot = create_bot()
        dp = create_dispatcher()

        loop.run_until_complete(bot.delete_webhook(drop_pending_updates=True))
        loop.run_until_complete(dp.start_polling(bot, drop_pending_updates=True, handle_signals=False))

    t = threading.Thread(target=_bot_thread, daemon=True)
    t.start()
    return t


if __name__ == "__main__":
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "web":
            print("🌐 Starting web server on http://localhost:8000")
            run_web()
        elif cmd == "bot":
            print("🤖 Starting Telegram bot...")
            run_bot()
        elif cmd == "seed":
            from seed_data import seed
            seed()
        elif cmd == "all":
            print("🚀 Starting web server + Telegram bot...")
            run_bot_in_thread()
            run_web()  # Web runs in main thread (blocking)
        else:
            print("Usage: python run.py [web|bot|seed|all]")
    else:
        print("Usage: python run.py [web|bot|seed|all]")
        print()
        print("  web  — Start web server only")
        print("  bot  — Start Telegram bot only")
        print("  seed — Seed database with sample products")
        print("  all  — Start both web server and bot")
