from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
import logging

from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from config import get_settings


class Base(DeclarativeBase):
    pass


logger = logging.getLogger(__name__)
settings = get_settings()

engine = create_async_engine(
    settings.database_url,
    future=True,
    pool_pre_ping=True,
)
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


@asynccontextmanager
async def session_scope() -> AsyncIterator[AsyncSession]:
    async with async_session_factory() as session:
        yield session


async def get_session() -> AsyncIterator[AsyncSession]:
    async with session_scope() as session:
        yield session


async def _sqlite_column_names(connection, table_name: str) -> set[str]:
    result = await connection.execute(text(f"PRAGMA table_info({table_name})"))
    return {row[1] for row in result.fetchall()}


async def _sqlite_add_column_if_missing(
    connection,
    *,
    table_name: str,
    column_names: set[str],
    column_name: str,
    column_type: str,
) -> set[str]:
    if column_name in column_names:
        return column_names

    try:
        await connection.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"))
    except OperationalError as exc:
        # Existing SQLite files may partially apply DDL during earlier failed runs.
        # Re-read the schema so startup can continue if the column is already there.
        refreshed_names = await _sqlite_column_names(connection, table_name)
        if column_name not in refreshed_names:
            raise exc
        return refreshed_names

    column_names.add(column_name)
    return column_names


def _postgres_is_textual_date_type(data_type: str) -> bool:
    return data_type.strip().lower() in {"text", "character varying", "character", "varchar", "bpchar"}


def _postgres_text_value_expression(column_name: str) -> str:
    return f"NULLIF(BTRIM(CAST({column_name} AS TEXT)), '')"


def _postgres_safe_date_expression(column_name: str) -> str:
    text_value_expression = _postgres_text_value_expression(column_name)
    return (
        "CASE "
        f"WHEN {text_value_expression} ~ '^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}$' "
        f"THEN CAST({text_value_expression} AS DATE) "
        "ELSE NULL END"
    )


async def _postgres_column_data_types(connection, table_name: str) -> dict[str, str]:
    result = await connection.execute(
        text(
            """
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_schema = current_schema() AND table_name = :table_name
            """
        ),
        {"table_name": table_name},
    )
    return {row.column_name: row.data_type for row in result.fetchall()}


async def _postgres_repair_public_holiday_date_type(connection) -> None:
    column_types = await _postgres_column_data_types(connection, "public_holidays")
    holiday_date_type = column_types.get("holiday_date")
    if not holiday_date_type or not _postgres_is_textual_date_type(holiday_date_type):
        return

    safe_date_expression = _postgres_safe_date_expression("holiday_date")
    invalid_value_count = await connection.execute(
        text(
            f"""
            SELECT COUNT(*)
            FROM public_holidays
            WHERE CAST(holiday_date AS TEXT) IS NOT NULL
              AND {safe_date_expression} IS NULL
            """
        )
    )
    invalid_count = int(invalid_value_count.scalar_one() or 0)
    if invalid_count:
        logger.warning(
            "Skipped automatic repair for public_holidays.holiday_date because %s rows contain non-ISO date text.",
            invalid_count,
        )
        return

    await connection.execute(
        text(
            f"""
            ALTER TABLE public_holidays
            ALTER COLUMN holiday_date TYPE DATE
            USING {safe_date_expression}
            """
        )
    )
    logger.info("Repaired public_holidays.holiday_date from %s to DATE.", holiday_date_type)


