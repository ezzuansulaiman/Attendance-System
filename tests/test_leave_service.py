import asyncio
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from models.database import Base
from models.models import Site, Worker
from services.leave_service import (
    LeaveError,
    admin_upsert_single_day_leave,
    annual_leave_notice_days,
    approve_leave_request,
    create_leave_request,
    delete_leave_request,
    get_leave_request,
)


def test_create_leave_request_rejects_overlapping_pending_or_approved_ranges() -> None:
    with TemporaryDirectory(dir=Path.cwd()) as temp_dir:
        asyncio.run(_test_create_leave_request_rejects_overlapping_pending_or_approved_ranges(Path(temp_dir)))


def test_admin_upsert_single_day_leave_creates_updates_and_deletes_one_day_leave() -> None:
    with TemporaryDirectory(dir=Path.cwd()) as temp_dir:
        asyncio.run(_test_admin_upsert_single_day_leave_creates_updates_and_deletes_one_day_leave(Path(temp_dir)))


def test_create_leave_request_supports_half_day_single_day_only() -> None:
    with TemporaryDirectory(dir=Path.cwd()) as temp_dir:
        asyncio.run(_test_create_leave_request_supports_half_day_single_day_only(Path(temp_dir)))


def test_create_leave_request_rejects_annual_leave_without_notice_period(monkeypatch) -> None:
    monkeypatch.setattr("services.leave_service._today_local_date", lambda: date(2026, 4, 8))
    with TemporaryDirectory(dir=Path.cwd()) as temp_dir:
        asyncio.run(_test_create_leave_request_rejects_annual_leave_without_notice_period(Path(temp_dir)))


def test_approve_leave_request_auto_rejects_late_annual_leave(monkeypatch) -> None:
    monkeypatch.setattr("services.leave_service._today_local_date", lambda: date(2026, 4, 8))
    with TemporaryDirectory(dir=Path.cwd()) as temp_dir:
        asyncio.run(_test_approve_leave_request_auto_rejects_late_annual_leave(Path(temp_dir)))


async def _test_create_leave_request_rejects_overlapping_pending_or_approved_ranges(tmp_path: Path) -> None:
    database_path = tmp_path / "leave-test.db"
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
            await session.commit()
            await session.refresh(worker)

            first_request = await create_leave_request(
                session,
                worker=worker,
                leave_type="mc",
                start_date=date(2026, 4, 7),
                end_date=date(2026, 4, 7),
                reason="Medical leave",
                telegram_file_id="photo-file-id",
            )

            with pytest.raises(LeaveError, match="bertindih"):
                await create_leave_request(
                    session,
                    worker=worker,
                    leave_type="mc",
                    start_date=date(2026, 4, 7),
                    end_date=date(2026, 4, 8),
                    reason="Overlap pending request",
                    telegram_file_id="photo-file-id-2",
                )

            await approve_leave_request(session, leave_request=first_request, admin_telegram_id=1)

            with pytest.raises(LeaveError, match="bertindih"):
                await create_leave_request(
                    session,
                    worker=worker,
                    leave_type="mc",
                    start_date=date(2026, 4, 6),
                    end_date=date(2026, 4, 7),
                    reason="Overlap approved request",
                    telegram_file_id="photo-file-id-3",
                )
    finally:
        await engine.dispose()


async def _test_admin_upsert_single_day_leave_creates_updates_and_deletes_one_day_leave(tmp_path: Path) -> None:
    database_path = tmp_path / "leave-grid-test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path.as_posix()}")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async with session_factory() as session:
            site = Site(name="Grid Site", code="GRID", is_active=True)
            session.add(site)
            await session.flush()

            worker = Worker(
                telegram_user_id=654321,
                full_name="Grid Worker",
                site_id=site.id,
                is_active=True,
            )
            session.add(worker)
            await session.commit()
            await session.refresh(worker)

            leave_request = await admin_upsert_single_day_leave(
                session,
                worker_id=worker.id,
                leave_type="mc",
                target_date=date(2026, 4, 9),
                day_portion="full",
                reason="Clinic visit",
            )

            assert leave_request.leave_type == "mc"
            assert leave_request.day_portion == "full"
            assert leave_request.status == "approved"
            assert leave_request.start_date == date(2026, 4, 9)
            assert leave_request.end_date == date(2026, 4, 9)

            updated_request = await admin_upsert_single_day_leave(
                session,
                worker_id=worker.id,
                leave_type="annual",
                target_date=date(2026, 4, 9),
                day_portion="pm",
                reason="Annual leave override",
            )

            assert updated_request.id == leave_request.id
            assert updated_request.leave_type == "annual"
            assert updated_request.day_portion == "pm"
            assert updated_request.reason == "Annual leave override"

            await delete_leave_request(session, updated_request)

            assert await get_leave_request(session, updated_request.id) is None
    finally:
        await engine.dispose()


