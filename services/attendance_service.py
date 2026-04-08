from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Select, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from datetime_utils import coerce_optional_local_datetime
from models.models import AttendanceRecord, LeaveRequest, Site, Worker
from services.leave_service import leave_blocks_attendance
from services.site_service import get_default_site


class AttendanceError(ValueError):
    pass


def _clean_optional_text(value: Optional[str]) -> Optional[str]:
    cleaned = (value or "").strip()
    return cleaned or None


def _worker_lookup_query(telegram_user_id: int) -> Select[tuple[Worker]]:
    return select(Worker).options(selectinload(Worker.site)).where(Worker.telegram_user_id == telegram_user_id)


def _active_worker_clause():
    # Legacy rows may carry NULL in is_active; treat them as active until normalized.
    return or_(Worker.is_active.is_(True), Worker.is_active.is_(None))


def _attendance_lookup_query(worker_id: int, attendance_date: date) -> Select[tuple[AttendanceRecord]]:
    return select(AttendanceRecord).where(
        AttendanceRecord.worker_id == worker_id,
        AttendanceRecord.attendance_date == attendance_date,
    )


def _attendance_list_query() -> Select[tuple[AttendanceRecord]]:
    return (
        select(AttendanceRecord)
        .options(selectinload(AttendanceRecord.worker).selectinload(Worker.site))
        .join(AttendanceRecord.worker)
        .order_by(AttendanceRecord.attendance_date.desc(), Worker.full_name)
    )


async def get_worker_by_telegram_id(
    session: AsyncSession,
    telegram_user_id: int,
    *,
    active_only: bool = True,
) -> Optional[Worker]:
    query = _worker_lookup_query(telegram_user_id)
    if active_only:
        query = query.where(_active_worker_clause())
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def get_worker_by_id(session: AsyncSession, worker_id: int) -> Optional[Worker]:
    result = await session.execute(
        select(Worker).options(selectinload(Worker.site)).where(Worker.id == worker_id)
    )
    return result.scalar_one_or_none()


async def list_workers(session: AsyncSession, *, site_id: Optional[int] = None) -> Sequence[Worker]:
    query = select(Worker).options(selectinload(Worker.site)).order_by(Worker.full_name)
    if site_id:
        query = query.where(Worker.site_id == site_id)
    result = await session.execute(query)
    return result.scalars().all()


async def list_active_workers(session: AsyncSession, *, site_id: Optional[int] = None) -> Sequence[Worker]:
    query = (
        select(Worker)
        .options(selectinload(Worker.site))
        .where(_active_worker_clause())
        .order_by(Worker.full_name)
    )
    if site_id:
        query = query.where(Worker.site_id == site_id)
    result = await session.execute(query)
    return result.scalars().all()


async def create_worker(
    session: AsyncSession,
    *,
    full_name: str,
    telegram_user_id: int,
    ic_number: Optional[str],
    employee_code: Optional[str],
    site_id: Optional[int],
    is_active: bool = True,
) -> Worker:
    existing = await get_worker_by_telegram_id(session, telegram_user_id, active_only=False)
    if existing:
        raise AttendanceError("Telegram ID ini sudah berdaftar dalam sistem.")
    if site_id is not None:
        site = await session.get(Site, site_id)
        if not site:
            raise AttendanceError("Selected site was not found.")
    else:
        default_site = await get_default_site(session)
        site_id = default_site.id if default_site else None

    worker = Worker(
        full_name=full_name.strip(),
        telegram_user_id=telegram_user_id,
        ic_number=_clean_optional_text(ic_number),
        employee_code=(employee_code or "").strip() or None,
        site_id=site_id,
        is_active=is_active,
    )
    session.add(worker)
    await session.commit()
    await session.refresh(worker)
    return worker


async def update_worker(
    session: AsyncSession,
    worker: Worker,
    *,
    full_name: str,
    telegram_user_id: int,
    ic_number: Optional[str],
    employee_code: Optional[str],
    site_id: Optional[int],
    is_active: bool,
) -> Worker:
    existing = await session.execute(
        select(Worker).where(
            Worker.telegram_user_id == telegram_user_id,
            Worker.id != worker.id,
        )
    )
    if existing.scalar_one_or_none():
        raise AttendanceError("Telegram user ID is already used by another worker.")
    if site_id is not None:
        site = await session.get(Site, site_id)
        if not site:
            raise AttendanceError("Selected site was not found.")

    worker.full_name = full_name.strip()
    worker.telegram_user_id = telegram_user_id
    worker.ic_number = _clean_optional_text(ic_number)
    worker.employee_code = (employee_code or "").strip() or None
    worker.site_id = site_id
    worker.is_active = is_active
    await session.commit()
    await session.refresh(worker)
    return worker


