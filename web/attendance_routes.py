from __future__ import annotations

import calendar
from datetime import date
from typing import Optional

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from bot.notifications import (
    send_attendance_sync_to_worker_via_configured_bot,
    send_public_holiday_sync_via_configured_bot,
)
from models import session_scope
from models.models import AttendanceRecord
from services.attendance_service import (
    AttendanceError,
    create_or_update_attendance_record,
    delete_attendance_record,
    get_approved_leave_for_day,
    get_attendance_record,
    get_attendance_for_date,
    get_worker_by_id,
    list_attendance_records,
    list_workers,
    update_attendance_record,
)
from services.leave_service import (
    LeaveError,
    admin_upsert_single_day_leave,
    approved_leaves_in_range,
    delete_leave_request,
    leave_label,
    leave_is_partial_day,
    leave_report_code,
    normalize_leave_day_portion,
)
from services.public_holiday_service import (
    PublicHolidayError,
    get_public_holiday_for_date,
    list_public_holidays_in_range,
    public_holiday_label,
    upsert_public_holiday_for_date,
    delete_public_holiday,
)
from services.site_service import list_sites
from web.dependencies import (
    FormValidationError,
    parse_date,
    parse_datetime_local,
    require_admin,
    require_csrf,
    templates,
    today_local,
)
from web.security import SecurityError

router = APIRouter(prefix="/attendance")


def _period_context(month: Optional[int], year: Optional[int]) -> tuple[int, int]:
    today = today_local()
    return month or today.month, year or today.year


def _attendance_redirect_url(
    request: Request,
    *,
    month: int,
    year: int,
    site_id: Optional[int] = None,
) -> str:
    url = request.url_for("attendance").include_query_params(month=month, year=year)
    if site_id:
        url = url.include_query_params(site_id=site_id)
    return str(url)


def _attendance_sync_payload(record: Optional[AttendanceRecord]) -> Optional[dict[str, object]]:
    if not record or record.source_chat_id is None or not record.worker:
        return None
    return {
        "worker_telegram_id": record.worker.telegram_user_id,
        "attendance_date": record.attendance_date,
        "check_in_at": record.check_in_at,
        "check_out_at": record.check_out_at,
        "notes": record.notes,
    }


def _attendance_record_symbol(record: AttendanceRecord) -> str:
    if record.check_in_at and record.check_out_at:
        return "P/C"
    if record.check_in_at:
        return "P"
    if record.check_out_at:
        return "OUT"
    return "REC"


def _attendance_record_summary(record: AttendanceRecord) -> str:
    if record.check_in_at and record.check_out_at:
        return f'{record.check_in_at.strftime("%H:%M")} - {record.check_out_at.strftime("%H:%M")}'
    if record.check_in_at:
        return f'IN {record.check_in_at.strftime("%H:%M")}'
    if record.check_out_at:
        return f'OUT {record.check_out_at.strftime("%H:%M")}'
    return "Recorded attendance"


async def _notify_worker_about_attendance_change(
    record: Optional[AttendanceRecord],
    *,
    action: str,
) -> bool:
    payload = _attendance_sync_payload(record)
    if not payload:
        return False
    return await send_attendance_sync_to_worker_via_configured_bot(action=action, **payload)


async def _notify_public_holiday_change(
    public_holiday: Optional[object],
    *,
    action: str,
) -> bool:
    if not public_holiday:
        return False
    site_name = getattr(public_holiday, "site_name", None)
    if site_name is None and getattr(public_holiday, "site", None) is not None:
        site_name = public_holiday.site.name
    return await send_public_holiday_sync_via_configured_bot(
        holiday_name=public_holiday.name,
        holiday_date=public_holiday.holiday_date,
        site_id=public_holiday.site_id,
        site_name=site_name,
        notes=public_holiday.notes,
        action=action,
    )


