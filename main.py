import asyncio
import logging
import os
from logging.handlers import RotatingFileHandler

import truststore

truststore.inject_into_ssl()

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import SimpleEventIsolation
import database
import premium_emoji
from blocked_middleware import BlockedUserMiddleware
from config import BOT_TOKEN, LOG_FILE_PATH
from fsm_storage import SQLiteStorage
from outgoing_format import OutgoingFormatMiddleware
from integrations.base import close_session

from admin import (
    blocklist,
    broadcasts,
    chats,
    games,
    gifts,
    logs,
    media,
    promo as admin_promo,
    settings as admin_settings,
    sponsors,
    statistics,
    tasks_panel,
    users as admin_users,
    withdrawals as admin_withdrawals,
)
from handlers import admin as admin_root, leaderboards, menu, profile, promo, referrals, start, tasks, withdrawals

os.makedirs(os.path.dirname(LOG_FILE_PATH) or ".", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        RotatingFileHandler(LOG_FILE_PATH, maxBytes=10 * 1024 * 1024, backupCount=1, encoding="utf-8"),
    ],
)
logger = logging.getLogger("main")


async def _fsm_cleanup_loop() -> None:
    # The bot can run for weeks without a restart, so startup alone isn't enough.
    while True:
        try:
            await database.fsm_cleanup()
        except Exception as exc:
            logger.warning("fsm cleanup failed: %s", exc)
        await asyncio.sleep(24 * 60 * 60)


async def main() -> None:
    await database.init_db()
    cleanup_task = asyncio.create_task(_fsm_cleanup_loop())
    premium_emoji.set_enabled(await database.get_setting_bool("premium_emoji_enabled", False))

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    bot.session.middleware(OutgoingFormatMiddleware())
    # Updates from the same user are handled one at a time: FSM reads/writes
    # now hit SQLite (they yield), so without this a double-tapped "confirm"
    # could pass the state check twice (two withdrawals, two gifts, ...).
    dp = Dispatcher(storage=SQLiteStorage(), events_isolation=SimpleEventIsolation())
    dp.message.outer_middleware(BlockedUserMiddleware())
    dp.callback_query.outer_middleware(BlockedUserMiddleware())

    # Admin routers first so specific admin-only handlers (e.g. "+мишка") take priority.
    dp.include_router(admin_root.router)
    dp.include_router(statistics.router)
    dp.include_router(admin_users.router)
    dp.include_router(admin_promo.router)
    dp.include_router(tasks_panel.router)
    dp.include_router(games.router)
    dp.include_router(admin_settings.router)
    dp.include_router(media.router)
    dp.include_router(sponsors.router)
    dp.include_router(blocklist.router)
    dp.include_router(gifts.router)
    dp.include_router(chats.router)
    dp.include_router(logs.router)
    dp.include_router(broadcasts.router)
    dp.include_router(admin_withdrawals.router)

    # User-facing routers.
    dp.include_router(start.router)
    dp.include_router(tasks.router)
    dp.include_router(profile.router)
    dp.include_router(promo.router)
    dp.include_router(referrals.router)
    dp.include_router(withdrawals.router)
    dp.include_router(leaderboards.router)
    dp.include_router(menu.router)

    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        cleanup_task.cancel()
        await close_session()
        await bot.session.close()
        await database.close_db()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped")
