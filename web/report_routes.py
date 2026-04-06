from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import Response

from models import session_scope
from services.report_service import generate_monthly_attendance_pdf
from web.dependencies import require_admin

router = APIRouter(prefix="/reports")


@router.get("/monthly", name="monthly_report")
async def monthly_report(
    request: Request,
    year: int,
    month: int,
    site_id: Optional[int] = None,
) -> Response:
    redirect = require_admin(request)
    if redirect:
        return redirect

    async with session_scope() as session:
        pdf_bytes = await generate_monthly_attendance_pdf(session, year=year, month=month, site_id=site_id)
    filename = f"attendance-{year}-{month:02d}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