def _attendance_grid_cell(
    record: Optional[AttendanceRecord],
    *,
    leave_request: Optional[object],
    public_holiday: Optional[object],
    current_date: date,
) -> dict[str, object]:
    status_label = "Empty"
    status_class = "is-empty"
    symbol = "-"
    time_summary = ""
    entry_mode = "attendance"
    leave_day_portion = normalize_leave_day_portion(getattr(leave_request, "day_portion", None) if leave_request else None)
    leave_reason_value = leave_request.reason if leave_request and leave_request.reason else ""
    attendance_notes_value = record.notes if record and record.notes else ""
    notes_value = leave_reason_value or attendance_notes_value
    leave_locked = False
    leave_message = ""
    leave_request_id = None
    public_holiday_id = None

    if record and leave_request:
        leave_request_id = leave_request.id
        entry_mode = leave_request.leave_type
        status_label = f'Attendance + {leave_label(leave_request.leave_type, day_portion=leave_day_portion)}'
        status_class = f'is-recorded is-leave is-{leave_request.leave_type}'
        symbol = f'{_attendance_record_symbol(record)}/{leave_report_code(leave_request.leave_type, day_portion=leave_day_portion)}'
        time_summary = (
            f'{_attendance_record_summary(record)} | '
            f'{leave_label(leave_request.leave_type, day_portion=leave_day_portion)}'
        )
    elif record:
        symbol = _attendance_record_symbol(record)
        time_summary = _attendance_record_summary(record)
        if record.check_in_at and record.check_out_at:
            status_label = "Complete"
            status_class = "is-complete"
        elif record.check_in_at:
            status_label = "Checked in"
            status_class = "is-present"
        elif record.check_out_at:
            status_label = "Checked out"
            status_class = "is-recorded"
        else:
            status_label = "Recorded"
            status_class = "is-recorded"
    elif leave_request:
        status_label = leave_label(leave_request.leave_type, day_portion=leave_day_portion)
        status_class = f'is-leave is-{leave_request.leave_type}'
        symbol = leave_report_code(leave_request.leave_type, day_portion=leave_day_portion)
        entry_mode = leave_request.leave_type
        leave_request_id = leave_request.id
        if leave_request.start_date != leave_request.end_date:
            leave_locked = True
            leave_message = (
                f"Part of a multi-day leave request: {leave_request.start_date.isoformat()} "
                f"to {leave_request.end_date.isoformat()}."
            )
            time_summary = "Edit from Leave Requests"
        elif leave_is_partial_day(leave_day_portion):
            time_summary = "Approved half-day leave"
        else:
            time_summary = "Approved leave"
    elif public_holiday:
        status_label = public_holiday_label(public_holiday) or "Public Holiday"
        status_class = "is-public-holiday"
        symbol = "PH"
        entry_mode = "public_holiday"
        notes_value = public_holiday.name
        public_holiday_id = public_holiday.id
        time_summary = f'{public_holiday.site.name if public_holiday.site else "Global"} holiday'

    if leave_request and leave_request.start_date != leave_request.end_date:
        leave_locked = True
        leave_message = (
            f"Part of a multi-day leave request: {leave_request.start_date.isoformat()} "
            f"to {leave_request.end_date.isoformat()}."
        )
        if not record:
            time_summary = "Edit from Leave Requests"

    return {
        "record": record,
        "leave_request": leave_request,
        "leave_request_id": leave_request_id,
        "public_holiday": public_holiday,
        "public_holiday_id": public_holiday_id,
        "day": current_date.day,
        "date": current_date,
        "date_iso": current_date.isoformat(),
        "day_label": f"{current_date.day} {calendar.day_abbr[current_date.weekday()]}",
        "is_weekend": current_date.weekday() >= 5,
        "status_label": status_label,
        "status_class": status_class,
        "symbol": symbol,
        "time_summary": time_summary,
        "has_note": bool(
            (record and record.notes)
            or (leave_request and leave_request.reason)
            or (public_holiday and (public_holiday.name or public_holiday.notes))
        ),
        "entry_mode": entry_mode,
        "notes_value": notes_value,
        "leave_day_portion": leave_day_portion,
        "leave_reason_value": leave_reason_value,
        "attendance_notes_value": attendance_notes_value,
        "leave_locked": leave_locked,
        "leave_message": leave_message,
    }


