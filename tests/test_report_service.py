import asyncio
from datetime import date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from models.database import Base
from models.models import AttendanceRecord, PublicHoliday, Site, Worker
from services.report_service import build_monthly_attendance_report


def test_build_monthly_attendance_report_defaults_to_sepang_scope() -> None:
    with TemporaryDirectory(dir=Path.cwd()) as temp_dir:
        asyncio.run(_test_build_monthly_attendance_report_defaults_to_sepang_scope(Path(temp_dir)))


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
                        worker_id=klang_worker.id,
                        attendance_date=date(2026, 4, 1),
                        check_in_at=datetime(2026, 4, 1, 8, 30),
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
            assert [row["worker_name"] for row in report["detail_rows"]] == ["Sepang Worker"]
            assert report["rows"][0]["days"][1] == "PH"
    finally:
        await engine.dispose()
