from __future__ import annotations

import calendar
from datetime import date, datetime
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from config import get_settings
from datetime_utils import format_local_datetime, now_local
from models.models import AttendanceRecord, Site, Worker
from services.excel_generator import build_monthly_attendance_excel as render_monthly_attendance_excel
from services.pdf_generator import build_monthly_attendance_pdf as render_monthly_attendance_pdf
from services.site_service import get_default_site


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


def _attendance_symbol(record: Optional[AttendanceRecord]) -> str:
    return "P" if record and record.check_in_at else ""


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
        symbol = _attendance_symbol(record)
        if symbol:
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


def _build_detail_rows(attendance_records: list[AttendanceRecord]) -> list[dict[str, str]]:
    ordered_records = sorted(
        attendance_records,
        key=lambda record: (
            record.attendance_date,
            _site_name(record.worker),
            record.worker.full_name,
        ),
    )
    detail_rows: list[dict[str, str]] = []
    for record in ordered_records:
        detail_rows.append(
            {
                "attendance_date": record.attendance_date.isoformat(),
                "weekday": calendar.day_abbr[record.attendance_date.weekday()],
                "worker_name": record.worker.full_name,
                "employee_code": record.worker.employee_code or "-",
                "site_name": _site_name(record.worker),
                "status": _attendance_status(record),
                "check_in": _format_timestamp(record.check_in_at),
                "check_out": _format_timestamp(record.check_out_at),
                "notes": record.notes or "-",
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
        .where(Worker.is_active.is_(True))
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

    attendance_lookup = _build_attendance_lookup(attendance_records)
    report_rows = [
        _build_worker_report_row(
            worker=worker,
            year=year,
            month=month,
            days_in_month=days_in_month,
            attendance_lookup=attendance_lookup,
        )
        for worker in workers
    ]
    detail_rows = _build_detail_rows(attendance_records)
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
