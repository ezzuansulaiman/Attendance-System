from __future__ import annotations

import calendar
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from config import get_settings
from datetime_utils import format_local_datetime, now_local
from models.models import AttendanceRecord, Site, Worker
from services.excel_generator import build_monthly_attendance_excel as render_monthly_attendance_excel
from services.leave_service import approved_leaves_in_range, leave_is_partial_day, leave_label, leave_report_code, normalize_leave_day_portion
from services.pdf_generator import build_monthly_attendance_pdf as render_monthly_attendance_pdf
from services.public_holiday_service import list_public_holidays_in_range
from services.site_service import get_default_site


def _active_worker_clause():
    return or_(Worker.is_active.is_(True), Worker.is_active.is_(None))


def build_report_download_filename(*, year: int, month: int, extension: str) -> str:
    timestamp = now_local().strftime("%Y%m%d-%H%M%S")
    normalized_extension = extension.lstrip(".")
    return f"attendance-{year}-{month:02d}-{timestamp}.{normalized_extension}"


def _site_name(worker: Worker) -> str:
    return worker.site.name if worker.site else "Unassigned"


def _display_site_name(site_name: str, *, default_site_name: str) -> str:
    cleaned_site_name = (site_name or "").strip()
    cleaned_default = (default_site_name or "").strip()
    if cleaned_site_name and cleaned_default and cleaned_site_name.casefold() == cleaned_default.casefold():
        return f"{cleaned_default} Region"
    return cleaned_site_name or f"{cleaned_default} Region"


def _build_attendance_lookup(
    attendance_records: list[AttendanceRecord],
) -> dict[tuple[int, date], AttendanceRecord]:
    return {
        (record.worker_id, record.attendance_date): record for record in attendance_records
    }


def _build_public_holiday_lookup(public_holidays: list[object]) -> dict[date, object]:
    lookup: dict[date, object] = {}
    for public_holiday in sorted(public_holidays, key=lambda item: (item.site_id is not None, item.id)):
        lookup[public_holiday.holiday_date] = public_holiday
    return lookup


def _build_leave_lookup(
    approved_leaves: list[object],
    *,
    year: int,
    month: int,
    days_in_month: int,
) -> dict[tuple[int, date], object]:
    lookup: dict[tuple[int, date], object] = {}
    for leave_request in approved_leaves:
        current_date = max(leave_request.start_date, date(year, month, 1))
        final_date = min(leave_request.end_date, date(year, month, days_in_month))
        while current_date <= final_date:
            lookup[(leave_request.worker_id, current_date)] = leave_request
            current_date = date.fromordinal(current_date.toordinal() + 1)
    return lookup


def _report_attendance_symbol(record: Optional[AttendanceRecord]) -> str:
    if not record:
        return ""
    if record.check_in_at:
        return "P"
    if record.check_out_at:
        return "OUT"
    return "REC"


def _attendance_symbol(
    record: Optional[AttendanceRecord],
    leave_request: Optional[object],
    *,
    public_holiday: Optional[object],
) -> str:
    if leave_request:
        leave_code = leave_report_code(
            leave_request.leave_type,
            day_portion=normalize_leave_day_portion(getattr(leave_request, "day_portion", None)),
        )
        attendance_code = _report_attendance_symbol(record)
        if attendance_code:
            return f"{attendance_code}/{leave_code}"
        return leave_code
    attendance_code = _report_attendance_symbol(record)
    if attendance_code:
        return attendance_code
    if public_holiday:
        return "PH"
    return ""


def _attendance_status(record: AttendanceRecord) -> str:
    if record.check_in_at and record.check_out_at:
        return "Present"
    if record.check_in_at:
        return "Pending checkout"
    return "Recorded"


def _format_timestamp(value: Optional[datetime]) -> str:
    return format_local_datetime(value, "%Y-%m-%d %H:%M") if value else "-"


