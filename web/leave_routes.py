from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from models import session_scope
from services.leave_service import (
    LeaveError,
    approve_leave_request,
    get_leave_request,
    list_leave_requests,
    reject_leave_request,
)
from services.site_service import list_sites
from web.dependencies import current_admin_username, require_admin, require_csrf, templates
from web.security import SecurityError

router = APIRouter(prefix="/leaves")


@router.get("", response_class=HTMLResponse, name="leaves")
async def leaves(request: Request, site_id: Optional[int] = None) -> Response:
    redirect = require_admin(request)
    if redirect:
        return redirect

    async with session_scope() as session:
        leave_items = await list_leave_requests(session, site_id=site_id)
        sites = await list_sites(session)
    return templates.TemplateResponse(
        request,
        "leaves.html",
        {"leaves": leave_items, "sites": sites, "selected_site_id": site_id},
    )


async def _review_leave(leave_id: int, *, approve: bool, reviewer: Optional[str]) -> None:
    async with session_scope() as session:
        leave_request = await get_leave_request(session, leave_id)
        if not leave_request:
            return
        notes_prefix = "Approved" if approve else "Rejected"
        review_note = f"{notes_prefix} from web dashboard"
        if reviewer:
            review_note = f"{review_note} by {reviewer}"
        try:
            if approve:
                await approve_leave_request(
                    session,
                    leave_request=leave_request,
                    admin_telegram_id=0,
                    notes=review_note,
                )
            else:
                await reject_leave_request(
                    session,
                    leave_request=leave_request,
                    admin_telegram_id=0,
                    notes=review_note,
                )
        except LeaveError:
            return


@router.post("/{leave_id}/approve", name="leaves_approve")
async def leaves_approve(request: Request, leave_id: int, csrf_token: str = Form("")) -> Response:
    redirect = require_admin(request)
    if redirect:
        return redirect

    try:
        require_csrf(request, csrf_token)
    except SecurityError as exc:
        async with session_scope() as session:
            leave_items = await list_leave_requests(session)
            sites = await list_sites(session)
        return templates.TemplateResponse(
            request,
            "leaves.html",
            {"leaves": leave_items, "sites": sites, "selected_site_id": None, "error": str(exc)},
            status_code=400,
        )
    await _review_leave(leave_id, approve=True, reviewer=current_admin_username(request))
    return RedirectResponse(url=request.url_for("leaves"), status_code=303)


@router.post("/{leave_id}/reject", name="leaves_reject")
async def leaves_reject(request: Request, leave_id: int, csrf_token: str = Form("")) -> Response:
    redirect = require_admin(request)
    if redirect:
        return redirect

    try:
        require_csrf(request, csrf_token)
    except SecurityError as exc:
        async with session_scope() as session:
            leave_items = await list_leave_requests(session)
            sites = await list_sites(session)
        return templates.TemplateResponse(
            request,
            "leaves.html",
            {"leaves": leave_items, "sites": sites, "selected_site_id": None, "error": str(exc)},
            status_code=400,
        )
    await _review_leave(leave_id, approve=False, reviewer=current_admin_username(request))
    return RedirectResponse(url=request.url_for("leaves"), status_code=303)
