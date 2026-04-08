import asyncio
from datetime import date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from models.database import Base
from models.models import AttendanceRecord, LeaveRequest, PublicHoliday, Site, Worker
from services.report_service import build_monthly_attendance_report


def test_build_monthly_attendance_report_defaults_to_sepang_scope() -> None:
    with TemporaryDirectory(dir=Path.cwd()) as temp_dir:
        asyncio.run(_test_build_monthly_attendance_report_defaults_to_sepang_scope(Path(temp_dir)))


def test_build_monthly_attendance_report_includes_legacy_worker_with_null_active_flag() -> None:
    with TemporaryDirectory(dir=Path.cwd()) as temp_dir:
        asyncio.run(_test_build_monthly_attendance_report_includes_legacy_worker_with_null_active_flag(Path(temp_dir)))


async def _test_build_monthly_attendance_report_defaults_to_sepang_scope(tmp_path: Path) -> None:
    database_path = tmp_path / "report-scope.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path.as_posix()}")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async with session_factory() as session:
            sepang = Site(name="Sepang", code="SEP", is_active=True)
            klang = Site(name="Klang", code="KLG", is_active=True)
            session.add_all([sepang, klang])
            await session.flush()

            sepang_worker = Worker(
                telegram_user_id=101,
                full_name="Sepang Worker",
                site_id=sepang.id,
                is_active=True,
            )
            klang_worker = Worker(
                telegram_user_id=202,
                full_name="Klang Worker",
                site_id=klang.id,
                is_active=True,
            )
            session.add_all([sepang_worker, klang_worker])
            await session.flush()

            session.add_all(
                [
                    AttendanceRecord(
                        worker_id=sepang_worker.id,
                        attendance_date=date(2026, 4, 1),
                        check_in_at=datetime(2026, 4, 1, 8, 0),
                    ),
                    AttendanceRecord(
                        worker_id=sepang_worker.id,
                        attendance_date=date(2026, 4, 3),
                        check_in_at=datetime(2026, 4, 3, 8, 0),
                    ),
                    AttendanceRecord(
                        worker_id=klang_worker.id,
                        attendance_date=date(2026, 4, 1),
                        check_in_at=datetime(2026, 4, 1, 8, 30),
                    ),
                    LeaveRequest(
                        worker_id=sepang_worker.id,
                        leave_type="annual",
                        day_portion="pm",
                        start_date=date(2026, 4, 3),
                        end_date=date(2026, 4, 3),
                        reason="Half day annual leave",
                        status="approved",
                    ),
                    PublicHoliday(
                        name="Labour Day",
                        holiday_date=date(2026, 4, 2),
                        site_id=sepang.id,
                    ),
                ]
            )
            await session.commit()

            import services.report_service as report_service

            original_get_settings = report_service.get_settings
            report_service.get_settings = lambda: SimpleNamespace(
                company_name="KHSAR",
                default_site_name="Sepang",
            )
            try:
                report = await build_monthly_attendance_report(session, year=2026, month=4)
            finally:
                report_service.get_settings = original_get_settings

            assert report["site_name"] == "Sepang Region"
            assert [row["worker_name"] for row in report["rows"]] == ["Sepang Worker"]
            assert {row["worker_name"] for row in report["detail_rows"]} == {"Sepang Worker"}
            assert report["rows"][0]["days"][1] == "PH"
            assert report["rows"][0]["days"][2] == "P/ALP"
            assert any("Half day annual leave" in row["notes"] for row in report["detail_rows"])
    finally:
        await engine.dispose()


async def _test_build_monthly_attendance_report_includes_legacy_worker_with_null_active_flag(tmp_path: Path) -> None:
    database_path = tmp_path / "report-legacy-worker.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path.as_posix()}")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    """
                    CREATE TABLE sites (
                        id INTEGER PRIMARY KEY,
                        name VARCHAR(120),
                        code VARCHAR(30),
                        telegram_group_id BIGINT,
                        is_active BOOLEAN,
                        created_at DATETIME
                    )
                    """
                )
            )
            await connection.execute(
                text(
                    """
                    CREATE TABLE workers (
                        id INTEGER PRIMARY KEY,
                        telegram_user_id BIGINT,
                        full_name VARCHAR(150),
                        ic_number VARCHAR(30),
                        employee_code VARCHAR(50),
                        site_id INTEGER,
                        is_active BOOLEAN NULL,
                        created_at DATETIME,
                        updated_at DATETIME
                    )
                    """
                )
            )
            await connection.execute(
                text(
                    """
                    CREATE TABLE attendance_records (
                        id INTEGER PRIMARY KEY,
                        worker_id INTEGER,
                        attendance_date DATE,
                        check_in_at DATETIME,
                        check_out_at DATETIME,
                        source_chat_id BIGINT,
                        notes TEXT,
                        created_at DATETIME,
                        updated_at DATETIME
                    )
                    """
                )
            )
            await connection.execute(
                text(
                    """
                    CREATE TABLE leave_requests (
                        id INTEGER PRIMARY KEY,
                        worker_id INTEGER,
                        leave_type VARCHAR(20),
                        day_portion VARCHAR(10),
                        start_date DATE,
                        end_date DATE,
                        reason TEXT,
                        telegram_file_id VARCHAR(255),
                        status VARCHAR(20),
                        submitted_at DATETIME,
                        reviewed_at DATETIME,
                        reviewed_by_telegram_id BIGINT,
                        review_notes TEXT
                    )
                    """
                )
            )
            await connection.execute(
                text(
                    """
                    CREATE TABLE public_holidays (
                        id INTEGER PRIMARY KEY,
                        name VARCHAR(150),
                        holiday_date DATE,
                        site_id INTEGER,
                        notes TEXT,
                        created_at DATETIME
                    )
                    """
                )
            )

        async with session_factory() as session:
            await session.execute(
                text(
                    """
                    INSERT INTO sites (id, name, code, is_active)
                    VALUES (1, 'Sepang', 'SEP', 1)
                    """
                )
            )
            await session.execute(
                text(
                    """
                    INSERT INTO workers (id, telegram_user_id, full_name, site_id, is_active)
                    VALUES (1, 404, 'Legacy Active Worker', 1, NULL)
                    """
                )
            )
            await session.commit()

            import services.report_service as report_service

            original_get_settings = report_service.get_settings
            report_service.get_settings = lambda: SimpleNamespace(
                company_name="KHSAR",
                default_site_name="Sepang",
            )
            try:
                report = await build_monthly_attendance_report(session, year=2026, month=4)
            finally:
                report_service.get_settings = original_get_settings

            assert [row["worker_name"] for row in report["rows"]] == ["Legacy Active Worker"]
    finally:
        await engine.dispose()
