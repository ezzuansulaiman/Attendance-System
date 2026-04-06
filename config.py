from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

load_dotenv()


def _get_env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _get_env_int(name: str, default: int) -> int:
    raw_value = _get_env(name, str(default))
    return int(raw_value) if raw_value else default


def _split_ints(raw_value: str) -> tuple[int, ...]:
    values: list[int] = []
    for chunk in raw_value.split(","):
        item = chunk.strip()
        if not item:
            continue
        values.append(int(item))
    return tuple(values)


def _normalize_database_url(raw_value: str) -> str:
    value = raw_value.strip()
    if not value:
        sqlite_path = _get_env("SQLITE_PATH", "attendance.db") or "attendance.db"
        resolved = Path(sqlite_path)
        if not resolved.is_absolute():
            resolved = Path.cwd() / resolved
        return f"sqlite+aiosqlite:///{resolved.as_posix()}"

    if value.startswith("postgres://"):
        return value.replace("postgres://", "postgresql+asyncpg://", 1)
    if value.startswith("postgresql://") and "+asyncpg" not in value:
        return value.replace("postgresql://", "postgresql+asyncpg://", 1)
    return value


@dataclass(frozen=True)
class Settings:
    bot_token: str
    database_url: str
    admin_ids: tuple[int, ...]
    group_id: Optional[int]
    web_base_url: str
    timezone: str
    host: str
    port: int
    web_username: str
    web_password: str
    session_secret: str
    company_name: str
    default_site_name: str
    annual_leave_notice_days: int

    @property
    def bot_enabled(self) -> bool:
        return bool(self.bot_token)

    @property
    def local_timezone(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @property
    def admin_web_login_url(self) -> Optional[str]:
        if not self.web_base_url:
            return None
        base_url = self.web_base_url.rstrip("/")
        if base_url.endswith("/login"):
            return base_url
        return f"{base_url}/login"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    group_raw = _get_env("GROUP_ID")
    return Settings(
        bot_token=_get_env("BOT_TOKEN"),
        database_url=_normalize_database_url(_get_env("DATABASE_URL")),
        admin_ids=_split_ints(_get_env("ADMIN_IDS")),
        group_id=int(group_raw) if group_raw else None,
        web_base_url=_get_env("WEB_BASE_URL"),
        timezone=_get_env("TIMEZONE", "Asia/Kuala_Lumpur") or "Asia/Kuala_Lumpur",
        host="0.0.0.0",
        port=_get_env_int("PORT", 8000),
        web_username=_get_env("ADMIN_WEB_USERNAME", "admin") or "admin",
        web_password=_get_env("ADMIN_WEB_PASSWORD", "change-me") or "change-me",
        session_secret=_get_env("SESSION_SECRET", "change-me-please") or "change-me-please",
        company_name=_get_env("COMPANY_NAME", "Khidmat Hartanah Samat Ayob & Rakan Sdn Bhd.") or "Khidmat Hartanah Samat Ayob & Rakan Sdn Bhd.",
        default_site_name=_get_env("DEFAULT_SITE_NAME", "Sepang") or "Sepang",
        annual_leave_notice_days=_get_env_int("ANNUAL_LEAVE_NOTICE_DAYS", 5),
    )
