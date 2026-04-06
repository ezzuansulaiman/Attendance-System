from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.bot_handlers import router, set_bot_commands
from bot.reminders import run_attendance_reminder_loop
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
    reminder_task = asyncio.create_task(run_attendance_reminder_loop(bot), name="attendance-reminders")

    await set_bot_commands(bot)
    try:
        await dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())
    finally:
        reminder_task.cancel()
        await asyncio.gather(reminder_task, return_exceptions=True)
        await bot.session.close()
