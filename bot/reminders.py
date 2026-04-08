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
from models.models import AttendanceRecord, Site, Worker
from services.attendance_service import list_active_workers, list_attendance_for_date
from services.leave_service import approved_leaves_in_range, leave_blocks_attendance
from services.public_holiday_service import list_public_holidays_in_range
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


def worker_reminder_chat_id(worker: Worker, fallback_group_id: Optional[int]) -> Optional[int]:
    if worker.site and worker.site.telegram_group_id is not None:
        return worker.site.telegram_group_id
    return fallback_group_id


def select_workers_for_chat(
    workers: Sequence[Worker],
    *,
    chat_id: int,
    fallback_group_id: Optional[int],
) -> list[Worker]:
    return [
        worker
        for worker in workers
        if worker_reminder_chat_id(worker, fallback_group_id) == chat_id
    ]


def pending_worker_names(
    *,
    reminder_type: str,
    workers: Sequence[Worker],
    attendance_lookup: dict[int, AttendanceRecord],
    approved_leave_worker_ids: set[int],
    public_holiday_worker_ids: set[int],
) -> list[str]:
    names: list[str] = []
    for worker in workers:
        if reminder_type == "checkin":
            if worker.id in approved_leave_worker_ids or worker.id in public_holiday_worker_ids:
                continue
            record = attendance_lookup.get(worker.id)
            if record and record.check_in_at:
                continue
            names.append(worker.full_name)
            continue

        if reminder_type == "checkout":
            record = attendance_lookup.get(worker.id)
            if not record or not record.check_in_at or record.check_out_at:
                continue
            names.append(worker.full_name)
            continue

        raise ValueError(f"Unsupported reminder type: {reminder_type}")
    return sorted(names)


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


def public_holiday_worker_ids_for_date(
    *,
    workers: Sequence[Worker],
    public_holidays: Sequence[object],
    target_date: date,
) -> set[int]:
    holiday_sites = {holiday.site_id for holiday in public_holidays if holiday.holiday_date == target_date}
    if None in holiday_sites:
        return {worker.id for worker in workers}
    worker_ids: set[int] = set()
    for worker in workers:
        if worker.site_id in holiday_sites:
            worker_ids.add(worker.id)
    return worker_ids


async def resolve_reminder_chat_ids(settings: Settings) -> tuple[int, ...]:
    async with session_scope() as session:
        sites = await list_sites(session, active_only=True)
    return extract_reminder_chat_ids(sites, settings.group_id)


async def pending_worker_names_for_chat(
    *,
    settings: Settings,
    chat_id: int,
    reminder_type: str,
    target_date: date,
) -> list[str]:
    async with session_scope() as session:
        workers = await list_active_workers(session)
        workers_for_chat = select_workers_for_chat(workers, chat_id=chat_id, fallback_group_id=settings.group_id)
        if not workers_for_chat:
            return []

        attendance_records = await list_attendance_for_date(session, attendance_date=target_date)
        attendance_lookup = {record.worker_id: record for record in attendance_records}
        approved_leave_worker_ids = {
            leave.worker_id
            for leave in await approved_leaves_in_range(session, start_date=target_date, end_date=target_date)
            if leave_blocks_attendance(leave)
        }
        public_holiday_worker_ids = public_holiday_worker_ids_for_date(
            workers=workers_for_chat,
            public_holidays=await list_public_holidays_in_range(session, start_date=target_date, end_date=target_date),
            target_date=target_date,
        )
    return pending_worker_names(
        reminder_type=reminder_type,
        workers=workers_for_chat,
        attendance_lookup=attendance_lookup,
        approved_leave_worker_ids=approved_leave_worker_ids,
        public_holiday_worker_ids=public_holiday_worker_ids,
    )


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
            pending_names: Optional[list[str]] = None
            try:
                pending_names = await pending_worker_names_for_chat(
                    settings=settings,
                    chat_id=chat_id,
                    reminder_type=slot.key,
                    target_date=now.date(),
                )
            except Exception:
                logger.exception("Failed to build smart reminder content for chat %s.", chat_id)

            if pending_names == []:
                sent_tokens.add(reminder_token(target_date=now.date(), slot_key=slot.key, chat_id=chat_id))
                continue

            try:
                await bot.send_message(
                    chat_id=chat_id,
                    text=build_attendance_reminder_text(slot.key, pending_names=pending_names),
                    reply_markup=worker_menu_keyboard(),
                )
            except TelegramAPIError:
                logger.exception("Failed to send %s attendance reminder to chat %s.", slot.key, chat_id)
                continue
            sent_tokens.add(reminder_token(target_date=now.date(), slot_key=slot.key, chat_id=chat_id))

        await asyncio.sleep(REMINDER_POLL_INTERVAL_SECONDS)
