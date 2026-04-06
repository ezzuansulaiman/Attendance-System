from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Iterable, Optional, Sequence

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from bot.keyboards import worker_menu_keyboard
from bot.messages import build_attendance_reminder_text
from config import Settings, get_settings
from models import session_scope
from models.models import Site
from services.site_service import list_sites

logger = logging.getLogger(__name__)

REMINDER_GRACE_PERIOD = timedelta(minutes=10)
REMINDER_POLL_INTERVAL_SECONDS = 30
CHAT_REFRESH_INTERVAL = timedelta(minutes=5)


@dataclass(frozen=True)
class ReminderSlot:
    key: str
    trigger_time: time


def build_reminder_slots(settings: Settings) -> tuple[ReminderSlot, ...]:
    return (
        ReminderSlot(key="checkin", trigger_time=settings.attendance_checkin_reminder_time),
        ReminderSlot(key="checkout", trigger_time=settings.attendance_checkout_reminder_time),
    )


def is_workday(target_date: date, workdays: tuple[int, ...]) -> bool:
    return target_date.weekday() in workdays


def reminder_token(*, target_date: date, slot_key: str, chat_id: int) -> str:
    return f"{target_date.isoformat()}:{slot_key}:{chat_id}"


def extract_reminder_chat_ids(sites: Sequence[Site], fallback_group_id: Optional[int]) -> tuple[int, ...]:
    chat_ids: set[int] = set()
    for site in sites:
        if not site.is_active:
            continue
        if site.telegram_group_id is not None:
            chat_ids.add(site.telegram_group_id)
            continue
        if fallback_group_id is not None:
            chat_ids.add(fallback_group_id)
    if not chat_ids and fallback_group_id is not None:
        chat_ids.add(fallback_group_id)
    return tuple(sorted(chat_ids))


def due_reminder_targets(
    *,
    now: datetime,
    slots: Sequence[ReminderSlot],
    workdays: tuple[int, ...],
    chat_ids: Iterable[int],
    sent_tokens: set[str],
    grace_period: timedelta = REMINDER_GRACE_PERIOD,
) -> list[tuple[ReminderSlot, int]]:
    if not is_workday(now.date(), workdays):
        return []

    due: list[tuple[ReminderSlot, int]] = []
    for slot in slots:
        scheduled_at = datetime.combine(now.date(), slot.trigger_time, tzinfo=now.tzinfo)
        if now < scheduled_at or now >= scheduled_at + grace_period:
            continue
        for chat_id in chat_ids:
            token = reminder_token(target_date=now.date(), slot_key=slot.key, chat_id=chat_id)
            if token in sent_tokens:
                continue
            due.append((slot, chat_id))
    return due


async def resolve_reminder_chat_ids(settings: Settings) -> tuple[int, ...]:
    async with session_scope() as session:
        sites = await list_sites(session, active_only=True)
    return extract_reminder_chat_ids(sites, settings.group_id)


async def run_attendance_reminder_loop(bot: Bot) -> None:
    settings = get_settings()
    if not settings.attendance_reminders_enabled:
        logger.info("Attendance reminders are disabled.")
        return

    slots = build_reminder_slots(settings)
    sent_tokens: set[str] = set()
    cached_chat_ids: tuple[int, ...] = ()
    next_chat_refresh_at: Optional[datetime] = None

    logger.info(
        "Attendance reminders enabled for workdays %s at %s and %s.",
        settings.attendance_reminder_workdays,
        settings.attendance_checkin_reminder_time.strftime("%H:%M"),
        settings.attendance_checkout_reminder_time.strftime("%H:%M"),
    )

    while True:
        now = datetime.now(settings.local_timezone)
        today_prefix = f"{now.date().isoformat()}:"
        sent_tokens = {token for token in sent_tokens if token.startswith(today_prefix)}

        if next_chat_refresh_at is None or now >= next_chat_refresh_at:
            try:
                cached_chat_ids = await resolve_reminder_chat_ids(settings)
            except Exception:
                logger.exception("Failed to refresh reminder chat targets.")
                cached_chat_ids = ()
            next_chat_refresh_at = now + CHAT_REFRESH_INTERVAL

        for slot, chat_id in due_reminder_targets(
            now=now,
            slots=slots,
            workdays=settings.attendance_reminder_workdays,
            chat_ids=cached_chat_ids,
            sent_tokens=sent_tokens,
        ):
            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=build_attendance_reminder_text(slot.key),
                    reply_markup=worker_menu_keyboard(),
                )
            except TelegramAPIError:
                logger.exception("Failed to send %s attendance reminder to chat %s.", slot.key, chat_id)
                continue
            sent_tokens.add(reminder_token(target_date=now.date(), slot_key=slot.key, chat_id=chat_id))

        await asyncio.sleep(REMINDER_POLL_INTERVAL_SECONDS)