async def self_register_worker(
    session: AsyncSession,
    *,
    telegram_user_id: int,
    full_name: str,
    ic_number: str,
) -> Worker:
    return await create_worker(
        session,
        full_name=full_name,
        telegram_user_id=telegram_user_id,
        ic_number=ic_number,
        employee_code=None,
        site_id=None,
        is_active=True,
    )


async def get_attendance_for_date(
    session: AsyncSession,
    *,
    worker_id: int,
    attendance_date: date,
) -> Optional[AttendanceRecord]:
    result = await session.execute(_attendance_lookup_query(worker_id, attendance_date))
    return result.scalar_one_or_none()


async def _approved_leave_for_day(
    session: AsyncSession,
    worker_id: int,
    target_date: date,
) -> Optional[LeaveRequest]:
    result = await session.execute(
        select(LeaveRequest).where(
            LeaveRequest.worker_id == worker_id,
            LeaveRequest.status == "approved",
            LeaveRequest.start_date <= target_date,
            LeaveRequest.end_date >= target_date,
        )
    )
    return result.scalar_one_or_none()


async def get_approved_leave_for_day(
    session: AsyncSession,
    *,
    worker_id: int,
    target_date: date,
) -> Optional[LeaveRequest]:
    return await _approved_leave_for_day(session, worker_id, target_date)


async def check_in(
    session: AsyncSession,
    *,
    worker: Worker,
    chat_id: int,
    occurred_at: datetime,
) -> AttendanceRecord:
    occurred_at = coerce_optional_local_datetime(occurred_at)
    if occurred_at is None:
        raise AttendanceError("Check-in time is required.")
    attendance_date = occurred_at.date()
    leave = await _approved_leave_for_day(session, worker.id, attendance_date)
    if leave and leave_blocks_attendance(leave):
        raise AttendanceError("Anda sudah mempunyai cuti yang diluluskan untuk hari ini.")

    record = await get_attendance_for_date(
        session,
        worker_id=worker.id,
        attendance_date=attendance_date,
    )
    if record and record.check_in_at:
        raise AttendanceError("Anda sudah merekod masuk untuk hari ini.")

    if not record:
        record = AttendanceRecord(
            worker_id=worker.id,
            attendance_date=attendance_date,
            source_chat_id=chat_id,
        )
        session.add(record)

    record.check_in_at = occurred_at
    record.source_chat_id = chat_id
    await session.commit()
    await session.refresh(record)
    return record


async def check_out(
    session: AsyncSession,
    *,
    worker: Worker,
    chat_id: int,
    occurred_at: datetime,
) -> AttendanceRecord:
    occurred_at = coerce_optional_local_datetime(occurred_at)
    if occurred_at is None:
        raise AttendanceError("Check-out time is required.")
    attendance_date = occurred_at.date()
    record = await get_attendance_for_date(
        session,
        worker_id=worker.id,
        attendance_date=attendance_date,
    )
    if not record or not record.check_in_at:
        raise AttendanceError("Rekod masuk diperlukan sebelum rekod keluar.")
    if record.check_out_at:
        raise AttendanceError("Anda sudah merekod keluar untuk hari ini.")

    record.check_out_at = occurred_at
    record.source_chat_id = chat_id
    await session.commit()
    await session.refresh(record)
    return record


async def list_attendance_records(
    session: AsyncSession,
    *,
    month: Optional[int] = None,
    year: Optional[int] = None,
    site_id: Optional[int] = None,
) -> Sequence[AttendanceRecord]:
    query: Select[tuple[AttendanceRecord]] = _attendance_list_query()
    if month and year:
        query = query.where(
            func.extract("month", AttendanceRecord.attendance_date) == month,
            func.extract("year", AttendanceRecord.attendance_date) == year,
        )
    if site_id:
        query = query.where(Worker.site_id == site_id)
    result = await session.execute(query)
    return result.scalars().all()


async def get_attendance_record(session: AsyncSession, record_id: int) -> Optional[AttendanceRecord]:
    result = await session.execute(
        select(AttendanceRecord)
        .options(selectinload(AttendanceRecord.worker).selectinload(Worker.site))
        .where(AttendanceRecord.id == record_id)
    )
    return result.scalar_one_or_none()


async def create_or_update_attendance_record(
    session: AsyncSession,
    *,
    worker_id: int,
    attendance_date: date,
    check_in_at: Optional[datetime],
    check_out_at: Optional[datetime],
    notes: Optional[str],
) -> AttendanceRecord:
    check_in_at = coerce_optional_local_datetime(check_in_at)
    check_out_at = coerce_optional_local_datetime(check_out_at)
    worker = await get_worker_by_id(session, worker_id)
    if not worker:
        raise AttendanceError("Worker not found.")
    if check_in_at and check_out_at and check_out_at < check_in_at:
        raise AttendanceError("Check-out cannot be earlier than check-in.")

    record = await get_attendance_for_date(
        session,
        worker_id=worker_id,
        attendance_date=attendance_date,
    )
    if not record:
        record = AttendanceRecord(worker_id=worker_id, attendance_date=attendance_date)
        session.add(record)

    record.check_in_at = check_in_at
    record.check_out_at = check_out_at
    record.notes = _clean_optional_text(notes)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise AttendanceError("Another attendance record already exists for this worker on that date.") from exc
    await session.refresh(record)
    return record


