from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, timedelta, timezone
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
LEAVE_DAY_PORTION_LABELS = {
    "full": "Sehari Penuh",
    "am": "Separuh Hari (Pagi)",
    "pm": "Separuh Hari (Petang)",
}
LEAVE_REPORT_CODES = {
    "annual": "AL",
    "mc": "MC",
    "emergency": "EL",
}
ACTIVE_REVIEWABLE_STATUSES = ("pending", "approved")
settings = get_settings()


class LeaveError(ValueError):
    pass


def is_supported_leave_type(leave_type: str) -> bool:
    return leave_type in LEAVE_LABELS


def normalize_leave_day_portion(day_portion: Optional[str]) -> str:
    normalized = (day_portion or "").strip().lower()
    if normalized in LEAVE_DAY_PORTION_LABELS:
        return normalized
    return "full"


def is_supported_leave_day_portion(day_portion: Optional[str]) -> bool:
    normalized = (day_portion or "").strip().lower()
    return normalized in LEAVE_DAY_PORTION_LABELS


def leave_day_portion_label(day_portion: Optional[str]) -> str:
    normalized = normalize_leave_day_portion(day_portion)
    return LEAVE_DAY_PORTION_LABELS[normalized]


def leave_is_partial_day(day_portion: Optional[str]) -> bool:
    return normalize_leave_day_portion(day_portion) in {"am", "pm"}


def leave_blocks_attendance(leave_request: LeaveRequest) -> bool:
    return not leave_is_partial_day(getattr(leave_request, "day_portion", None))


def leave_requires_photo(leave_type: str) -> bool:
    return leave_type in REQUIRES_PHOTO


def leave_label(leave_type: str, day_portion: Optional[str] = None) -> str:
    base_label = LEAVE_LABELS.get(leave_type, leave_type.title())
    normalized_day_portion = normalize_leave_day_portion(day_portion)
    if normalized_day_portion == "full":
        return base_label
    return f"{base_label} ({leave_day_portion_label(normalized_day_portion)})"


def leave_report_code(leave_type: str, day_portion: Optional[str] = None) -> str:
    base_code = LEAVE_REPORT_CODES.get(leave_type, leave_type.upper())
    normalized_day_portion = normalize_leave_day_portion(day_portion)
    if normalized_day_portion == "am":
        return f"{base_code}A"
    if normalized_day_portion == "pm":
        return f"{base_code}P"
    return base_code


def leave_duration_days(*, start_date: date, end_date: date, day_portion: Optional[str] = None) -> float:
    if end_date < start_date:
        return 0
    normalized_day_portion = normalize_leave_day_portion(day_portion)
    if start_date == end_date and normalized_day_portion in {"am", "pm"}:
        return 0.5
    return float((end_date - start_date).days + 1)


def leave_status_label(status: str) -> str:
    labels = {
        "pending": "Dalam Semakan",
        "approved": "Diluluskan",
        "rejected": "Ditolak",
    }
    return labels.get(status, status.replace("_", " ").title())


def annual_leave_notice_days() -> int:
    return max(0, settings.annual_leave_notice_days)


def annual_leave_notice_text() -> str:
    days = annual_leave_notice_days()
    if days == 1:
        return "Permohonan Cuti Tahunan perlu dibuat sekurang-kurangnya 1 hari sebelum tarikh mula."
    return f"Permohonan Cuti Tahunan perlu dibuat sekurang-kurangnya {days} hari sebelum tarikh mula."


def annual_leave_auto_reject_text() -> str:
    days = annual_leave_notice_days()
    if days == 1:
        return "Ditolak automatik kerana permohonan Cuti Tahunan dibuat kurang daripada 1 hari sebelum tarikh mula."
    return f"Ditolak automatik kerana permohonan Cuti Tahunan dibuat kurang daripada {days} hari sebelum tarikh mula."


def _clean_notes(value: Optional[str]) -> Optional[str]:
    cleaned = (value or "").strip()
    return cleaned or None


def _today_local_date() -> date:
    return datetime.now(settings.local_timezone).date()


def annual_leave_notice_met(*, leave_type: str, start_date: date, reference_date: Optional[date] = None) -> bool:
    """Return True if the annual leave notice period requirement is satisfied."""
    if leave_type != "annual":
        return True
    notice_days = annual_leave_notice_days()
    if not notice_days:
        return True
    effective_reference_date = reference_date or _today_local_date()
    return (start_date - effective_reference_date).days >= notice_days


def annual_leave_earliest_start_date(reference_date: Optional[date] = None) -> date:
    """Return the earliest start date that satisfies the annual leave notice requirement."""
    effective = reference_date or _today_local_date()
    return effective + timedelta(days=annual_leave_notice_days())


def _validate_annual_leave_notice(*, leave_type: str, start_date: date, reference_date: Optional[date] = None) -> None:
    if not annual_leave_notice_met(leave_type=leave_type, start_date=start_date, reference_date=reference_date):
        raise LeaveError(annual_leave_notice_text())