def _build_attendance_grid(
    *,
    workers: list[object],
    records: list[AttendanceRecord],
    approved_leaves: list[object],
    public_holidays: list[object],
    month: int,
    year: int,
) -> dict[str, object]:
    _, days_in_month = calendar.monthrange(year, month)
    days = []
    for day_number in range(1, days_in_month + 1):
        current_date = date(year, month, day_number)
        days.append(
            {
                "day": day_number,
                "date": current_date,
                "date_iso": current_date.isoformat(),
                "weekday_label": calendar.day_abbr[current_date.weekday()],
                "is_weekend": current_date.weekday() >= 5,
            }
        )

    record_lookup = {(record.worker_id, record.attendance_date): record for record in records}
    leave_lookup: dict[tuple[int, date], object] = {}
    for leave_request in approved_leaves:
        current_date = max(leave_request.start_date, date(year, month, 1))
        final_date = min(leave_request.end_date, date(year, month, days_in_month))
        while current_date <= final_date:
            leave_lookup[(leave_request.worker_id, current_date)] = leave_request
            current_date = date.fromordinal(current_date.toordinal() + 1)
    public_holiday_lookup = {
        (public_holiday.site_id, public_holiday.holiday_date): public_holiday for public_holiday in public_holidays
    }
    rows: list[dict[str, object]] = []
    for worker in workers:
        cells = []
        present_days = 0
        completed_days = 0
        for day_info in days:
            record = record_lookup.get((worker.id, day_info["date"]))
            leave_request = leave_lookup.get((worker.id, day_info["date"]))
            public_holiday = public_holiday_lookup.get((getattr(worker, "site_id", None), day_info["date"]))
            if public_holiday is None:
                public_holiday = public_holiday_lookup.get((None, day_info["date"]))
            if record and record.check_in_at:
                present_days += 1
                if record.check_out_at:
                    completed_days += 1
            cells.append(
                _attendance_grid_cell(
                    record,
                    leave_request=leave_request,
                    public_holiday=public_holiday,
                    current_date=day_info["date"],
                )
            )
        rows.append(
            {
                "worker": worker,
                "cells": cells,
                "present_days": present_days,
                "completed_days": completed_days,
            }
        )

    return {"days": days, "rows": rows, "days_in_month": days_in_month}


async def _attendance_page_context(
    *,
    month: int,
    year: int,
    record_id: Optional[int] = None,
    site_id: Optional[int] = None,
    form_data: Optional[dict[str, object]] = None,
) -> dict[str, object]:
    _, days_in_month = calendar.monthrange(year, month)
    start_date = date(year, month, 1)
    end_date = date(year, month, days_in_month)
    async with session_scope() as session:
        records = await list_attendance_records(session, month=month, year=year, site_id=site_id)
        worker_items = await list_workers(session, site_id=site_id)
        worker_ids = {worker.id for worker in worker_items}
        leave_items = await approved_leaves_in_range(session, start_date=start_date, end_date=end_date)
        holiday_items = await list_public_holidays_in_range(session, start_date=start_date, end_date=end_date)
        sites = await list_sites(session)
        record = await get_attendance_record(session, record_id) if record_id else None
    approved_leave_items = [leave for leave in leave_items if leave.worker_id in worker_ids]
    return {
        "records": records,
        "workers": worker_items,
        "attendance_grid": _build_attendance_grid(
            workers=list(worker_items),
            records=list(records),
            approved_leaves=approved_leave_items,
            public_holidays=list(holiday_items),
            month=month,
            year=year,
        ),
        "sites": sites,
        "record": record,
        "selected_month": month,
        "selected_year": year,
        "selected_site_id": site_id,
        "form_data": form_data or {},
    }


