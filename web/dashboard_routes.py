from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response

from models import session_scope
from services.attendance_service import get_dashboard_summary, recent_attendance
from services.leave_service import list_leave_requests
from services.site_service import list_sites
from web.dependencies import require_admin, templates, today_local

router = APIRouter()


@router.get("/", response_class=HTMLResponse, name="dashboard")
async def dashboard(request: Request, site_id: Optional[int] = None) -> Response:
    redirect = require_admin(request)
    if redirect:
        return redirect

    today = today_local()
    async with session_scope() as session:
        summary = await get_dashboard_summary(session, target_date=today, site_id=site_id)
        recent_records = await recent_attendance(session, site_id=site_id)
        leave_requests = await list_leave_requests(session, site_id=site_id)
        sites = await list_sites(session, active_only=True)

    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "summary": summary,
            "today": today,
            "recent_records": recent_records,
            "leave_requests": leave_requests[:10],
            "sites": sites,
            "selected_site_id": site_id,
        },
    )
