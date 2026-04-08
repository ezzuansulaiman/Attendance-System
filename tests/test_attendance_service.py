import asyncio
from datetime import date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from models.database import Base
from models.models import AttendanceRecord, Site, Worker
from services.attendance_service import AttendanceError, check_in, get_worker_by_telegram_id, list_active_workers, update_attendance_record
from services.leave_service import approve_leave_request, create_leave_request


LOCAL_TZ = ZoneInfo("Asia/Kuala_Lumpur")


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


def test_attendance_record_round_trip_keeps_malaysia_timezone_in_sqlite() -> None:
    with TemporaryDirectory(dir=Path.cwd()) as temp_dir:
        asyncio.run(_test_attendance_record_round_trip_keeps_malaysia_timezone_in_sqlite(Path(temp_dir)))


def test_check_in_allows_approved_half_day_leave() -> None:
    with TemporaryDirectory(dir=Path.cwd()) as temp_dir:
        asyncio.run(_test_check_in_allows_approved_half_day_leave(Path(temp_dir)))


def test_active_worker_lookup_treats_null_is_active_as_active() -> None:
    with TemporaryDirectory(dir=Path.cwd()) as temp_dir:
        asyncio.run(_test_active_worker_lookup_treats_null_is_active_as_active(Path(temp_dir)))


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
                check_in_at=datetime(2026, 4, 1, 8, 0, tzinfo=LOCAL_TZ),
            )
            conflicting_record = AttendanceRecord(
                worker_id=worker.id,
                attendance_date=date(2026, 4, 2),
                check_in_at=datetime(2026, 4, 2, 8, 0, tzinfo=LOCAL_TZ),
            )
            session.add_all([original_record, conflicting_record])
            await session.commit()

            with pytest.raises(AttendanceError, match="already exists"):
                await update_attendance_record(
                    session,
                    original_record,
                    worker_id=worker.id,
                    attendance_date=date(2026, 4, 2),
                    check_in_at=datetime(2026, 4, 2, 9, 0, tzinfo=LOCAL_TZ),
                    check_out_at=None,
                    notes="Updated",
                )

            await session.refresh(original_record)
            assert original_record.attendance_date == date(2026, 4, 1)
            assert original_record.check_in_at == datetime(2026, 4, 1, 8, 0, tzinfo=LOCAL_TZ)
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
                check_in_at=datetime(2026, 4, 7, 8, 0, tzinfo=LOCAL_TZ),
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
                check_in_at=datetime(2026, 4, 7, 8, 15, tzinfo=LOCAL_TZ),
                check_out_at=datetime(2026, 4, 7, 17, 30, tzinfo=LOCAL_TZ),
                notes="Adjusted from admin web",
            )

            await session.refresh(record)
            assert record.source_chat_id == -1001234567890
            assert record.notes == "Adjusted from admin web"
    finally:
        await engine.dispose()


async def _test_attendance_record_round_trip_keeps_malaysia_timezone_in_sqlite(tmp_path) -> None:
    database_path = tmp_path / "attendance-timezone.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path.as_posix()}")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async with session_factory() as session:
            site = Site(name="Timezone Site", code="TZ", is_active=True)
            session.add(site)
            await session.flush()

            worker = Worker(
                telegram_user_id=111222,
                full_name="Timezone Worker",
                site_id=site.id,
                is_active=True,
            )
            session.add(worker)
            await session.flush()

            expected = datetime(2026, 4, 7, 8, 30, tzinfo=LOCAL_TZ)
            record = AttendanceRecord(
                worker_id=worker.id,
                attendance_date=expected.date(),
                check_in_at=expected,
            )
            session.add(record)
            await session.commit()
            await session.refresh(record)

            assert record.check_in_at == expected
            assert record.check_in_at.tzinfo == LOCAL_TZ
    finally:
        await engine.dispose()


async def _test_check_in_allows_approved_half_day_leave(tmp_path) -> None:
    database_path = tmp_path / "attendance-half-day.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path.as_posix()}")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async with session_factory() as session:
            site = Site(name="Half Day Checkin Site", code="HDCK", is_active=True)
            session.add(site)
            await session.flush()

            worker = Worker(
                telegram_user_id=333444,
                full_name="Half Day Checkin Worker",
                site_id=site.id,
                is_active=True,
            )
            session.add(worker)
            await session.commit()
            await session.refresh(worker)

            leave_request = await create_leave_request(
                session,
                worker=worker,
                leave_type="mc",
                start_date=date(2026, 4, 7),
                end_date=date(2026, 4, 7),
                day_portion="pm",
                reason="Afternoon clinic visit",
                telegram_file_id="photo-file-id",
            )
            await approve_leave_request(session, leave_request=leave_request, admin_telegram_id=1)

            record = await check_in(
                session,
                worker=worker,
                chat_id=-10012345,
                occurred_at=datetime(2026, 4, 7, 8, 0, tzinfo=LOCAL_TZ),
            )

            assert record.check_in_at == datetime(2026, 4, 7, 8, 0, tzinfo=LOCAL_TZ)
    finally:
        await engine.dispose()


async def _test_active_worker_lookup_treats_null_is_active_as_active(tmp_path) -> None:
    database_path = tmp_path / "attendance-null-active.db"
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

        async with session_factory() as session:
            await session.execute(
                text(
                    """
                    INSERT INTO sites (id, name, code, is_active)
                    VALUES (1, 'Legacy Site', 'LEG', 1)
                    """
                )
            )
            await session.execute(
                text(
                    """
                    INSERT INTO workers (id, telegram_user_id, full_name, site_id, is_active)
                    VALUES (1, 818181, 'Legacy Worker', 1, NULL)
                    """
                )
            )
            await session.commit()

            resolved_worker = await get_worker_by_telegram_id(session, 818181)
            active_workers = await list_active_workers(session)

            assert resolved_worker is not None
            assert resolved_worker.full_name == "Legacy Worker"
            assert [item.full_name for item in active_workers] == ["Legacy Worker"]
    finally:
        await engine.dispose()
