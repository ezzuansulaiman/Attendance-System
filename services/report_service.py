from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from config import get_settings
from models.models import AttendanceRecord, Site, Worker
from services.leave_service import approved_leaves_in_range, leave_report_code
from services.pdf_generator import build_monthly_attendance_pdf


def _build_attendance_lookup(
    attendance_records: list[AttendanceRecord],
) -> dict[tuple[int, date], AttendanceRecord]:
    return {
        (record.worker_id, record.attendance_date): record for record in attendance_records
    }


def _build_leave_lookup(
    approved_leaves,
    *,
    start_date: date,
    end_date: date,
) -> dict[tuple[int, date], str]:
    leave_lookup: dict[tuple[int, date], str] = {}
    for leave in approved_leaves:
        cursor = leave.start_date
        while cursor <= leave.end_date:
            if start_date <= cursor <= end_date:
                leave_lookup[(leave.worker_id, cursor)] = leave_report_code(leave.leave_type)
            cursor = cursor + timedelta(days=1)
    return leave_lookup


def _build_worker_report_row(
    *,
    worker: Worker,
    year: int,
    month: int,
    days_in_month: int,
    attendance_lookup: dict[tuple[int, date], AttendanceRecord],
    leave_lookup: dict[tuple[int, date], str],
) -> dict[str, object]:
    day_values: list[str] = []
    present_total = 0
    leave_total = 0

    for day in range(1, 32):
        if day > days_in_month:
            day_values.append("")
            continue

        current_date = date(year, month, day)
        if (worker.id, current_date) in leave_lookup:
            value = leave_lookup[(worker.id, current_date)]
            leave_total += 1
        elif (worker.id, current_date) in attendance_lookup and attendance_lookup[(worker.id, current_date)].check_in_at:
            value = "P"
            present_total += 1
        else:
            value = ""
        day_values.append(value)

    return {
        "worker_name": worker.full_name,
        "employee_code": worker.employee_code or "-",
        "days": day_values,
        "present_total": present_total,
        "leave_total": leave_total,
    }


async def generate_monthly_attendance_pdf(
    session: AsyncSession,
    *,
    year: int,
    month: int,
    site_id: Optional[int] = None,
) -> bytes:
    settings = get_settings()
    _, days_in_month = calendar.monthrange(year, month)
    start_date = date(year, month, 1)
    end_date = date(year, month, days_in_month)

    workers_query = select(Worker).where(Worker.is_active.is_(True)).order_by(Worker.full_name)
    if site_id:
        workers_query = workers_query.where(Worker.site_id == site_id)
    workers_result = await session.execute(workers_query)
    workers = workers_result.scalars().all()

    attendance_query = (
        select(AttendanceRecord)
        .options(selectinload(AttendanceRecord.worker))
        .join(AttendanceRecord.worker)
        .where(
            AttendanceRecord.attendance_date >= start_date,
            AttendanceRecord.attendance_date <= end_date,
        )
    )
    if site_id:
        attendance_query = attendance_query.where(Worker.site_id == site_id)
    attendance_result = await session.execute(attendance_query)
    attendance_records = attendance_result.scalars().all()
    approved_leaves = await approved_leaves_in_range(session, start_date=start_date, end_date=end_date)
    if site_id:
        approved_leaves = [leave for leave in approved_leaves if leave.worker and leave.worker.site_id == site_id]

    attendance_lookup = _build_attendance_lookup(attendance_records)
    leave_lookup = _build_leave_lookup(
        approved_leaves,
        start_date=start_date,
        end_date=end_date,
    )

    report_rows: list[dict[str, object]] = []
    for worker in workers:
        report_rows.append(
            _build_worker_report_row(
                worker=worker,
                year=year,
                month=month,
                days_in_month=days_in_month,
                attendance_lookup=attendance_lookup,
                leave_lookup=leave_lookup,
            )
        )

    report_name = settings.company_name
    if site_id:
        site_result = await session.execute(select(Site).where(Site.id == site_id))
        site = site_result.scalar_one_or_none()
        if site:
            report_name = f"{settings.company_name} - {site.name}"

    return build_monthly_attendance_pdf(
        company_name=report_name,
        year=year,
        month=month,
        rows=report_rows,
    )
