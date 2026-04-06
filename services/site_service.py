from __future__ import annotations

from collections.abc import Sequence
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.models import Site


class SiteError(ValueError):
    pass


async def list_sites(session: AsyncSession, *, active_only: bool = False) -> Sequence[Site]:
    query = select(Site).order_by(Site.name)
    if active_only:
        query = query.where(Site.is_active.is_(True))
    result = await session.execute(query)
    return result.scalars().all()


async def get_site_by_id(session: AsyncSession, site_id: int) -> Optional[Site]:
    result = await session.execute(select(Site).where(Site.id == site_id))
    return result.scalar_one_or_none()


async def get_default_site(session: AsyncSession) -> Optional[Site]:
    result = await session.execute(
        select(Site).where(Site.is_active.is_(True)).order_by(Site.id.asc()).limit(1)
    )
    return result.scalar_one_or_none()


async def create_site(
    session: AsyncSession,
    *,
    name: str,
    code: Optional[str] = None,
    telegram_group_id: Optional[int] = None,
    is_active: bool = True,
) -> Site:
    cleaned_name = name.strip()
    cleaned_code = (code or "").strip() or None
    existing_by_name = await session.execute(select(Site).where(Site.name == cleaned_name))
    if existing_by_name.scalar_one_or_none():
        raise SiteError("Site name or code already exists.")
    if cleaned_code:
        existing_by_code = await session.execute(select(Site).where(Site.code == cleaned_code))
        if existing_by_code.scalar_one_or_none():
            raise SiteError("Site name or code already exists.")
    if telegram_group_id is not None:
        existing_by_group = await session.execute(
            select(Site).where(Site.telegram_group_id == telegram_group_id)
        )
        if existing_by_group.scalar_one_or_none():
            raise SiteError("Telegram group ID is already assigned to another site.")

    site = Site(
        name=cleaned_name,
        code=cleaned_code,
        telegram_group_id=telegram_group_id,
        is_active=is_active,
    )
    session.add(site)
    await session.commit()
    await session.refresh(site)
    return site


async def update_site(
    session: AsyncSession,
    site: Site,
    *,
    name: str,
    code: Optional[str] = None,
    telegram_group_id: Optional[int] = None,
    is_active: bool = True,
) -> Site:
    cleaned_name = name.strip()
    cleaned_code = (code or "").strip() or None
    result = await session.execute(select(Site).where(Site.id != site.id))
    for existing in result.scalars().all():
        if existing.name == cleaned_name or (cleaned_code and existing.code == cleaned_code):
            raise SiteError("Site name or code already exists.")
        if telegram_group_id is not None and existing.telegram_group_id == telegram_group_id:
            raise SiteError("Telegram group ID is already assigned to another site.")

    site.name = cleaned_name
    site.code = cleaned_code
    site.telegram_group_id = telegram_group_id
    site.is_active = is_active
    await session.commit()
    await session.refresh(site)
    return site
