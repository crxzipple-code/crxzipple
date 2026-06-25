from __future__ import annotations

from datetime import datetime
from typing import Any

from crxzipple.shared.time import coerce_utc_datetime, format_datetime_utc

MAX_PAYLOAD_DEPTH = 4
MAX_PAYLOAD_ITEMS = 24
MAX_TEXT_LENGTH = 512


def sanitize_payload(value: Any, *, depth: int = 0) -> Any:
    if depth >= MAX_PAYLOAD_DEPTH:
        return truncate(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return truncate(value)
    if isinstance(value, datetime):
        return format_datetime_utc(value)
    if isinstance(value, dict):
        items = list(value.items())[:MAX_PAYLOAD_ITEMS]
        return {
            str(key): sanitize_payload(item_value, depth=depth + 1)
            for key, item_value in items
            if isinstance(key, str) and key.strip()
        }
    if isinstance(value, (list, tuple, set)):
        return [
            sanitize_payload(item, depth=depth + 1)
            for item in list(value)[:MAX_PAYLOAD_ITEMS]
        ]
    return truncate(value)


def truncate(value: Any) -> str:
    text = str(value)
    if len(text) <= MAX_TEXT_LENGTH:
        return text
    return f"{text[:MAX_TEXT_LENGTH]}..."


def optional_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def int_value(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip():
        try:
            return int(float(value))
        except ValueError:
            return 0
    return 0


def optional_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value)
        except ValueError:
            return None
    return None


def count_map(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key): int_value(item)
        for key, item in value.items()
        if isinstance(key, str) and key.strip()
    }


def parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return coerce_utc_datetime(datetime.fromisoformat(value))
    except ValueError:
        return None