async def update_attendance_record(
    session: AsyncSession,
    record: AttendanceRecord,
    *,
    worker_id: int,
    attendance_date: date,
    check_in_at: Optional[datetime],
    check_out_at: Optional[datetime],
    notes: Optional[str],
) -> AttendanceRecord:
    check_in_at = coerce_optional_local_datetime(check_in_at)
    check_out_at = coerce_optional_local_datetime(check_out_at)
    worker = await get_worker_by_id(session, worker_id)
    if not worker:
        raise AttendanceError("Worker not found.")
    if check_in_at and check_out_at and check_out_at < check_in_at:
        raise AttendanceError("Check-out cannot be earlier than check-in.")

    existing = await get_attendance_for_date(
        session,
        worker_id=worker_id,
        attendance_date=attendance_date,
    )
    if existing and existing.id != record.id:
        raise AttendanceError("Another attendance record already exists for this worker on that date.")

    record.worker_id = worker_id
    record.attendance_date = attendance_date
    record.check_in_at = check_in_at
    record.check_out_at = check_out_at
    record.notes = _clean_optional_text(notes)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise AttendanceError("Another attendance record already exists for this worker on that date.") from exc
    await session.refresh(record)
    return record


async def delete_attendance_record(session: AsyncSession, record: AttendanceRecord) -> None:
    await session.delete(record)
    await session.commit()


async def get_dashboard_summary(
    session: AsyncSession,
    *,
    target_date: date,
    site_id: Optional[int] = None,
) -> dict[str, int]:
    worker_query = select(func.count()).select_from(Worker).where(_active_worker_clause())
    if site_id:
        worker_query = worker_query.where(Worker.site_id == site_id)
    total_workers = await session.scalar(worker_query)

    checkin_query = (
        select(func.count())
        .select_from(AttendanceRecord)
        .join(AttendanceRecord.worker)
        .where(
            AttendanceRecord.attendance_date == target_date,
            AttendanceRecord.check_in_at.is_not(None),
        )
    )
    if site_id:
        checkin_query = checkin_query.where(Worker.site_id == site_id)
    checked_in = await session.scalar(
        checkin_query
    )

    checkout_query = (
        select(func.count())
        .select_from(AttendanceRecord)
        .join(AttendanceRecord.worker)
        .where(
            AttendanceRecord.attendance_date == target_date,
            AttendanceRecord.check_out_at.is_not(None),
        )
    )
    if site_id:
        checkout_query = checkout_query.where(Worker.site_id == site_id)
    checked_out = await session.scalar(
        checkout_query
    )
    pending_query = (
        select(func.count())
        .select_from(LeaveRequest)
        .join(LeaveRequest.worker)
        .where(LeaveRequest.status == "pending")
    )
    if site_id:
        pending_query = pending_query.where(Worker.site_id == site_id)
    pending_leaves = await session.scalar(pending_query)
    return {
        "total_workers": int(total_workers or 0),
        "checked_in": int(checked_in or 0),
        "checked_out": int(checked_out or 0),
        "pending_leaves": int(pending_leaves or 0),
    }


async def recent_attendance(
    session: AsyncSession,
    *,
    limit: int = 10,
    site_id: Optional[int] = None,
) -> Sequence[AttendanceRecord]:
    query = (
        select(AttendanceRecord)
        .options(selectinload(AttendanceRecord.worker).selectinload(Worker.site))
        .join(AttendanceRecord.worker)
        .order_by(AttendanceRecord.updated_at.desc(), AttendanceRecord.id.desc())
        .limit(limit)
    )
    if site_id:
        query = query.where(Worker.site_id == site_id)
    result = await session.execute(query)
    return result.scalars().all()


async def list_recent_attendance_for_worker(
    session: AsyncSession,
    *,
    worker_id: int,
    limit: int = 5,
) -> Sequence[AttendanceRecord]:
    result = await session.execute(
        select(AttendanceRecord)
        .where(AttendanceRecord.worker_id == worker_id)
        .order_by(AttendanceRecord.attendance_date.desc(), AttendanceRecord.id.desc())
        .limit(limit)
    )
    return result.scalars().all()


async def list_attendance_for_date(
    session: AsyncSession,
    *,
    attendance_date: date,
) -> Sequence[AttendanceRecord]:
    result = await session.execute(
        select(AttendanceRecord)
        .options(selectinload(AttendanceRecord.worker).selectinload(Worker.site))
        .join(AttendanceRecord.worker)
        .where(AttendanceRecord.attendance_date == attendance_date)
    )
    return result.scalars().all()
