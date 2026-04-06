from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from models import session_scope
from services.site_service import SiteError, create_site, get_site_by_id, list_sites, update_site
from web.dependencies import require_admin, templates

router = APIRouter(prefix="/sites")


@router.get("", response_class=HTMLResponse, name="sites")
async def sites(request: Request) -> Response:
    redirect = require_admin(request)
    if redirect:
        return redirect

    async with session_scope() as session:
        site_items = await list_sites(session)
    return templates.TemplateResponse(
        "sites.html",
        {"request": request, "sites": site_items, "site": None, "error": None},
    )


@router.post("", name="sites_create")
async def sites_create(
    request: Request,
    name: str = Form(...),
    code: str = Form(""),
    telegram_group_id: Optional[int] = Form(None),
    is_active: Optional[str] = Form(None),
) -> Response:
    redirect = require_admin(request)
    if redirect:
        return redirect

    async with session_scope() as session:
        try:
            await create_site(
                session,
                name=name,
                code=code,
                telegram_group_id=telegram_group_id,
                is_active=bool(is_active),
            )
        except SiteError as exc:
            site_items = await list_sites(session)
            return templates.TemplateResponse(
                "sites.html",
                {"request": request, "sites": site_items, "site": None, "error": str(exc)},
                status_code=400,
            )
    return RedirectResponse(url=request.url_for("sites"), status_code=303)


@router.get("/{site_id}/edit", response_class=HTMLResponse, name="sites_edit")
async def sites_edit(request: Request, site_id: int) -> Response:
    redirect = require_admin(request)
    if redirect:
        return redirect

    async with session_scope() as session:
        site = await get_site_by_id(session, site_id)
        site_items = await list_sites(session)
    return templates.TemplateResponse(
        "sites.html",
        {"request": request, "sites": site_items, "site": site, "error": None},
    )


@router.post("/{site_id}/edit", name="sites_update")
async def sites_update(
    request: Request,
    site_id: int,
    name: str = Form(...),
    code: str = Form(""),
    telegram_group_id: Optional[int] = Form(None),
    is_active: Optional[str] = Form(None),
) -> Response:
    redirect = require_admin(request)
    if redirect:
        return redirect

    async with session_scope() as session:
        site = await get_site_by_id(session, site_id)
        if not site:
            return RedirectResponse(url=request.url_for("sites"), status_code=303)
        try:
            await update_site(
                session,
                site,
                name=name,
                code=code,
                telegram_group_id=telegram_group_id,
                is_active=bool(is_active),
            )
        except SiteError as exc:
            site_items = await list_sites(session)
            return templates.TemplateResponse(
                "sites.html",
                {"request": request, "sites": site_items, "site": site, "error": str(exc)},
                status_code=400,
            )
    return RedirectResponse(url=request.url_for("sites"), status_code=303)
