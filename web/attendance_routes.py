from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from models import session_scope
from services.attendance_service import (
    AttendanceError,
    create_or_update_attendance_record,
    delete_attendance_record,
    get_attendance_record,
    list_attendance_records,
    list_workers,
)
from services.site_service import list_sites
from web.dependencies import parse_date, parse_datetime_local, require_admin, templates, today_local

router = APIRouter(prefix="/attendance")


def _period_context(month: Optional[int], year: Optional[int]) -> tuple[int, int]:
    today = today_local()
    return month or today.month, year or today.year


async def _attendance_page_context(
    *,
    month: int,
    year: int,
    record_id: Optional[int] = None,
    site_id: Optional[int] = None,
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
    return templates.TemplateResponse("attendance.html", {"request": request, "error": None, **context})


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
    return templates.TemplateResponse("attendance.html", {"request": request, "error": None, **context})


@router.post("", name="attendance_create")
async def attendance_create(
    request: Request,
    worker_id: int = Form(...),
    attendance_date: str = Form(...),
    check_in_at: str = Form(""),
    check_out_at: str = Form(""),
    notes: str = Form(""),
) -> Response:
    redirect = require_admin(request)
    if redirect:
        return redirect

    try:
        async with session_scope() as session:
            await create_or_update_attendance_record(
                session,
                worker_id=worker_id,
                attendance_date=parse_date(attendance_date),
                check_in_at=parse_datetime_local(check_in_at),
                check_out_at=parse_datetime_local(check_out_at),
                notes=notes,
            )
    except AttendanceError as exc:
        selected_month, selected_year = _period_context(None, None)
        context = await _attendance_page_context(month=selected_month, year=selected_year)
        return templates.TemplateResponse(
            "attendance.html",
            {"request": request, "error": str(exc), **context},
            status_code=400,
        )
    return RedirectResponse(url=request.url_for("attendance"), status_code=303)


@router.post("/{record_id}/edit", name="attendance_update")
async def attendance_update(
    request: Request,
    record_id: int,
    worker_id: int = Form(...),
    attendance_date: str = Form(...),
    check_in_at: str = Form(""),
    check_out_at: str = Form(""),
    notes: str = Form(""),
) -> Response:
    redirect = require_admin(request)
    if redirect:
        return redirect

    new_date = parse_date(attendance_date)
    try:
        async with session_scope() as session:
            record = await get_attendance_record(session, record_id)
            if not record:
                return RedirectResponse(url=request.url_for("attendance"), status_code=303)
            if record.worker_id != worker_id or record.attendance_date != new_date:
                await delete_attendance_record(session, record)
            await create_or_update_attendance_record(
                session,
                worker_id=worker_id,
                attendance_date=new_date,
                check_in_at=parse_datetime_local(check_in_at),
                check_out_at=parse_datetime_local(check_out_at),
                notes=notes,
            )
    except AttendanceError as exc:
        selected_month, selected_year = _period_context(None, None)
        context = await _attendance_page_context(month=selected_month, year=selected_year, record_id=record_id)
        return templates.TemplateResponse(
            "attendance.html",
            {"request": request, "error": str(exc), **context},
            status_code=400,
        )
    return RedirectResponse(url=request.url_for("attendance"), status_code=303)


@router.post("/{record_id}/delete", name="attendance_delete")
async def attendance_delete(request: Request, record_id: int) -> Response:
    redirect = require_admin(request)
    if redirect:
        return redirect

    async with session_scope() as session:
        record = await get_attendance_record(session, record_id)
        if record:
            await delete_attendance_record(session, record)
    return RedirectResponse(url=request.url_for("attendance"), status_code=303)
