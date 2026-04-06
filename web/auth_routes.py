from __future__ import annotations

import secrets

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from web.dependencies import require_csrf, settings, templates
from web.security import SecurityError, login_admin, logout_admin, verify_password

router = APIRouter()


@router.get("/login", response_class=HTMLResponse, name="login")
async def login(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "login.html", {"error": None})


@router.post("/login", name="login_post")
async def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    csrf_token: str = Form(""),
) -> Response:
    try:
        require_csrf(request, csrf_token)
    except SecurityError as exc:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": str(exc)},
            status_code=400,
        )

    valid_user = secrets.compare_digest(username, settings.web_username)
    valid_password = verify_password(
        password,
        password_hash=settings.web_password_hash,
        fallback_password=settings.web_password,
    )
    if not (valid_user and valid_password):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Invalid credentials."},
            status_code=400,
        )
    login_admin(request, username=settings.web_username)
    return RedirectResponse(url=request.url_for("dashboard"), status_code=303)


@router.post("/logout", name="logout")
async def logout(request: Request, csrf_token: str = Form("")) -> Response:
    try:
        require_csrf(request, csrf_token)
    except SecurityError as exc:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": str(exc)},
            status_code=400,
        )
    logout_admin(request)
    return RedirectResponse(url=request.url_for("login"), status_code=303)
