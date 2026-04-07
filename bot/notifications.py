from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.keyboards import leave_review_keyboard
from bot.messages import build_attendance_sync_text, build_leave_review_text, build_leave_summary_text
from config import get_settings
from models import session_scope
from services.leave_service import get_leave_request

logger = logging.getLogger(__name__)


async def send_leave_request_to_admins(bot: Bot, leave_request_id: int) -> None:
    settings = get_settings()
    async with session_scope() as session:
        leave_request = await get_leave_request(session, leave_request_id)
        if not leave_request:
            return

        text = build_leave_summary_text(
            leave_request.id,
            leave_request.worker.full_name,
            leave_request.leave_type,
            leave_request.start_date,
            leave_request.end_date,
            leave_request.reason,
        )

        for admin_id in settings.admin_ids:
            try:
                if leave_request.telegram_file_id:
                    await bot.send_photo(
                        chat_id=admin_id,
                        photo=leave_request.telegram_file_id,
                        caption=text,
                        reply_markup=leave_review_keyboard(leave_request.id),
                    )
                else:
                    await bot.send_message(
                        chat_id=admin_id,
                        text=text,
                        reply_markup=leave_review_keyboard(leave_request.id),
                    )
            except Exception:
                logger.exception("Failed to send leave request %s to admin %s.", leave_request.id, admin_id)


async def send_leave_review_to_worker(bot: Bot, leave_request_id: int) -> None:
    async with session_scope() as session:
        leave_request = await get_leave_request(session, leave_request_id)
        if not leave_request:
            return

        try:
            await bot.send_message(
                chat_id=leave_request.worker.telegram_user_id,
                text=build_leave_review_text(
                    leave_request.id,
                    leave_request.leave_type,
                    leave_request.start_date,
                    leave_request.end_date,
                    leave_request.status,
                    leave_request.review_notes,
                ),
            )
        except Exception:
            logger.exception("Failed to send reviewed leave notification for request %s.", leave_request.id)


async def send_leave_review_to_worker_via_configured_bot(leave_request_id: int) -> bool:
    settings = get_settings()
    if not settings.bot_enabled:
        return False

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    try:
        await send_leave_review_to_worker(bot, leave_request_id)
        return True
    finally:
        await bot.session.close()


async def send_attendance_sync_to_worker(
    bot: Bot,
    *,
    worker_telegram_id: int,
    attendance_date,
    check_in_at,
    check_out_at,
    notes,
    action: str,
) -> None:
    try:
        await bot.send_message(
            chat_id=worker_telegram_id,
            text=build_attendance_sync_text(
                attendance_date=attendance_date,
                check_in_at=check_in_at,
                check_out_at=check_out_at,
                notes=notes,
                action=action,
            ),
        )
    except Exception:
        logger.exception("Failed to send attendance sync notification to worker %s.", worker_telegram_id)


async def send_attendance_sync_to_worker_via_configured_bot(
    *,
    worker_telegram_id: int,
    attendance_date,
    check_in_at,
    check_out_at,
    notes,
    action: str,
) -> bool:
    settings = get_settings()
    if not settings.bot_enabled:
        return False

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    try:
        await send_attendance_sync_to_worker(
            bot,
            worker_telegram_id=worker_telegram_id,
            attendance_date=attendance_date,
            check_in_at=check_in_at,
            check_out_at=check_out_at,
            notes=notes,
            action=action,
        )
        return True
    finally:
        await bot.session.close()
