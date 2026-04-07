from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from fastapi import Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from config import get_settings
from services.leave_service import leave_label
from web.security import ADMIN_SESSION_KEY, csrf_token as get_csrf_token, session_admin_username, verify_csrf_token

settings = get_settings()
local_tz = settings.local_timezone
templates = Jinja2Templates(directory="web/templates")
templates.env.globals["current_year"] = lambda: datetime.now(local_tz).year
templates.env.globals["current_month"] = lambda: datetime.now(local_tz).month
templates.env.globals["current_company_name"] = lambda: settings.company_name
templates.env.globals["csrf_token"] = get_csrf_token
templates.env.globals["leave_label"] = leave_label


class FormValidationError(ValueError):
    pass


def is_logged_in(request: Request) -> bool:
    return bool(request.session.get(ADMIN_SESSION_KEY))


def redirect_to_login(request: Request) -> RedirectResponse:
    return RedirectResponse(url=request.url_for("login"), status_code=303)


def require_admin(request: Request) -> Optional[RedirectResponse]:
    if is_logged_in(request):
        return None
    return redirect_to_login(request)


def require_csrf(request: Request, submitted_token: str) -> None:
    verify_csrf_token(request, submitted_token)


def current_admin_username(request: Request) -> Optional[str]:
    return session_admin_username(request)


def parse_datetime_local(raw_value: Optional[str]) -> Optional[datetime]:
    cleaned = (raw_value or "").strip()
    if not cleaned:
        return None
    try:
        parsed = datetime.strptime(cleaned, "%Y-%m-%dT%H:%M")
    except ValueError as exc:
        raise FormValidationError("Please use YYYY-MM-DDTHH:MM for date and time fields.") from exc
    return parsed.replace(tzinfo=local_tz)


def parse_date(raw_value: str) -> date:
    try:
        return datetime.strptime(raw_value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise FormValidationError("Please use YYYY-MM-DD for date fields.") from exc


def today_local() -> date:
    return datetime.now(local_tz).date()