async def init_database() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        dialect = connection.dialect.name
        if dialect == "sqlite":
            site_names = await _sqlite_column_names(connection, "sites")
            site_names = await _sqlite_add_column_if_missing(
                connection,
                table_name="sites",
                column_names=site_names,
                column_name="telegram_group_id",
                column_type="BIGINT",
            )

            worker_names = await _sqlite_column_names(connection, "workers")
            for column_name, column_type in (
                ("ic_number", "VARCHAR(30)"),
                ("employee_code", "VARCHAR(50)"),
                ("site_id", "INTEGER"),
                ("is_active", "BOOLEAN DEFAULT 1"),
            ):
                worker_names = await _sqlite_add_column_if_missing(
                    connection,
                    table_name="workers",
                    column_names=worker_names,
                    column_name=column_name,
                    column_type=column_type,
                )
            if "is_active" in worker_names:
                await connection.execute(
                    text(
                        """
                        UPDATE workers
                        SET is_active = 1
                        WHERE is_active IS NULL
                        """
                    )
                )

            leave_names = await _sqlite_column_names(connection, "leave_requests")
            sqlite_missing_columns = {
                "worker_id": "INTEGER",
                "day_portion": "VARCHAR(10) DEFAULT 'full'",
                "start_date": "DATE",
                "end_date": "DATE",
                "telegram_file_id": "VARCHAR(255)",
                "reviewed_by_telegram_id": "BIGINT",
                "review_notes": "TEXT",
            }
            for column_name, column_type in sqlite_missing_columns.items():
                leave_names = await _sqlite_add_column_if_missing(
                    connection,
                    table_name="leave_requests",
                    column_names=leave_names,
                    column_name=column_name,
                    column_type=column_type,
                )
            if "employee_id" in leave_names and "worker_id" in leave_names:
                await connection.execute(
                    text(
                        """
                        UPDATE leave_requests
                        SET worker_id = employee_id
                        WHERE worker_id IS NULL
                        """
                    )
                )
            if "date_from" in leave_names and "start_date" in leave_names:
                await connection.execute(
                    text(
                        """
                        UPDATE leave_requests
                        SET start_date = CAST(CAST(date_from AS TEXT) AS DATE)
                        WHERE start_date IS NULL
                        """
                    )
                )
            if "day_portion" in leave_names:
                await connection.execute(
                    text(
                        """
                        UPDATE leave_requests
                        SET day_portion = 'full'
                        WHERE day_portion IS NULL OR TRIM(CAST(day_portion AS TEXT)) = ''
                        """
                    )
                )
            if "date_to" in leave_names and "end_date" in leave_names:
                await connection.execute(
                    text(
                        """
                        UPDATE leave_requests
                        SET end_date = CAST(CAST(date_to AS TEXT) AS DATE)
                        WHERE end_date IS NULL
                        """
                    )
                )
            if "supporting_doc" in leave_names and "telegram_file_id" in leave_names:
                await connection.execute(
                    text(
                        """
                        UPDATE leave_requests
                        SET telegram_file_id = supporting_doc
                        WHERE telegram_file_id IS NULL
                        """
                    )
                )
            if "reviewer_notes" in leave_names and "review_notes" in leave_names:
                await connection.execute(
                    text(
                        """
                        UPDATE leave_requests
                        SET review_notes = reviewer_notes
                        WHERE review_notes IS NULL
                        """
                    )
                )
            # Drop legacy columns that are no longer populated by the ORM.
            # SQLite 3.35+ supports DROP COLUMN; older versions skip silently.
            for _legacy_col in ("employee_id", "date_from", "date_to", "supporting_doc", "reviewer_notes"):
                if _legacy_col in leave_names:
                    try:
                        await connection.execute(text(f'ALTER TABLE leave_requests DROP COLUMN "{_legacy_col}"'))
                        leave_names.discard(_legacy_col)
                    except Exception as _drop_exc:
                        logger.debug("Cannot drop legacy column %s from SQLite leave_requests: %s", _legacy_col, _drop_exc)

            public_holiday_names = await _sqlite_column_names(connection, "public_holidays")
            for column_name, column_type in (
                ("name", "VARCHAR(150)"),
                ("holiday_date", "DATE"),
                ("site_id", "INTEGER"),
                ("notes", "TEXT"),
                ("created_at", "DATETIME"),
            ):
                public_holiday_names = await _sqlite_add_column_if_missing(
                    connection,
                    table_name="public_holidays",
                    column_names=public_holiday_names,
                    column_name=column_name,
                    column_type=column_type,
                )
        elif dialect == "postgresql":
            await connection.execute(
                text(
                    """
                    ALTER TABLE sites
                    ADD COLUMN IF NOT EXISTS telegram_group_id BIGINT
                    """
                )
            )
            await connection.execute(
                text(
                    """
                    ALTER TABLE workers
                    ADD COLUMN IF NOT EXISTS ic_number VARCHAR(30)
                    """
                )
            )
            await connection.execute(
                text(
                    """
                    ALTER TABLE workers
                    ADD COLUMN IF NOT EXISTS employee_code VARCHAR(50)
                    """
                )
            )
            await connection.execute(
                text(
                    """
                    ALTER TABLE workers
                    ADD COLUMN IF NOT EXISTS site_id INTEGER
                    """
                )
            )
            await connection.execute(
                text(
                    """
                    ALTER TABLE workers
                    ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE
                    """
                )
            )
            await connection.execute(
                text(
                    """
                    UPDATE workers
                    SET is_active = TRUE
                    WHERE is_active IS NULL
                    """
                )
            )
            postgres_missing_columns = [
                ("worker_id", "INTEGER"),
                ("day_portion", "VARCHAR(10) DEFAULT 'full'"),
                ("start_date", "DATE"),
                ("end_date", "DATE"),
                ("telegram_file_id", "VARCHAR(255)"),
                ("reviewed_by_telegram_id", "BIGINT"),
                ("review_notes", "TEXT"),
            ]
            for column_name, column_type in postgres_missing_columns:
                await connection.execute(
                    text(
                        f"""
                        ALTER TABLE leave_requests
                        ADD COLUMN IF NOT EXISTS {column_name} {column_type}
                        """
                    )
                )
            for column_name, column_type in (
                ("name", "VARCHAR(150)"),
                ("holiday_date", "DATE"),
                ("site_id", "INTEGER"),
                ("notes", "TEXT"),
                ("created_at", "TIMESTAMP WITH TIME ZONE"),
            ):
                await connection.execute(
                    text(
                        f"""
                        ALTER TABLE public_holidays
                        ADD COLUMN IF NOT EXISTS {column_name} {column_type}
                        """
                    )
                )
            await _postgres_repair_public_holiday_date_type(connection)
            pg_columns = await connection.execute(
                text(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_name = 'leave_requests'
                    """
                )
            )
            pg_names = {row[0] for row in pg_columns.fetchall()}
            if "employee_id" in pg_names and "worker_id" in pg_names:
                await connection.execute(
                    text(
                        """
                        UPDATE leave_requests
                        SET worker_id = employee_id
                        WHERE worker_id IS NULL
                        """
                    )
                )
            if "date_from" in pg_names and "start_date" in pg_names:
                await connection.execute(
                    text(
                        """
                        UPDATE leave_requests
                        SET start_date = CAST(CAST(date_from AS TEXT) AS DATE)
                        WHERE start_date IS NULL
                        """
                    )
                )
            if "day_portion" in pg_names:
                await connection.execute(
                    text(
                        """
                        UPDATE leave_requests
                        SET day_portion = 'full'
                        WHERE day_portion IS NULL OR BTRIM(CAST(day_portion AS TEXT)) = ''
                        """
                    )
                )
            if "date_to" in pg_names and "end_date" in pg_names:
                await connection.execute(
                    text(
                        """
                        UPDATE leave_requests
                        SET end_date = CAST(CAST(date_to AS TEXT) AS DATE)
                        WHERE end_date IS NULL
                        """
                    )
                )
            if "supporting_doc" in pg_names and "telegram_file_id" in pg_names:
                await connection.execute(
                    text(
                        """
                        UPDATE leave_requests
                        SET telegram_file_id = supporting_doc
                        WHERE telegram_file_id IS NULL
                        """
                    )
                )
            if "reviewer_notes" in pg_names and "review_notes" in pg_names:
                await connection.execute(
                    text(
                        """
                        UPDATE leave_requests
                        SET review_notes = reviewer_notes
                        WHERE review_notes IS NULL
                        """
                    )
                )
            # Drop NOT NULL constraints from legacy columns that the ORM no longer populates.
            # Without this, every INSERT into leave_requests raises IntegrityError.
            for _legacy_col in ("employee_id", "date_from", "date_to", "supporting_doc", "reviewer_notes"):
                if _legacy_col in pg_names:
                    await connection.execute(
                        text(f"ALTER TABLE leave_requests ALTER COLUMN {_legacy_col} DROP NOT NULL")
                    )

        default_site_name = settings.default_site_name
        existing_site = await connection.execute(
            text("SELECT id FROM sites WHERE name = :name"),
            {"name": default_site_name},
        )
        if existing_site.first() is None:
            await connection.execute(
                text(
                    """
                    INSERT INTO sites (name, code, is_active)
                    VALUES (:name, :code, :is_active)
                    """
                ),
                {"name": default_site_name, "code": default_site_name[:10].upper(), "is_active": True},
            )
