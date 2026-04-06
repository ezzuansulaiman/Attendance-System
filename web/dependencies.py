from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from fastapi import Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from config import get_settings

settings = get_settings()
local_tz = settings.local_timezone
templates = Jinja2Templates(directory="web/templates")
templates.env.globals["current_year"] = lambda: datetime.now(local_tz).year
templates.env.globals["current_month"] = lambda: datetime.now(local_tz).month
templates.env.globals["current_company_name"] = lambda: settings.company_name


def is_logged_in(request: Request) -> bool:
    return bool(request.session.get("is_admin"))


def redirect_to_login(request: Request) -> RedirectResponse:
    return RedirectResponse(url=request.url_for("login"), status_code=303)


def require_admin(request: Request) -> Optional[RedirectResponse]:
    if is_logged_in(request):
        return None
    return redirect_to_login(request)


def parse_datetime_local(raw_value: Optional[str]) -> Optional[datetime]:
    cleaned = (raw_value or "").strip()
    if not cleaned:
        return None
    parsed = datetime.strptime(cleaned, "%Y-%m-%dT%H:%M")
    return parsed.replace(tzinfo=local_tz)


def parse_date(raw_value: str) -> date:
    return datetime.strptime(raw_value, "%Y-%m-%d").date()


def today_local() -> date:
    return datetime.now(local_tz).date()