def _build_worker_report_row(
    *,
    worker: Worker,
    year: int,
    month: int,
    days_in_month: int,
    attendance_lookup: dict[tuple[int, date], AttendanceRecord],
    leave_lookup: dict[tuple[int, date], object],
    public_holiday_lookup: dict[date, object],
) -> dict[str, Any]:
    day_values: list[str] = []
    present_days = 0
    completed_days = 0

    for day in range(1, 32):
        if day > days_in_month:
            day_values.append("")
            continue

        current_date = date(year, month, day)
        record = attendance_lookup.get((worker.id, current_date))
        leave_request = leave_lookup.get((worker.id, current_date))
        public_holiday = public_holiday_lookup.get(current_date)
        symbol = _attendance_symbol(record, leave_request, public_holiday=public_holiday)
        if symbol:
            if record and record.check_in_at:
                present_days += 1
            if record and record.check_out_at:
                completed_days += 1
        day_values.append(symbol)

    return {
        "worker_name": worker.full_name,
        "employee_code": worker.employee_code or "-",
        "site_name": _site_name(worker),
        "days": day_values,
        "present_days": present_days,
        "completed_days": completed_days,
    }


def _detail_status(record: Optional[AttendanceRecord], leave_request: Optional[object]) -> str:
    if record and leave_request:
        return f"{_attendance_status(record)} + {leave_label(leave_request.leave_type, leave_request.day_portion)}"
    if leave_request:
        if leave_is_partial_day(leave_request.day_portion):
            return f"Approved half-day leave ({leave_label(leave_request.leave_type, leave_request.day_portion)})"
        return f"Approved leave ({leave_label(leave_request.leave_type, leave_request.day_portion)})"
    if record:
        return _attendance_status(record)
    return "-"


def _detail_notes(record: Optional[AttendanceRecord], leave_request: Optional[object]) -> str:
    notes: list[str] = []
    if leave_request and leave_request.reason:
        notes.append(f"Leave: {leave_request.reason}")
    if record and record.notes:
        notes.append(f"Attendance: {record.notes}")
    if notes:
        return " | ".join(notes)
    return "-"


def _build_detail_rows(
    *,
    attendance_lookup: dict[tuple[int, date], AttendanceRecord],
    leave_lookup: dict[tuple[int, date], object],
) -> list[dict[str, str]]:
    ordered_keys = sorted(
        set(attendance_lookup) | set(leave_lookup),
        key=lambda item: (
            item[1],
            _site_name(attendance_lookup.get(item, leave_lookup.get(item)).worker),
            attendance_lookup.get(item, leave_lookup.get(item)).worker.full_name,
        ),
    )
    detail_rows: list[dict[str, str]] = []
    for key in ordered_keys:
        record = attendance_lookup.get(key)
        leave_request = leave_lookup.get(key)
        worker = record.worker if record else leave_request.worker
        target_date = key[1]
        detail_rows.append(
            {
                "attendance_date": target_date.isoformat(),
                "weekday": calendar.day_abbr[target_date.weekday()],
                "worker_name": worker.full_name,
                "employee_code": worker.employee_code or "-",
                "site_name": _site_name(worker),
                "status": _detail_status(record, leave_request),
                "check_in": _format_timestamp(record.check_in_at if record else None),
                "check_out": _format_timestamp(record.check_out_at if record else None),
                "notes": _detail_notes(record, leave_request),
            }
        )
    return detail_rows


async def _resolve_report_scope(
    session: AsyncSession,
    *,
    site_id: Optional[int],
    default_site_name: str,
) -> tuple[Optional[int], str]:
    if site_id:
        site_result = await session.execute(select(Site).where(Site.id == site_id))
        site = site_result.scalar_one_or_none()
        if site:
            return site.id, _display_site_name(site.name, default_site_name=default_site_name)

    default_site_result = await session.execute(select(Site).where(Site.name == default_site_name).limit(1))
    default_site = default_site_result.scalar_one_or_none()
    if default_site:
        return default_site.id, _display_site_name(default_site.name, default_site_name=default_site_name)

    fallback_site = await get_default_site(session)
    if fallback_site:
        return fallback_site.id, _display_site_name(fallback_site.name, default_site_name=default_site_name)

    return None, _display_site_name(default_site_name, default_site_name=default_site_name)