@router.get("", response_class=HTMLResponse, name="attendance")
async def attendance(
    request: Request,
    month: Optional[int] = None,
    year: Optional[int] = None,
    site_id: Optional[int] = None,
) -> Response:
    redirect = require_admin(request)
    if redirect:
        return redirect

    selected_month, selected_year = _period_context(month, year)
    context = await _attendance_page_context(month=selected_month, year=selected_year, site_id=site_id)
    return templates.TemplateResponse(request, "attendance.html", {"error": None, **context})


@router.get("/{record_id}/edit", response_class=HTMLResponse, name="attendance_edit")
async def attendance_edit(
    request: Request,
    record_id: int,
    month: Optional[int] = None,
    year: Optional[int] = None,
    site_id: Optional[int] = None,
) -> Response:
    redirect = require_admin(request)
    if redirect:
        return redirect

    selected_month, selected_year = _period_context(month, year)
    context = await _attendance_page_context(
        month=selected_month,
        year=selected_year,
        record_id=record_id,
        site_id=site_id,
    )
    return templates.TemplateResponse(request, "attendance.html", {"error": None, **context})


@router.post("/grid/save", name="attendance_grid_save")
async def attendance_grid_save(
    request: Request,
    worker_id: int = Form(...),
    attendance_date: str = Form(...),
    entry_mode: str = Form("attendance"),
    leave_day_portion: str = Form("full"),
    check_in_at: str = Form(""),
    check_out_at: str = Form(""),
    notes: str = Form(""),
    month: Optional[int] = Form(None),
    year: Optional[int] = Form(None),
    site_id: Optional[int] = Form(None),
    csrf_token: str = Form(""),
) -> Response:
    redirect = require_admin(request)
    if redirect:
        return redirect

    selected_month, selected_year = _period_context(month, year)
    synced_record: Optional[AttendanceRecord] = None
    synced_public_holiday: Optional[object] = None
    public_holiday_action: Optional[str] = None

    try:
        require_csrf(request, csrf_token)
        target_date = parse_date(attendance_date)
        async with session_scope() as session:
            existing_record = await get_attendance_for_date(session, worker_id=worker_id, attendance_date=target_date)
            existing_leave = await get_approved_leave_for_day(session, worker_id=worker_id, target_date=target_date)
            worker = await get_worker_by_id(session, worker_id)
            if not worker:
                raise AttendanceError("Worker not found.")
            holiday_site_id = site_id if site_id is not None else worker.site_id
            existing_public_holiday = await get_public_holiday_for_date(
                session,
                target_date=target_date,
                site_id=holiday_site_id,
            )

            if entry_mode == "clear":
                if existing_record:
                    await delete_attendance_record(session, existing_record)
                if existing_leave:
                    if existing_leave.start_date != target_date or existing_leave.end_date != target_date:
                        raise LeaveError("This date is part of a multi-day leave request. Edit it from the Leave Requests page.")
                    await delete_leave_request(session, existing_leave)
                elif existing_public_holiday:
                    setattr(
                        existing_public_holiday,
                        "site_name",
                        existing_public_holiday.site.name if getattr(existing_public_holiday, "site", None) else None,
                    )
                    synced_public_holiday = existing_public_holiday
                    public_holiday_action = "deleted"
                    await delete_public_holiday(session, existing_public_holiday)
            elif entry_mode == "attendance":
                parsed_check_in = parse_datetime_local(check_in_at)
                parsed_check_out = parse_datetime_local(check_out_at)
                cleaned_notes = (notes or "").strip()
                if not existing_record and not parsed_check_in and not parsed_check_out and not cleaned_notes:
                    raise FormValidationError("Add attendance times or choose a leave type before saving this day.")
                if existing_leave:
                    if existing_leave.start_date != target_date or existing_leave.end_date != target_date:
                        raise LeaveError("This date is part of a multi-day leave request. Edit it from the Leave Requests page.")
                    await delete_leave_request(session, existing_leave)
                saved_record = await create_or_update_attendance_record(
                    session,
                    worker_id=worker_id,
                    attendance_date=target_date,
                    check_in_at=parsed_check_in,
                    check_out_at=parsed_check_out,
                    notes=cleaned_notes,
                )
                synced_record = await get_attendance_record(session, saved_record.id)
            elif entry_mode in {"annual", "mc", "emergency"}:
                parsed_check_in = parse_datetime_local(check_in_at)
                parsed_check_out = parse_datetime_local(check_out_at)
                await admin_upsert_single_day_leave(
                    session,
                    worker_id=worker_id,
                    leave_type=entry_mode,
                    target_date=target_date,
                    day_portion=leave_day_portion,
                    reason=notes,
                )
                if leave_is_partial_day(leave_day_portion):
                    if parsed_check_in or parsed_check_out:
                        saved_record = await create_or_update_attendance_record(
                            session,
                            worker_id=worker_id,
                            attendance_date=target_date,
                            check_in_at=parsed_check_in,
                            check_out_at=parsed_check_out,
                            notes=existing_record.notes if existing_record else None,
                        )
                        synced_record = await get_attendance_record(session, saved_record.id)
                    elif existing_record:
                        await delete_attendance_record(session, existing_record)
                elif existing_record:
                    await delete_attendance_record(session, existing_record)
            elif entry_mode == "public_holiday":
                holiday_name = (notes or "").strip() or "Public Holiday"
                holiday_already_exists = existing_public_holiday is not None
                synced_public_holiday = await upsert_public_holiday_for_date(
                    session,
                    holiday_date=target_date,
                    site_id=holiday_site_id,
                    name=holiday_name,
                    notes=None,
                )
                setattr(synced_public_holiday, "site_name", worker.site.name if worker.site else None)
                public_holiday_action = "saved" if holiday_already_exists else "created"
            else:
                raise FormValidationError("Please choose a supported day mode.")
    except (AttendanceError, FormValidationError, SecurityError, LeaveError, PublicHolidayError) as exc:
        context = await _attendance_page_context(
            month=selected_month,
            year=selected_year,
            site_id=site_id,
        )
        return templates.TemplateResponse(
            request,
            "attendance.html",
            {"error": str(exc), **context},
            status_code=400,
        )

    await _notify_worker_about_attendance_change(synced_record, action="saved")
    if synced_public_holiday and public_holiday_action:
        await _notify_public_holiday_change(synced_public_holiday, action=public_holiday_action)
    return RedirectResponse(
        url=_attendance_redirect_url(
            request,
            month=selected_month,
            year=selected_year,
            site_id=site_id,
        ),
        status_code=303,
    )