def _validated_day_portion(*, day_portion: Optional[str], start_date: date, end_date: date) -> str:
    raw_day_portion = (day_portion or "").strip().lower()
    if raw_day_portion and raw_day_portion not in LEAVE_DAY_PORTION_LABELS:
        raise LeaveError("Bahagian hari ini tidak disokong.")

    normalized_day_portion = normalize_leave_day_portion(day_portion)
    if start_date != end_date and normalized_day_portion != "full":
        raise LeaveError("Cuti separuh hari hanya disokong untuk satu tarikh sahaja.")
    return normalized_day_portion


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
    day_portion: Optional[str] = None,
    reason: str,
    telegram_file_id: Optional[str] = None,
) -> LeaveRequest:
    if not is_supported_leave_type(leave_type):
        raise LeaveError("Jenis cuti ini tidak disokong.")
    if end_date < start_date:
        raise LeaveError("Tarikh akhir tidak boleh lebih awal daripada tarikh mula.")
    validated_day_portion = _validated_day_portion(
        day_portion=day_portion,
        start_date=start_date,
        end_date=end_date,
    )
    _validate_annual_leave_notice(leave_type=leave_type, start_date=start_date)
    existing_request_result = await session.execute(
        select(LeaveRequest).where(
            LeaveRequest.worker_id == worker.id,
            LeaveRequest.status.in_(ACTIVE_REVIEWABLE_STATUSES),
            LeaveRequest.start_date <= end_date,
            LeaveRequest.end_date >= start_date,
        )
    )
    existing_request = existing_request_result.scalar_one_or_none()
    if existing_request:
        raise LeaveError(
            "Sudah ada permohonan cuti yang bertindih dalam tempoh ini. "
            "Sila semak permohonan sedia ada sebelum menghantar yang baharu."
        )
    if leave_requires_photo(leave_type) and not telegram_file_id:
        raise LeaveError("Gambar sokongan Telegram diperlukan untuk jenis cuti ini.")

    request = LeaveRequest(
        worker_id=worker.id,
        leave_type=leave_type,
        day_portion=validated_day_portion,
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


async def list_leave_requests_for_worker(
    session: AsyncSession,
    *,
    worker_id: int,
    limit: int = 5,
) -> Sequence[LeaveRequest]:
    result = await session.execute(
        select(LeaveRequest)
        .options(selectinload(LeaveRequest.worker).selectinload(Worker.site))
        .where(LeaveRequest.worker_id == worker_id)
        .order_by(LeaveRequest.submitted_at.desc(), LeaveRequest.id.desc())
        .limit(limit)
    )
    return result.scalars().all()


async def get_leave_request(session: AsyncSession, leave_id: int) -> Optional[LeaveRequest]:
    result = await session.execute(
        select(LeaveRequest)
        .options(selectinload(LeaveRequest.worker).selectinload(Worker.site))
        .where(LeaveRequest.id == leave_id)
    )
    return result.scalar_one_or_none()


async def admin_upsert_single_day_leave(
    session: AsyncSession,
    *,
    worker_id: int,
    leave_type: str,
    target_date: date,
    day_portion: Optional[str] = None,
    reason: Optional[str] = None,
) -> LeaveRequest:
    if not is_supported_leave_type(leave_type):
        raise LeaveError("Selected leave type is not supported.")
    validated_day_portion = _validated_day_portion(
        day_portion=day_portion,
        start_date=target_date,
        end_date=target_date,
    )

    worker = await session.get(Worker, worker_id)
    if not worker:
        raise LeaveError("Worker not found.")

    result = await session.execute(
        select(LeaveRequest).where(
            LeaveRequest.worker_id == worker_id,
            LeaveRequest.status.in_(ACTIVE_REVIEWABLE_STATUSES),
            LeaveRequest.start_date <= target_date,
            LeaveRequest.end_date >= target_date,
        )
    )
    existing_request = result.scalar_one_or_none()
    if existing_request and (existing_request.start_date != target_date or existing_request.end_date != target_date):
        raise LeaveError("This date is part of a multi-day leave request. Edit it from the Leave Requests page.")

    effective_reason = (
        (reason or "").strip()
        or f"{leave_label(leave_type, day_portion=validated_day_portion)} recorded from attendance grid."
    )

    if existing_request:
        existing_request.leave_type = leave_type
        existing_request.day_portion = validated_day_portion
        existing_request.reason = effective_reason
        existing_request.status = "approved"
        existing_request.reviewed_at = datetime.now(timezone.utc)
        existing_request.reviewed_by_telegram_id = 0
        existing_request.review_notes = "Updated from attendance grid."
        await session.commit()
        await session.refresh(existing_request)
        return existing_request

    leave_request = LeaveRequest(
        worker_id=worker_id,
        leave_type=leave_type,
        day_portion=validated_day_portion,
        start_date=target_date,
        end_date=target_date,
        reason=effective_reason,
        status="approved",
        reviewed_at=datetime.now(timezone.utc),
        reviewed_by_telegram_id=0,
        review_notes="Created from attendance grid.",
    )
    session.add(leave_request)
    await session.commit()
    await session.refresh(leave_request)
    return leave_request


async def delete_leave_request(session: AsyncSession, leave_request: LeaveRequest) -> None:
    await session.delete(leave_request)
    await session.commit()


async def approve_leave_request(
    session: AsyncSession,
    *,
    leave_request: LeaveRequest,
    admin_telegram_id: int,
    notes: Optional[str] = None,
) -> LeaveRequest:
    if not annual_leave_notice_met(
        leave_type=leave_request.leave_type,
        start_date=leave_request.start_date,
    ):
        return await _review_leave_request(
            session,
            leave_request=leave_request,
            admin_telegram_id=admin_telegram_id,
            status="rejected",
            notes=annual_leave_auto_reject_text(),
        )
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
        .options(selectinload(LeaveRequest.worker).selectinload(Worker.site))
        .where(
            LeaveRequest.status == "approved",
            LeaveRequest.start_date <= end_date,
            LeaveRequest.end_date >= start_date,
        )
    )
    return result.scalars().all()
