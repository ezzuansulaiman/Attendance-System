from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from config import get_settings
from models.models import LeaveRequest, Worker

REQUIRES_PHOTO = {"mc", "emergency"}
LEAVE_LABELS = {
    "annual": "Cuti Tahunan",
    "mc": "Cuti Sakit",
    "emergency": "Cuti Kecemasan",
}
LEAVE_REPORT_CODES = {
    "annual": "AL",
    "mc": "MC",
    "emergency": "EL",
}
settings = get_settings()


class LeaveError(ValueError):
    pass


def is_supported_leave_type(leave_type: str) -> bool:
    return leave_type in LEAVE_LABELS


def leave_requires_photo(leave_type: str) -> bool:
    return leave_type in REQUIRES_PHOTO


def leave_label(leave_type: str) -> str:
    return LEAVE_LABELS.get(leave_type, leave_type.title())


def leave_report_code(leave_type: str) -> str:
    return LEAVE_REPORT_CODES.get(leave_type, leave_type.upper())


def annual_leave_notice_days() -> int:
    return max(0, settings.annual_leave_notice_days)


def annual_leave_notice_text() -> str:
    days = annual_leave_notice_days()
    if days == 1:
        return "Permohonan Cuti Tahunan perlu dibuat sekurang-kurangnya 1 hari sebelum tarikh mula."
    return f"Permohonan Cuti Tahunan perlu dibuat sekurang-kurangnya {days} hari sebelum tarikh mula."


def _clean_notes(value: Optional[str]) -> Optional[str]:
    cleaned = (value or "").strip()
    return cleaned or None


async def _review_leave_request(
    session: AsyncSession,
    *,
    leave_request: LeaveRequest,
    admin_telegram_id: int,
    status: str,
    notes: Optional[str] = None,
) -> LeaveRequest:
    if leave_request.status != "pending":
        raise LeaveError("This leave request has already been reviewed.")

    leave_request.status = status
    leave_request.reviewed_at = datetime.now(timezone.utc)
    leave_request.reviewed_by_telegram_id = admin_telegram_id
    leave_request.review_notes = _clean_notes(notes)
    await session.commit()
    await session.refresh(leave_request)
    return leave_request


async def create_leave_request(
    session: AsyncSession,
    *,
    worker: Worker,
    leave_type: str,
    start_date: date,
    end_date: date,
    reason: str,
    telegram_file_id: Optional[str] = None,
) -> LeaveRequest:
    if not is_supported_leave_type(leave_type):
        raise LeaveError("Unsupported leave type.")
    if end_date < start_date:
        raise LeaveError("End date cannot be earlier than start date.")
    if leave_type == "annual":
        today = datetime.now(settings.local_timezone).date()
        notice_days = annual_leave_notice_days()
        if notice_days and (start_date - today).days < notice_days:
            raise LeaveError(annual_leave_notice_text())
    if leave_requires_photo(leave_type) and not telegram_file_id:
        raise LeaveError("A Telegram photo is required for this leave type.")

    request = LeaveRequest(
        worker_id=worker.id,
        leave_type=leave_type,
        start_date=start_date,
        end_date=end_date,
        reason=reason.strip(),
        telegram_file_id=telegram_file_id,
        status="pending",
    )
    session.add(request)
    await session.commit()
    await session.refresh(request)
    return request


async def list_pending_leave_requests(session: AsyncSession) -> Sequence[LeaveRequest]:
    result = await session.execute(
        select(LeaveRequest)
        .options(selectinload(LeaveRequest.worker).selectinload(Worker.site))
        .join(LeaveRequest.worker)
        .where(LeaveRequest.status == "pending")
        .order_by(LeaveRequest.submitted_at.asc())
    )
    return result.scalars().all()


async def list_leave_requests(session: AsyncSession, *, site_id: Optional[int] = None) -> Sequence[LeaveRequest]:
    query = (
        select(LeaveRequest)
        .options(selectinload(LeaveRequest.worker).selectinload(Worker.site))
        .join(LeaveRequest.worker)
        .order_by(LeaveRequest.submitted_at.desc())
    )
    if site_id:
        query = query.where(Worker.site_id == site_id)
    result = await session.execute(query)
    return result.scalars().all()


async def get_leave_request(session: AsyncSession, leave_id: int) -> Optional[LeaveRequest]:
    result = await session.execute(
        select(LeaveRequest)
        .options(selectinload(LeaveRequest.worker).selectinload(Worker.site))
        .where(LeaveRequest.id == leave_id)
    )
    return result.scalar_one_or_none()


async def approve_leave_request(
    session: AsyncSession,
    *,
    leave_request: LeaveRequest,
    admin_telegram_id: int,
    notes: Optional[str] = None,
) -> LeaveRequest:
    return await _review_leave_request(
        session,
        leave_request=leave_request,
        admin_telegram_id=admin_telegram_id,
        status="approved",
        notes=notes,
    )


async def reject_leave_request(
    session: AsyncSession,
    *,
    leave_request: LeaveRequest,
    admin_telegram_id: int,
    notes: Optional[str] = None,
) -> LeaveRequest:
    return await _review_leave_request(
        session,
        leave_request=leave_request,
        admin_telegram_id=admin_telegram_id,
        status="rejected",
        notes=notes,
    )


async def approved_leaves_in_range(
    session: AsyncSession,
    *,
    start_date: date,
    end_date: date,
) -> Sequence[LeaveRequest]:
    result = await session.execute(
        select(LeaveRequest)
        .options(selectinload(LeaveRequest.worker))
        .where(
            LeaveRequest.status == "approved",
            LeaveRequest.start_date <= end_date,
            LeaveRequest.end_date >= start_date,
        )
    )
    return result.scalars().all()
