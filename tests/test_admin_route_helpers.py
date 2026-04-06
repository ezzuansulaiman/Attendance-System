from fastapi import FastAPI
from starlette.requests import Request

from web.attendance_routes import _attendance_redirect_url
from web.leave_routes import _leaves_redirect_url


def _request_for_path(path: str) -> Request:
    app = FastAPI()

    @app.get("/", name="dashboard")
    async def dashboard() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/attendance", name="attendance")
    async def attendance() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/leaves", name="leaves")
    async def leaves() -> dict[str, str]:
        return {"status": "ok"}

    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "headers": [],
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
        "app": app,
    }
    return Request(scope)


def test_attendance_redirect_url_preserves_period_and_site() -> None:
    request = _request_for_path("/attendance")

    url = _attendance_redirect_url(request, month=4, year=2026, site_id=3)

    assert url.endswith("/attendance?month=4&year=2026&site_id=3")


def test_leaves_redirect_url_can_return_to_dashboard() -> None:
    request = _request_for_path("/leaves")

    url = _leaves_redirect_url(request, site_id=7, return_to="dashboard")

    assert url.endswith("/?site_id=7")
