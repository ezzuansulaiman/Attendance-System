from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware

from models.database import init_database
from web.attendance_routes import router as attendance_router
from web.auth_routes import router as auth_router
from web.dashboard_routes import router as dashboard_router
from web.dependencies import settings
from web.leave_routes import router as leave_router
from web.report_routes import router as report_router
from web.site_routes import router as site_router
from web.worker_routes import router as worker_router


@asynccontextmanager
async def _lifespan(_: FastAPI):
    await init_database()
    yield


def _initialize_database_for_app() -> None:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(init_database())


def create_app() -> FastAPI:
    _initialize_database_for_app()
    app = FastAPI(title="Telegram Attendance Dashboard", lifespan=_lifespan)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret,
        same_site="lax",
        https_only=settings.session_https_only,
        session_cookie="attendance_admin_session",
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(auth_router)
    app.include_router(dashboard_router)
    app.include_router(site_router)
    app.include_router(worker_router)
    app.include_router(attendance_router)
    app.include_router(leave_router)
    app.include_router(report_router)
    return app
