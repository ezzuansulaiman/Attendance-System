from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from bot.notifications import send_attendance_sync_to_worker_via_configured_bot
from models import session_scope
from models.models import AttendanceRecord
from services.attendance_service import (
    AttendanceError,
    create_or_update_attendance_record,
    delete_attendance_record,
    get_attendance_record,
    list_attendance_records,
    list_workers,
    update_attendance_record,
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


async def _notify_worker_about_attendance_change(
    record: Optional[AttendanceRecord],
    *,
    action: str,
) -> bool:
    payload = _attendance_sync_payload(record)
    if not payload:
        return False
    return await send_attendance_sync_to_worker_via_configured_bot(action=action, **payload)


async def _attendance_page_context(
    *,
    month: int,
    year: int,
    record_id: Optional[int] = None,
    site_id: Optional[int] = None,
    form_data: Optional[dict[str, object]] = None,
) -> dict[str, object]:
    async with session_scope() as session:
        records = await list_attendance_records(session, month=month, year=year, site_id=site_id)
        worker_items = await list_workers(session, site_id=site_id)
        sites = await list_sites(session)
        record = await get_attendance_record(session, record_id) if record_id else None
    return {
        "records": records,
        "workers": worker_items,
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
