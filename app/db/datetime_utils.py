from __future__ import annotations

from datetime import UTC, datetime


def normalize_datetime_to_utc(value: datetime) -> datetime:
    """Normalize datetime to timezone-aware UTC.

    Naive inputs are interpreted as UTC.
    Aware inputs are converted to UTC.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
