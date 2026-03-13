from __future__ import annotations

from datetime import datetime

from sqlalchemy.types import DateTime, TypeDecorator

from app.db.datetime_utils import normalize_datetime_to_utc


class UTCDateTime(TypeDecorator):
    """Persist and load datetimes as timezone-aware UTC values."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):
        if value is None:
            return None
        return normalize_datetime_to_utc(value)

    def process_result_value(self, value: datetime | None, dialect):
        if value is None:
            return None
        return normalize_datetime_to_utc(value)
