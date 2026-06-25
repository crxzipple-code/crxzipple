from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def short_generation(value: Any) -> str:
    value_text = text(value)
    if value_text == "-" or len(value_text) <= 12:
        return value_text
    return value_text[:12]


def bytes_label(value: Any) -> str:
    size = int_value(value, -1)
    if size < 0:
        return "-"
    if size < 1024:
        return f"{size} B"
    kib = size / 1024
    if kib < 1024:
        return f"{kib:.1f} KiB"
    mib = kib / 1024
    return f"{mib:.1f} MiB"


def pool_concurrency_label(pool: Any) -> str:
    per_profile = int_value(getattr(pool, "max_concurrency_per_profile", None), 1)
    total = getattr(pool, "max_concurrency_total", None)
    total_label = text(total) if total is not None else "unlimited"
    return f"{per_profile}/profile · {total_label} total"


def consumer_label(allocation: Any) -> str:
    kind = text(getattr(allocation, "consumer_kind", None))
    consumer_id = text(getattr(allocation, "consumer_id", None))
    if kind == "-":
        return consumer_id
    if consumer_id == "-":
        return kind
    return f"{kind}:{consumer_id}"


def duration_seconds_label(value: Any) -> str:
    seconds = int_value(value, -1)
    if seconds < 0:
        return "-"
    return compact_seconds(seconds)


def age_label(value: Any, *, now: datetime) -> str:
    timestamp = datetime_value(value)
    if timestamp is None:
        return "-"
    seconds = max(0, int((now - timestamp).total_seconds()))
    return compact_seconds(seconds)


def ttl_label(value: Any, *, now: datetime) -> str:
    timestamp = datetime_value(value)
    if timestamp is None:
        return "-"
    seconds = int((timestamp - now).total_seconds())
    if seconds < 0:
        return "expired"
    return compact_seconds(seconds)


def compact_seconds(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    minutes, rem = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {rem}s" if rem else f"{minutes}m"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m" if minutes else f"{hours}h"


def normalized_filter(value: Any) -> str:
    value_text = str(value or "all").strip().lower()
    return value_text or "all"


def text(value: Any, fallback: str = "-") -> str:
    if value is None or value == "":
        return fallback
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


def int_value(value: Any, fallback: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return fallback


def datetime_value(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    return None


def dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def to_payload(value: Any) -> dict[str, Any]:
    to_payload_fn = getattr(value, "to_payload", None)
    if callable(to_payload_fn):
        payload = to_payload_fn()
        if isinstance(payload, dict):
            return dict(payload)
    return {}


def list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def join(values: Any) -> str:
    if not values:
        return "-"
    return ", ".join(str(value) for value in values if str(value)) or "-"
