from __future__ import annotations

from datetime import datetime
from typing import Optional

from config import get_settings


def local_timezone():
    return get_settings().local_timezone


def coerce_local_datetime(value: datetime) -> datetime:
    local_tz = local_timezone()
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        return value.replace(tzinfo=local_tz)
    return value.astimezone(local_tz)


def coerce_optional_local_datetime(value: Optional[datetime]) -> Optional[datetime]:
    if value is None:
        return None
    return coerce_local_datetime(value)


def parse_stored_datetime(value: datetime | str) -> datetime:
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        parsed = value
    return coerce_local_datetime(parsed)


def format_local_datetime(value: datetime, fmt: str = "%d/%m/%Y %H:%M") -> str:
    return coerce_local_datetime(value).strftime(fmt)


def format_local_datetime_input(value: Optional[datetime]) -> str:
    if value is None:
        return ""
    return format_local_datetime(value, "%Y-%m-%dT%H:%M")


def now_local() -> datetime:
    return datetime.now(local_timezone())