async def build_monthly_attendance_report(
    session: AsyncSession,
    *,
    year: int,
    month: int,
    site_id: Optional[int] = None,
) -> dict[str, Any]:
    settings = get_settings()
    _, days_in_month = calendar.monthrange(year, month)
    start_date = date(year, month, 1)
    end_date = date(year, month, days_in_month)
    resolved_site_id, report_site_name = await _resolve_report_scope(
        session,
        site_id=site_id,
        default_site_name=settings.default_site_name,
    )

    workers_query = (
        select(Worker)
        .options(selectinload(Worker.site))
        .where(_active_worker_clause())
        .order_by(Worker.full_name)
    )
    if resolved_site_id:
        workers_query = workers_query.where(Worker.site_id == resolved_site_id)
    workers_result = await session.execute(workers_query)
    workers = workers_result.scalars().all()

    attendance_query = (
        select(AttendanceRecord)
        .options(selectinload(AttendanceRecord.worker).selectinload(Worker.site))
        .join(AttendanceRecord.worker)
        .where(
            AttendanceRecord.attendance_date >= start_date,
            AttendanceRecord.attendance_date <= end_date,
        )
        .order_by(AttendanceRecord.attendance_date, Worker.full_name)
    )
    if resolved_site_id:
        attendance_query = attendance_query.where(Worker.site_id == resolved_site_id)
    attendance_result = await session.execute(attendance_query)
    attendance_records = attendance_result.scalars().all()
    approved_leaves = await approved_leaves_in_range(session, start_date=start_date, end_date=end_date)
    public_holidays = await list_public_holidays_in_range(session, start_date=start_date, end_date=end_date)

    attendance_lookup = _build_attendance_lookup(attendance_records)
    worker_ids = {worker.id for worker in workers}
    leave_lookup = _build_leave_lookup(
        [leave for leave in approved_leaves if leave.worker_id in worker_ids],
        year=year,
        month=month,
        days_in_month=days_in_month,
    )
    public_holiday_lookup = _build_public_holiday_lookup(
        [holiday for holiday in public_holidays if holiday.site_id in {resolved_site_id, None}]
    )
    report_rows = [
        _build_worker_report_row(
            worker=worker,
            year=year,
            month=month,
            days_in_month=days_in_month,
            attendance_lookup=attendance_lookup,
            leave_lookup=leave_lookup,
            public_holiday_lookup=public_holiday_lookup,
        )
        for worker in workers
    ]
    detail_rows = _build_detail_rows(attendance_lookup=attendance_lookup, leave_lookup=leave_lookup)
    total_present_days = sum(int(row["present_days"]) for row in report_rows)
    total_completed_days = sum(int(row["completed_days"]) for row in report_rows)
    total_workers = len(report_rows)

    return {
        "company_name": settings.company_name,
        "site_name": report_site_name,
        "year": year,
        "month": month,
        "days_in_month": days_in_month,
        "period_label": f"{calendar.month_name[month]} {year}",
        "generated_at": now_local().strftime("%d %b %Y %H:%M"),
        "rows": report_rows,
        "detail_rows": detail_rows,
        "summary": {
            "total_workers": total_workers,
            "total_present_days": total_present_days,
            "total_completed_days": total_completed_days,
            "average_present_days": round(total_present_days / total_workers, 1) if total_workers else 0,
            "completion_rate": round((total_completed_days / total_present_days) * 100, 1)
            if total_present_days
            else 0,
        },
    }


async def generate_monthly_attendance_pdf(
    session: AsyncSession,
    *,
    year: int,
    month: int,
    site_id: Optional[int] = None,
) -> bytes:
    report = await build_monthly_attendance_report(session, year=year, month=month, site_id=site_id)
    return render_monthly_attendance_pdf(report=report)


async def generate_monthly_attendance_excel(
    session: AsyncSession,
    *,
    year: int,
    month: int,
    site_id: Optional[int] = None,
) -> bytes:
    report = await build_monthly_attendance_report(session, year=year, month=month, site_id=site_id)
    return render_monthly_attendance_excel(report=report)
