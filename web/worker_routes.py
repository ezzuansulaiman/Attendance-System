from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from models import session_scope
from services.attendance_service import AttendanceError, create_worker, get_worker_by_id, list_workers, update_worker
from services.site_service import list_sites
from web.dependencies import require_admin, templates

router = APIRouter(prefix="/workers")


@router.get("", response_class=HTMLResponse, name="workers")
async def workers(request: Request) -> Response:
    redirect = require_admin(request)
    if redirect:
        return redirect

    async with session_scope() as session:
        worker_items = await list_workers(session)
        sites = await list_sites(session)
    return templates.TemplateResponse(
        request,
        "workers.html",
        {"workers": worker_items, "worker": None, "sites": sites, "error": None},
    )


@router.post("", name="workers_create")
async def workers_create(
    request: Request,
    full_name: str = Form(...),
    telegram_user_id: int = Form(...),
    ic_number: str = Form(""),
    employee_code: str = Form(""),
    site_id: Optional[int] = Form(None),
    is_active: Optional[str] = Form(None),
) -> Response:
    redirect = require_admin(request)
    if redirect:
        return redirect

    async with session_scope() as session:
        try:
            await create_worker(
                session,
                full_name=full_name,
                telegram_user_id=telegram_user_id,
                ic_number=ic_number,
                employee_code=employee_code,
                site_id=site_id,
                is_active=bool(is_active),
            )
        except AttendanceError as exc:
            worker_items = await list_workers(session)
            sites = await list_sites(session)
            return templates.TemplateResponse(
                request,
                "workers.html",
                {"workers": worker_items, "worker": None, "sites": sites, "error": str(exc)},
                status_code=400,
            )
    return RedirectResponse(url=request.url_for("workers"), status_code=303)


@router.get("/{worker_id}/edit", response_class=HTMLResponse, name="workers_edit")
async def workers_edit(request: Request, worker_id: int) -> Response:
    redirect = require_admin(request)
    if redirect:
        return redirect

    async with session_scope() as session:
        worker = await get_worker_by_id(session, worker_id)
        worker_items = await list_workers(session)
        sites = await list_sites(session)
    return templates.TemplateResponse(
        request,
        "workers.html",
        {"workers": worker_items, "worker": worker, "sites": sites, "error": None},
    )


@router.post("/{worker_id}/edit", name="workers_update")
async def workers_update(
    request: Request,
    worker_id: int,
    full_name: str = Form(...),
    telegram_user_id: int = Form(...),
    ic_number: str = Form(""),
    employee_code: str = Form(""),
    site_id: Optional[int] = Form(None),
    is_active: Optional[str] = Form(None),
) -> Response:
    redirect = require_admin(request)
    if redirect:
        return redirect

    async with session_scope() as session:
        worker = await get_worker_by_id(session, worker_id)
        if not worker:
            return RedirectResponse(url=request.url_for("workers"), status_code=303)
        try:
            await update_worker(
                session,
                worker,
                full_name=full_name,
                telegram_user_id=telegram_user_id,
                ic_number=ic_number,
                employee_code=employee_code,
                site_id=site_id,
                is_active=bool(is_active),
            )
        except AttendanceError as exc:
            worker_items = await list_workers(session)
            sites = await list_sites(session)
            return templates.TemplateResponse(
                request,
                "workers.html",
                {"workers": worker_items, "worker": worker, "sites": sites, "error": str(exc)},
                status_code=400,
            )
    return RedirectResponse(url=request.url_for("workers"), status_code=303)
