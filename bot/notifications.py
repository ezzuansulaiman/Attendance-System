from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.messages import build_public_holiday_sync_text
from bot.reminders import extract_reminder_chat_ids
from bot.keyboards import leave_review_keyboard
from bot.messages import build_attendance_sync_text, build_leave_review_text, build_leave_summary_text
from config import get_settings
from models import session_scope
from services.leave_service import get_leave_request, leave_requires_photo
from services.site_service import get_site_by_id, list_sites

logger = logging.getLogger(__name__)


def _leave_group_chat_id(leave_request: object, fallback_group_id: int | None) -> int | None:
    worker = getattr(leave_request, "worker", None)
    site = getattr(worker, "site", None)
    site_group_id = getattr(site, "telegram_group_id", None)
    if site_group_id is not None:
        return int(site_group_id)
    return fallback_group_id


async def _send_leave_request_to_group(bot: Bot, *, leave_request: object, text: str, fallback_group_id: int | None) -> None:
    if not leave_requires_photo(getattr(leave_request, "leave_type", "")):
        return

    group_chat_id = _leave_group_chat_id(leave_request, fallback_group_id)
    telegram_file_id = getattr(leave_request, "telegram_file_id", None)
    if group_chat_id is None or not telegram_file_id:
        return

    group_text = (
        "<b>Makluman Permohonan Cuti</b>\n"
        "Bukti sokongan dilampirkan di sini bersama alasan.\n\n"
        f"{text}"
    )
    try:
        await bot.send_photo(
            chat_id=group_chat_id,
            photo=telegram_file_id,
            caption=group_text,
        )
    except Exception:
        logger.exception("Failed to send leave request %s to worker group %s.", getattr(leave_request, "id", "?"), group_chat_id)


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
            leave_request.day_portion,
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

        await _send_leave_request_to_group(
            bot,
            leave_request=leave_request,
            text=text,
            fallback_group_id=settings.group_id,
        )


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
                    leave_request.day_portion,
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


async def send_public_holiday_sync(
    bot: Bot,
    *,
    holiday_name: str,
    holiday_date,
    site_id,
    site_name,
    notes,
    action: str,
) -> None:
    settings = get_settings()
    async with session_scope() as session:
        chat_ids: tuple[int, ...]
        resolved_site_name = site_name
        if site_id is not None:
            site = await get_site_by_id(session, site_id)
            resolved_site_name = site.name if site else site_name
            if site and site.telegram_group_id is not None:
                chat_ids = (site.telegram_group_id,)
            elif settings.group_id is not None:
                chat_ids = (settings.group_id,)
            else:
                chat_ids = ()
        else:
            sites = await list_sites(session, active_only=True)
            chat_ids = extract_reminder_chat_ids(sites, settings.group_id)
            resolved_site_name = resolved_site_name or "Semua site"

    if not chat_ids:
        return

    text = build_public_holiday_sync_text(
        holiday_date=holiday_date,
        holiday_name=holiday_name,
        site_name=resolved_site_name,
        notes=notes,
        action=action,
    )
    for chat_id in chat_ids:
        try:
            await bot.send_message(chat_id=chat_id, text=text)
        except Exception:
            logger.exception("Failed to send public holiday sync to chat %s.", chat_id)


async def send_public_holiday_sync_via_configured_bot(
    *,
    holiday_name: str,
    holiday_date,
    site_id,
    site_name,
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
        await send_public_holiday_sync(
            bot,
            holiday_name=holiday_name,
            holiday_date=holiday_date,
            site_id=site_id,
            site_name=site_name,
            notes=notes,
            action=action,
        )
        return True
    finally:
        await bot.session.close()
