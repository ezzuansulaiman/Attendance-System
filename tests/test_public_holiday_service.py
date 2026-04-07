import asyncio
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from models.database import Base
from models.models import Site
from services.public_holiday_service import (
    create_public_holiday,
    delete_public_holiday,
    get_public_holiday_for_date,
    list_public_holidays_in_range,
    upsert_public_holiday_for_date,
)


def test_public_holiday_service_supports_site_and_global_lookup() -> None:
    with TemporaryDirectory(dir=Path.cwd()) as temp_dir:
        asyncio.run(_test_public_holiday_service_supports_site_and_global_lookup(Path(temp_dir)))


async def _test_public_holiday_service_supports_site_and_global_lookup(tmp_path: Path) -> None:
    database_path = tmp_path / "public-holiday-test.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path.as_posix()}")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

        async with session_factory() as session:
            site = Site(name="Sepang", code="SEP", is_active=True)
            session.add(site)
            await session.commit()
            await session.refresh(site)

            global_holiday = await create_public_holiday(
                session,
                name="Labour Day",
                holiday_date=date(2026, 5, 1),
                site_id=None,
            )

            resolved_global = await get_public_holiday_for_date(
                session,
                target_date=date(2026, 5, 1),
                site_id=site.id,
            )
            assert resolved_global is not None
            assert resolved_global.id == global_holiday.id

            site_holiday = await upsert_public_holiday_for_date(
                session,
                holiday_date=date(2026, 5, 1),
                site_id=site.id,
                name="Sepang Special Holiday",
            )

            resolved_site = await get_public_holiday_for_date(
                session,
                target_date=date(2026, 5, 1),
                site_id=site.id,
            )
            assert resolved_site is not None
            assert resolved_site.id == site_holiday.id
            assert resolved_site.name == "Sepang Special Holiday"

            await delete_public_holiday(session, site_holiday)

            resolved_after_delete = await get_public_holiday_for_date(
                session,
                target_date=date(2026, 5, 1),
                site_id=site.id,
            )
            assert resolved_after_delete is not None
            assert resolved_after_delete.id == global_holiday.id
    finally:
        await engine.dispose()


def test_public_holiday_service_reads_legacy_table_without_site_id() -> None:
    with TemporaryDirectory(dir=Path.cwd()) as temp_dir:
        asyncio.run(_test_public_holiday_service_reads_legacy_table_without_site_id(Path(temp_dir)))


async def _test_public_holiday_service_reads_legacy_table_without_site_id(tmp_path: Path) -> None:
    database_path = tmp_path / "public-holiday-legacy.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path.as_posix()}")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with engine.begin() as connection:
            tables = [table for name, table in Base.metadata.tables.items() if name != "public_holidays"]
            await connection.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=tables))
            await connection.execute(
                text(
                    """
                    CREATE TABLE public_holidays (
                        id INTEGER NOT NULL PRIMARY KEY,
                        name VARCHAR(150) NOT NULL,
                        holiday_date DATE NOT NULL,
                        notes TEXT,
                        created_at DATETIME
                    )
                    """
                )
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO public_holidays (id, name, holiday_date, notes)
                    VALUES (1, 'Labour Day', '2026-05-01', 'Legacy schema row')
                    """
                )
            )

        async with session_factory() as session:
            resolved = await get_public_holiday_for_date(
                session,
                target_date=date(2026, 5, 1),
                site_id=123,
            )
            listed = await list_public_holidays_in_range(
                session,
                start_date=date(2026, 5, 1),
                end_date=date(2026, 5, 1),
            )

            assert resolved is not None
            assert resolved.name == "Labour Day"
            assert resolved.site_id is None
            assert len(listed) == 1
            assert listed[0].name == "Labour Day"
            assert listed[0].site_id is None
    finally:
        await engine.dispose()


def test_public_holiday_service_reads_minimal_legacy_table_shape() -> None:
    with TemporaryDirectory(dir=Path.cwd()) as temp_dir:
        asyncio.run(_test_public_holiday_service_reads_minimal_legacy_table_shape(Path(temp_dir)))


async def _test_public_holiday_service_reads_minimal_legacy_table_shape(tmp_path: Path) -> None:
    database_path = tmp_path / "public-holiday-legacy-min.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path.as_posix()}")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with engine.begin() as connection:
            tables = [table for name, table in Base.metadata.tables.items() if name != "public_holidays"]
            await connection.run_sync(lambda sync_conn: Base.metadata.create_all(sync_conn, tables=tables))
            await connection.execute(
                text(
                    """
                    CREATE TABLE public_holidays (
                        id INTEGER NOT NULL PRIMARY KEY,
                        name VARCHAR(150) NOT NULL,
                        holiday_date DATE NOT NULL
                    )
                    """
                )
            )
            await connection.execute(
                text(
                    """
                    INSERT INTO public_holidays (id, name, holiday_date)
                    VALUES (1, 'Labour Day', '2026-05-01')
                    """
                )
            )

        async with session_factory() as session:
            resolved = await get_public_holiday_for_date(
                session,
                target_date=date(2026, 5, 1),
                site_id=456,
            )
            listed = await list_public_holidays_in_range(
                session,
                start_date=date(2026, 5, 1),
                end_date=date(2026, 5, 1),
            )

            assert resolved is not None
            assert resolved.name == "Labour Day"
            assert resolved.notes is None
            assert resolved.site_id is None
            assert len(listed) == 1
            assert listed[0].name == "Labour Day"
            assert listed[0].notes is None
    finally:
        await engine.dispose()
