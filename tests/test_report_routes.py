from __future__ import annotations

import re

from fastapi.testclient import TestClient

from services.pdf_generator import PdfExportError
from web.app import create_app
from web.dependencies import settings


def _login(client: TestClient) -> None:
    login_page = client.get("/login")
    assert login_page.status_code == 200

    marker = 'name="csrf_token" value="'
    start = login_page.text.find(marker)
    assert start != -1
    start += len(marker)
    end = login_page.text.find('"', start)
    csrf_token = login_page.text[start:end]

    response = client.post(
        "/login",
        data={
            "username": settings.web_username,
            "password": settings.web_password,
            "csrf_token": csrf_token,
        },
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_monthly_pdf_report_download_route_returns_attachment() -> None:
    client = TestClient(create_app())
    _login(client)

    response = client.get("/reports/monthly?year=2026&month=4", follow_redirects=False)

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert re.search(
        r'attachment; filename="attendance-2026-04-\d{8}-\d{6}\.pdf"',
        response.headers["content-disposition"],
    )
    assert response.headers["cache-control"] == "no-store, no-cache, must-revalidate, max-age=0"
    assert response.headers["pragma"] == "no-cache"
    assert response.headers["expires"] == "0"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.content.startswith(b"%PDF")


def test_monthly_excel_report_download_route_returns_attachment() -> None:
    client = TestClient(create_app())
    _login(client)

    response = client.get("/reports/monthly/excel?year=2026&month=4", follow_redirects=False)

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert re.search(
        r'attachment; filename="attendance-2026-04-\d{8}-\d{6}\.xlsx"',
        response.headers["content-disposition"],
    )
    assert response.headers["cache-control"] == "no-store, no-cache, must-revalidate, max-age=0"
    assert response.headers["pragma"] == "no-cache"
    assert response.headers["expires"] == "0"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.content.startswith(b"PK")


def test_monthly_pdf_report_download_route_returns_controlled_error_on_pdf_failure(monkeypatch) -> None:
    client = TestClient(create_app())
    _login(client)

    async def _fake_generate_monthly_attendance_pdf(*args, **kwargs):
        raise PdfExportError("boom")

    monkeypatch.setattr("web.report_routes.generate_monthly_attendance_pdf", _fake_generate_monthly_attendance_pdf)

    response = client.get("/reports/monthly?year=2026&month=4", follow_redirects=False)

    assert response.status_code == 500
    assert response.headers["content-type"].startswith("text/plain")
    assert "Unable to generate the PDF report right now." in response.text
