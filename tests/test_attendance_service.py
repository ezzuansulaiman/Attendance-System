import asyncio
from datetime import date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from models.database import Base
from models.models import AttendanceRecord, Site, Worker
from services.attendance_service import AttendanceError, update_attendance_record


def test_update_attendance_record_rejects_duplicate_target_without_deleting_original() -> None:
    with TemporaryDirectory(dir=Path.cwd()) as temp_dir:
        asyncio.run(
            _test_update_attendance_record_rejects_duplicate_target_without_deleting_original(Path(temp_dir))
        )


def test_update_attendance_record_preserves_source_chat_id_for_telegram_originated_record() -> None:
    with TemporaryDirectory(dir=Path.cwd()) as temp_dir:
        asyncio.run(
            _test_update_attendance_record_preserves_source_chat_id_for_telegram_originated_record(Path(temp_dir))
        )


async def _test_update_attendance_record_rejects_duplicate_target_without_deleting_original(tmp_path) -> None:
    database_path = tmp_path / "attendance-test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path.as_posix()}")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async with session_factory() as session:
            site = Site(name="Test Site", code="TEST", is_active=True)
            session.add(site)
            await session.flush()

            worker = Worker(
                telegram_user_id=123456,
                full_name="Test Worker",
                site_id=site.id,
                is_active=True,
            )
            session.add(worker)
            await session.flush()

            original_record = AttendanceRecord(
                worker_id=worker.id,
                attendance_date=date(2026, 4, 1),
                check_in_at=datetime(2026, 4, 1, 8, 0),
            )
            conflicting_record = AttendanceRecord(
                worker_id=worker.id,
                attendance_date=date(2026, 4, 2),
                check_in_at=datetime(2026, 4, 2, 8, 0),
            )
            session.add_all([original_record, conflicting_record])
            await session.commit()

            with pytest.raises(AttendanceError, match="already exists"):
                await update_attendance_record(
                    session,
                    original_record,
                    worker_id=worker.id,
                    attendance_date=date(2026, 4, 2),
                    check_in_at=datetime(2026, 4, 2, 9, 0),
                    check_out_at=None,
                    notes="Updated",
                )

            await session.refresh(original_record)
            assert original_record.attendance_date == date(2026, 4, 1)
            assert original_record.check_in_at == datetime(2026, 4, 1, 8, 0)
    finally:
        await engine.dispose()


async def _test_update_attendance_record_preserves_source_chat_id_for_telegram_originated_record(tmp_path) -> None:
    database_path = tmp_path / "attendance-source-chat.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path.as_posix()}")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async with session_factory() as session:
            site = Site(name="Telegram Site", code="TG", is_active=True)
            session.add(site)
            await session.flush()

            worker = Worker(
                telegram_user_id=67890,
                full_name="Telegram Worker",
                site_id=site.id,
                is_active=True,
            )
            session.add(worker)
            await session.flush()

            record = AttendanceRecord(
                worker_id=worker.id,
                attendance_date=date(2026, 4, 7),
                check_in_at=datetime(2026, 4, 7, 8, 0),
                source_chat_id=-1001234567890,
                notes="Original Telegram check-in",
            )
            session.add(record)
            await session.commit()

            await update_attendance_record(
                session,
                record,
                worker_id=worker.id,
                attendance_date=date(2026, 4, 7),
                check_in_at=datetime(2026, 4, 7, 8, 15),
                check_out_at=datetime(2026, 4, 7, 17, 30),
                notes="Adjusted from admin web",
            )

            await session.refresh(record)
            assert record.source_chat_id == -1001234567890
            assert record.notes == "Adjusted from admin web"
    finally:
        await engine.dispose()