@router.post("", name="attendance_create")
async def attendance_create(
    request: Request,
    worker_id: int = Form(...),
    attendance_date: str = Form(...),
    check_in_at: str = Form(""),
    check_out_at: str = Form(""),
    notes: str = Form(""),
    month: Optional[int] = Form(None),
    year: Optional[int] = Form(None),
    site_id: Optional[int] = Form(None),
    csrf_token: str = Form(""),
) -> Response:
    redirect = require_admin(request)
    if redirect:
        return redirect

    selected_month, selected_year = _period_context(month, year)
    synced_record: Optional[AttendanceRecord] = None

    try:
        require_csrf(request, csrf_token)
        async with session_scope() as session:
            saved_record = await create_or_update_attendance_record(
                session,
                worker_id=worker_id,
                attendance_date=parse_date(attendance_date),
                check_in_at=parse_datetime_local(check_in_at),
                check_out_at=parse_datetime_local(check_out_at),
                notes=notes,
            )
            synced_record = await get_attendance_record(session, saved_record.id)
    except (AttendanceError, FormValidationError, SecurityError) as exc:
        context = await _attendance_page_context(
            month=selected_month,
            year=selected_year,
            site_id=site_id,
            form_data={
                "worker_id": worker_id,
                "attendance_date": attendance_date,
                "check_in_at": check_in_at,
                "check_out_at": check_out_at,
                "notes": notes,
            },
        )
        return templates.TemplateResponse(
            request,
            "attendance.html",
            {"error": str(exc), **context},
            status_code=400,
        )
    await _notify_worker_about_attendance_change(synced_record, action="saved")
    return RedirectResponse(
        url=_attendance_redirect_url(
            request,
            month=selected_month,
            year=selected_year,
            site_id=site_id,
        ),
        status_code=303,
    )


