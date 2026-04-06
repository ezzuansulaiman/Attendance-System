from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from config import get_settings


class Base(DeclarativeBase):
    pass


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


async def init_database() -> None:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
        dialect = connection.dialect.name
        if dialect == "sqlite":
            site_columns = await connection.execute(text("PRAGMA table_info(sites)"))
            site_names = {row[1] for row in site_columns.fetchall()}
            if "telegram_group_id" not in site_names:
                await connection.execute(text("ALTER TABLE sites ADD COLUMN telegram_group_id BIGINT"))

            worker_columns = await connection.execute(text("PRAGMA table_info(workers)"))
            worker_names = {row[1] for row in worker_columns.fetchall()}
            if "site_id" not in worker_names:
                await connection.execute(text("ALTER TABLE workers ADD COLUMN site_id INTEGER"))

            leave_columns = await connection.execute(text("PRAGMA table_info(leave_requests)"))
            leave_names = {row[1] for row in leave_columns.fetchall()}
            sqlite_missing_columns = {
                "worker_id": "INTEGER",
                "start_date": "DATE",
                "end_date": "DATE",
                "telegram_file_id": "VARCHAR(255)",
                "reviewed_by_telegram_id": "BIGINT",
                "review_notes": "TEXT",
            }
            for column_name, column_type in sqlite_missing_columns.items():
                if column_name not in leave_names:
                    await connection.execute(
                        text(f"ALTER TABLE leave_requests ADD COLUMN {column_name} {column_type}")
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
                        SET start_date = date_from
                        WHERE start_date IS NULL
                        """
                    )
                )
            if "date_to" in leave_names and "end_date" in leave_names:
                await connection.execute(
                    text(
                        """
                        UPDATE leave_requests
                        SET end_date = date_to
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
                    ADD COLUMN IF NOT EXISTS site_id INTEGER
                    """
                )
            )
            postgres_missing_columns = [
                ("worker_id", "INTEGER"),
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
                        SET start_date = date_from
                        WHERE start_date IS NULL
                        """
                    )
                )
            if "date_to" in pg_names and "end_date" in pg_names:
                await connection.execute(
                    text(
                        """
                        UPDATE leave_requests
                        SET end_date = date_to
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
