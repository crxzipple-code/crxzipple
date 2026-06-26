from __future__ import annotations

from datetime import datetime, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def normalize_key(value: str) -> str:
    return value.strip().lower()


def normalize_identifier(value: str) -> str:
    return value.strip()
