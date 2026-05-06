from __future__ import annotations

from datetime import datetime, timezone


def coerce_utc_datetime(value: datetime) -> datetime:
    """Treat naive persisted datetimes as UTC and emit aware UTC values."""
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def coerce_optional_utc_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return coerce_utc_datetime(value)


def format_datetime_utc(value: datetime) -> str:
    return coerce_utc_datetime(value).isoformat()


def format_optional_datetime_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    return format_datetime_utc(value)
