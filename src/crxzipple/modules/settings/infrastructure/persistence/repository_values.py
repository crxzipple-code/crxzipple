from __future__ import annotations

from datetime import datetime, timezone

from crxzipple.modules.settings.infrastructure.persistence.records import (
    SettingsEffectiveSnapshotRecord,
    SettingsResourceVersionRecord,
)
from crxzipple.shared.time import coerce_utc_datetime


def _with_create_timestamps(record: object) -> dict[str, datetime]:
    created_at = _record_created_at(record)
    updated_at = getattr(record, "updated_at", None)
    return {
        "created_at": created_at,
        "updated_at": coerce_utc_datetime(updated_at) if updated_at else created_at,
    }


def _version_timestamps(record: SettingsResourceVersionRecord) -> dict[str, datetime]:
    timestamps = _with_create_timestamps(record)
    if record.status == "published" and record.published_at is None:
        return {**timestamps, "published_at": timestamps["updated_at"]}
    return timestamps


def _snapshot_timestamps(
    record: SettingsEffectiveSnapshotRecord,
) -> dict[str, datetime]:
    created_at = _record_created_at(record)
    updated_at = getattr(record, "updated_at", None)
    generated_at = getattr(record, "generated_at", None)
    return {
        "created_at": created_at,
        "updated_at": coerce_utc_datetime(updated_at) if updated_at else created_at,
        "generated_at": coerce_utc_datetime(generated_at) if generated_at else created_at,
    }


def _record_created_at(record: object) -> datetime:
    created_at = getattr(record, "created_at", None)
    return _coerce_or_now(created_at)


def _record_updated_at(record: object) -> datetime:
    updated_at = getattr(record, "updated_at", None)
    if updated_at is not None:
        return coerce_utc_datetime(updated_at)
    return _record_created_at(record)


def _record_generated_at(record: object) -> datetime:
    generated_at = getattr(record, "generated_at", None)
    if generated_at is not None:
        return coerce_utc_datetime(generated_at)
    return _record_created_at(record)


def _coerce_or_now(value: datetime | None) -> datetime:
    return coerce_utc_datetime(value or datetime.now(timezone.utc))


def _required_text(value: str, label: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"settings {label} cannot be blank")
    return normalized


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None
