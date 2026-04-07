from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, String
from sqlalchemy.types import TypeDecorator

from datetime_utils import coerce_local_datetime, parse_stored_datetime


class LocalizedDateTime(TypeDecorator):
    impl = DateTime
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "sqlite":
            return dialect.type_descriptor(String(40))
        return dialect.type_descriptor(DateTime(timezone=True))

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        localized = coerce_local_datetime(value)
        if dialect.name == "sqlite":
            return localized.isoformat(sep=" ", timespec="microseconds")
        return localized

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if dialect.name == "sqlite":
            return parse_stored_datetime(value)
        if isinstance(value, datetime):
            return coerce_local_datetime(value)
        return parse_stored_datetime(value)
