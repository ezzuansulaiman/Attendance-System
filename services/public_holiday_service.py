from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from types import SimpleNamespace
from typing import Optional

from sqlalchemy import or_, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models.models import PublicHoliday, Site


class PublicHolidayError(ValueError):
    pass


def _clean_optional_text(value: Optional[str]) -> Optional[str]:
    cleaned = (value or "").strip()
    return cleaned or None


def public_holiday_label(public_holiday: Optional[PublicHoliday]) -> Optional[str]:
    if not public_holiday:
        return None
    return public_holiday.name.strip()


def _coerce_holiday_date(value: object) -> date:
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _is_legacy_public_holiday_schema_error(exc: OperationalError) -> bool:
    message = str(exc).lower()
    return any(
        marker in message
        for marker in (
            "public_holidays.site_id",
            "public_holidays.notes",
            "public_holidays.created_at",
            "no such table: public_holidays",
            "no such column: site_id",
            "no such column: notes",
            "no such column: created_at",
            "column public_holidays.site_id does not exist",
            "column public_holidays.notes does not exist",
            "column public_holidays.created_at does not exist",
            "column \"site_id\" does not exist",
            "column \"notes\" does not exist",
            "column \"created_at\" does not exist",
            "relation \"public_holidays\" does not exist",
        )
    )