@router.post("/{record_id}/edit", name="attendance_update")
async def attendance_update(
    request: Request,
    record_id: int,
    worker_id: int = Form(...),
    attendance_date: str = Form(...),
    check_in_at: str = Form(""),
    check_out_at: str = Form(""),
    notes: str = Form(""),
    month: Optional[int] = Form(None),
    year: Optional[int] = Form(None),
    site_id: Optional[int] = Form(None),
    csrf_token: str = Form(""),
) -> Response:
    redirect = require_admin(request)
    if redirect:
        return redirect

    selected_month, selected_year = _period_context(month, year)
    synced_record: Optional[AttendanceRecord] = None

    try:
        require_csrf(request, csrf_token)
        new_date = parse_date(attendance_date)
        async with session_scope() as session:
            record = await get_attendance_record(session, record_id)
            if not record:
                return RedirectResponse(
                    url=_attendance_redirect_url(
                        request,
                        month=selected_month,
                        year=selected_year,
                        site_id=site_id,
                    ),
                    status_code=303,
                )
            saved_record = await update_attendance_record(
                session,
                record,
                worker_id=worker_id,
                attendance_date=new_date,
                check_in_at=parse_datetime_local(check_in_at),
                check_out_at=parse_datetime_local(check_out_at),
                notes=notes,
            )
            synced_record = await get_attendance_record(session, saved_record.id)
    except (AttendanceError, FormValidationError, SecurityError) as exc:
        context = await _attendance_page_context(
            month=selected_month,
            year=selected_year,
            record_id=record_id,
            site_id=site_id,
            form_data={
                "worker_id": worker_id,
                "attendance_date": attendance_date,
                "check_in_at": check_in_at,
                "check_out_at": check_out_at,
                "notes": notes,
            },
        )
        return templates.TemplateResponse(
            request,
            "attendance.html",
            {"error": str(exc), **context},
            status_code=400,
        )
    await _notify_worker_about_attendance_change(synced_record, action="saved")
    return RedirectResponse(
        url=_attendance_redirect_url(
            request,
            month=selected_month,
            year=selected_year,
            site_id=site_id,
        ),
        status_code=303,
    )


@router.post("/{record_id}/delete", name="attendance_delete")
async def attendance_delete(
    request: Request,
    record_id: int,
    month: Optional[int] = Form(None),
    year: Optional[int] = Form(None),
    site_id: Optional[int] = Form(None),
    csrf_token: str = Form(""),
) -> Response:
    redirect = require_admin(request)
    if redirect:
        return redirect

    selected_month, selected_year = _period_context(month, year)
    deleted_record: Optional[AttendanceRecord] = None

    try:
        require_csrf(request, csrf_token)
        async with session_scope() as session:
            record = await get_attendance_record(session, record_id)
            if record:
                deleted_record = record
                await delete_attendance_record(session, record)
    except SecurityError as exc:
        context = await _attendance_page_context(
            month=selected_month,
            year=selected_year,
            site_id=site_id,
        )
        return templates.TemplateResponse(
            request,
            "attendance.html",
            {"error": str(exc), **context},
            status_code=400,
        )
    await _notify_worker_about_attendance_change(deleted_record, action="deleted")
    return RedirectResponse(
        url=_attendance_redirect_url(
            request,
            month=selected_month,
            year=selected_year,
            site_id=site_id,
        ),
        status_code=303,
    )
