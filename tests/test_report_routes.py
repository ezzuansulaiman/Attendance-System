from __future__ import annotations

from fastapi.testclient import TestClient

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
    assert 'attachment; filename="attendance-2026-04.pdf"' in response.headers["content-disposition"]
    assert response.content.startswith(b"%PDF")


def test_monthly_excel_report_download_route_returns_attachment() -> None:
    client = TestClient(create_app())
    _login(client)

    response = client.get("/reports/monthly/excel?year=2026&month=4", follow_redirects=False)

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert 'attachment; filename="attendance-2026-04.xlsx"' in response.headers["content-disposition"]
    assert response.content.startswith(b"PK")
