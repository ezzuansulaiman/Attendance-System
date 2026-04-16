from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response

from config import get_settings
from models import session_scope
from services.attendance_service import get_dashboard_summary, list_workers, recent_attendance
from services.leave_service import list_leave_requests
from services.site_service import list_sites
from web.dependencies import require_admin, templates, today_local

router = APIRouter()
settings = get_settings()


def build_telegram_config_health(*, workers: list, sites: list) -> dict[str, object]:
    sites_missing_group = [site for site in sites if site.is_active and site.telegram_group_id is None]
    workers_missing_site = [worker for worker in workers if worker.is_active and worker.site_id is None]
    workers_missing_group_mapping = [
        worker
        for worker in workers
        if worker.is_active
        and worker.site_id is not None
        and (worker.site is None or worker.site.telegram_group_id is None)
    ]
    fallback_group_missing = settings.group_id is None
    has_issues = bool(sites_missing_group or workers_missing_site or workers_missing_group_mapping or fallback_group_missing)
    return {
        "has_issues": has_issues,
        "fallback_group_missing": fallback_group_missing,
        "sites_missing_group": sites_missing_group,
        "workers_missing_site": workers_missing_site,
        "workers_missing_group_mapping": workers_missing_group_mapping,
    }


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
        all_sites = await list_sites(session, active_only=False)
        workers = await list_workers(session)
    telegram_config_health = build_telegram_config_health(workers=list(workers), sites=list(all_sites))

    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "summary": summary,
            "today": today,
            "recent_records": recent_records,
            "leave_requests": leave_requests[:10],
            "sites": sites,
            "selected_site_id": site_id,
            "telegram_config_health": telegram_config_health,
        },
    )