async def _test_create_leave_request_supports_half_day_single_day_only(tmp_path: Path) -> None:
    database_path = tmp_path / "leave-half-day-test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path.as_posix()}")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async with session_factory() as session:
            site = Site(name="Half Day Site", code="HALF", is_active=True)
            session.add(site)
            await session.flush()

            worker = Worker(
                telegram_user_id=999111,
                full_name="Half Day Worker",
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
                start_date=date(2026, 4, 10),
                end_date=date(2026, 4, 10),
                day_portion="am",
                reason="Morning clinic visit",
                telegram_file_id="photo-file-id",
            )

            assert leave_request.day_portion == "am"

            with pytest.raises(LeaveError, match="separuh hari"):
                await create_leave_request(
                    session,
                    worker=worker,
                    leave_type="mc",
                    start_date=date(2026, 4, 11),
                    end_date=date(2026, 4, 12),
                    day_portion="pm",
                    reason="Invalid multi-day partial leave",
                    telegram_file_id="photo-file-id-2",
                )
    finally:
        await engine.dispose()


async def _test_create_leave_request_rejects_annual_leave_without_notice_period(tmp_path: Path) -> None:
    database_path = tmp_path / "leave-annual-notice.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path.as_posix()}")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async with session_factory() as session:
            site = Site(name="Annual Notice Site", code="ANNUAL", is_active=True)
            session.add(site)
            await session.flush()

            worker = Worker(
                telegram_user_id=222333,
                full_name="Annual Leave Worker",
                site_id=site.id,
                is_active=True,
            )
            session.add(worker)
            await session.commit()
            await session.refresh(worker)

            expected_notice_days = annual_leave_notice_days()
            with pytest.raises(LeaveError, match=rf"sekurang-kurangnya {expected_notice_days} hari"):
                await create_leave_request(
                    session,
                    worker=worker,
                    leave_type="annual",
                    start_date=date(2026, 4, 11),
                    end_date=date(2026, 4, 11),
                    reason="Too soon annual leave",
                )
    finally:
        await engine.dispose()


async def _test_approve_leave_request_auto_rejects_late_annual_leave(tmp_path: Path) -> None:
    database_path = tmp_path / "leave-annual-auto-reject.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path.as_posix()}")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async with session_factory() as session:
            site = Site(name="Annual Reject Site", code="AREJ", is_active=True)
            session.add(site)
            await session.flush()

            worker = Worker(
                telegram_user_id=444555,
                full_name="Pending Annual Worker",
                site_id=site.id,
                is_active=True,
            )
            session.add(worker)
            await session.flush()

            late_request = await create_leave_request(
                session,
                worker=worker,
                leave_type="mc",
                start_date=date(2026, 4, 9),
                end_date=date(2026, 4, 9),
                reason="Temporary request to create row",
                telegram_file_id="photo-file-id",
            )
            late_request.leave_type = "annual"
            late_request.reason = "Late annual leave"
            late_request.telegram_file_id = None
            await session.commit()
            await session.refresh(late_request)

            reviewed_request = await approve_leave_request(
                session,
                leave_request=late_request,
                admin_telegram_id=101,
                notes="Diluluskan dari ujian",
            )

            assert reviewed_request.status == "rejected"
            expected_notice_days = annual_leave_notice_days()
            assert reviewed_request.review_notes == (
                "Ditolak automatik kerana permohonan Cuti Tahunan dibuat kurang daripada "
                f"{expected_notice_days} hari sebelum tarikh mula."
            )
    finally:
        await engine.dispose()
