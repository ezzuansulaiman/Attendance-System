from __future__ import annotations

import secrets

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from web.dependencies import settings, templates

router = APIRouter()


@router.get("/login", response_class=HTMLResponse, name="login")
async def login(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(request, "login.html", {"error": None})


@router.post("/login", name="login_post")
async def login_post(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
) -> Response:
    valid_user = secrets.compare_digest(username, settings.web_username)
    valid_password = secrets.compare_digest(password, settings.web_password)
    if not (valid_user and valid_password):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Invalid credentials."},
            status_code=400,
        )
    request.session["is_admin"] = True
    return RedirectResponse(url=request.url_for("dashboard"), status_code=303)


@router.get("/logout", name="logout")
async def logout(request: Request) -> RedirectResponse:
    request.session.clear()
    return RedirectResponse(url=request.url_for("login"), status_code=303)