async def _list_legacy_public_holidays_in_range(
    session: AsyncSession,
    *,
    start_date: date,
    end_date: date,
) -> Sequence[object]:
    connection = await session.connection()
    dialect = connection.dialect.name
    if dialect == "sqlite":
        column_result = await connection.execute(text("PRAGMA table_info(public_holidays)"))
        column_names = {row[1] for row in column_result.fetchall()}
    elif dialect == "postgresql":
        column_result = await connection.execute(
            text(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = 'public_holidays'
                """
            )
        )
        column_names = {row[0] for row in column_result.fetchall()}
    else:
        column_names = {"id", "name", "holiday_date", "site_id", "notes", "created_at"}

    if not {"id", "name", "holiday_date"}.issubset(column_names):
        return []

    select_expressions = {
        "id": "id",
        "name": "name",
        "holiday_date": "holiday_date",
        "site_id": "site_id" if "site_id" in column_names else "NULL AS site_id",
        "notes": "notes" if "notes" in column_names else "NULL AS notes",
        "created_at": "created_at" if "created_at" in column_names else "NULL AS created_at",
    }
    try:
        result = await session.execute(
            text(
                f"""
                SELECT {select_expressions["id"]}, {select_expressions["name"]}, {select_expressions["holiday_date"]},
                       {select_expressions["site_id"]}, {select_expressions["notes"]}, {select_expressions["created_at"]}
                FROM public_holidays
                WHERE holiday_date >= :start_date AND holiday_date <= :end_date
                ORDER BY holiday_date ASC, name ASC
                """
            ),
            {"start_date": start_date, "end_date": end_date},
        )
    except OperationalError as exc:
        if _is_legacy_public_holiday_schema_error(exc):
            return []
        raise

    return [
        SimpleNamespace(
            id=row.id,
            name=row.name,
            holiday_date=_coerce_holiday_date(row.holiday_date),
            site_id=None,
            notes=row.notes,
            created_at=row.created_at,
            site=None,
        )
        for row in result
    ]


async def _get_legacy_public_holiday_for_date(
    session: AsyncSession,
    *,
    target_date: date,
) -> Optional[object]:
    legacy_rows = await _list_legacy_public_holidays_in_range(
        session,
        start_date=target_date,
        end_date=target_date,
    )
    return next(iter(legacy_rows), None)


async def get_public_holiday(session: AsyncSession, holiday_id: int) -> Optional[PublicHoliday]:
    result = await session.execute(
        select(PublicHoliday)
        .options(selectinload(PublicHoliday.site))
        .where(PublicHoliday.id == holiday_id)
    )
    return result.scalar_one_or_none()


async def get_public_holiday_for_date(
    session: AsyncSession,
    *,
    target_date: date,
    site_id: Optional[int],
) -> Optional[PublicHoliday]:
    query = (
        select(PublicHoliday)
        .options(selectinload(PublicHoliday.site))
        .where(PublicHoliday.holiday_date == target_date)
        .order_by(PublicHoliday.site_id.is_(None), PublicHoliday.id.asc())
    )
    if site_id is None:
        query = query.where(PublicHoliday.site_id.is_(None))
    else:
        query = query.where(or_(PublicHoliday.site_id == site_id, PublicHoliday.site_id.is_(None)))
    try:
        result = await session.execute(query)
    except OperationalError as exc:
        if _is_legacy_public_holiday_schema_error(exc):
            return await _get_legacy_public_holiday_for_date(session, target_date=target_date)
        raise
    return result.scalars().first()


async def list_public_holidays_in_range(
    session: AsyncSession,
    *,
    start_date: date,
    end_date: date,
) -> Sequence[PublicHoliday]:
    try:
        result = await session.execute(
            select(PublicHoliday)
            .options(selectinload(PublicHoliday.site))
            .where(
                PublicHoliday.holiday_date >= start_date,
                PublicHoliday.holiday_date <= end_date,
            )
            .order_by(PublicHoliday.holiday_date.asc(), PublicHoliday.name.asc())
        )
    except OperationalError as exc:
        if _is_legacy_public_holiday_schema_error(exc):
            return await _list_legacy_public_holidays_in_range(session, start_date=start_date, end_date=end_date)
        raise
    return result.scalars().all()


async def _validate_site(session: AsyncSession, site_id: Optional[int]) -> Optional[int]:
    if site_id is None:
        return None
    site = await session.get(Site, site_id)
    if not site:
        raise PublicHolidayError("Selected site was not found.")
    return site_id


async def _find_exact_holiday_conflict(
    session: AsyncSession,
    *,
    holiday_date: date,
    site_id: Optional[int],
    exclude_id: Optional[int] = None,
) -> Optional[PublicHoliday]:
    query = select(PublicHoliday).where(
        PublicHoliday.holiday_date == holiday_date,
        PublicHoliday.site_id == site_id,
    )
    if exclude_id is not None:
        query = query.where(PublicHoliday.id != exclude_id)
    result = await session.execute(query)
    return result.scalar_one_or_none()


async def create_public_holiday(
    session: AsyncSession,
    *,
    name: str,
    holiday_date: date,
    site_id: Optional[int] = None,
    notes: Optional[str] = None,
) -> PublicHoliday:
    cleaned_name = name.strip()
    if not cleaned_name:
        raise PublicHolidayError("Holiday name is required.")

    validated_site_id = await _validate_site(session, site_id)
    conflict = await _find_exact_holiday_conflict(session, holiday_date=holiday_date, site_id=validated_site_id)
    if conflict:
        raise PublicHolidayError("A public holiday already exists for that date and site scope.")

    public_holiday = PublicHoliday(
        name=cleaned_name,
        holiday_date=holiday_date,
        site_id=validated_site_id,
        notes=_clean_optional_text(notes),
    )
    session.add(public_holiday)
    await session.commit()
    await session.refresh(public_holiday)
    return public_holiday


async def update_public_holiday(
    session: AsyncSession,
    public_holiday: PublicHoliday,
    *,
    name: str,
    holiday_date: date,
    site_id: Optional[int] = None,
    notes: Optional[str] = None,
) -> PublicHoliday:
    cleaned_name = name.strip()
    if not cleaned_name:
        raise PublicHolidayError("Holiday name is required.")

    validated_site_id = await _validate_site(session, site_id)
    conflict = await _find_exact_holiday_conflict(
        session,
        holiday_date=holiday_date,
        site_id=validated_site_id,
        exclude_id=public_holiday.id,
    )
    if conflict:
        raise PublicHolidayError("A public holiday already exists for that date and site scope.")

    public_holiday.name = cleaned_name
    public_holiday.holiday_date = holiday_date
    public_holiday.site_id = validated_site_id
    public_holiday.notes = _clean_optional_text(notes)
    await session.commit()
    await session.refresh(public_holiday)
    return public_holiday


async def upsert_public_holiday_for_date(
    session: AsyncSession,
    *,
    holiday_date: date,
    site_id: Optional[int],
    name: str,
    notes: Optional[str] = None,
) -> PublicHoliday:
    existing = await _find_exact_holiday_conflict(session, holiday_date=holiday_date, site_id=site_id)
    if existing:
        return await update_public_holiday(
            session,
            existing,
            name=name,
            holiday_date=holiday_date,
            site_id=site_id,
            notes=notes,
        )
    return await create_public_holiday(
        session,
        name=name,
        holiday_date=holiday_date,
        site_id=site_id,
        notes=notes,
    )


async def delete_public_holiday(session: AsyncSession, public_holiday: PublicHoliday) -> None:
    await session.delete(public_holiday)
    await session.commit()
