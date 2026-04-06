from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.bot_handlers import router, set_bot_commands
from config import get_settings

logger = logging.getLogger(__name__)


def build_dispatcher() -> Dispatcher:
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.include_router(router)
    return dispatcher


async def run_bot_polling() -> None:
    settings = get_settings()
    if not settings.bot_enabled:
        logger.warning("BOT_TOKEN is not configured. Telegram bot polling is disabled.")
        while True:
            await asyncio.sleep(3600)

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = build_dispatcher()

    await set_bot_commands(bot)
    try:
        await dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())
    finally:
        await bot.session.close()
