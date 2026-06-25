from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from crxzipple.modules.operations.application.read_models.channels_payload_formatting import (
    short_json,
)
from crxzipple.shared.time import coerce_utc_datetime, format_datetime_utc


def seconds_since(value: Any, *, now: datetime) -> float:
    if not isinstance(value, datetime):
        return 0.0
    return max(0.0, (now - coerce_utc_datetime(value)).total_seconds())


def age_label(seconds: float) -> str:
    if seconds < 60:
        return f"{round(seconds)}s"
    if seconds < 3600:
        return f"{round(seconds / 60)}m"
    if seconds < 86400:
        return f"{round(seconds / 3600, 1)}h"
    return f"{round(seconds / 86400, 1)}d"


def format_datetime(value: Any) -> str:
    if isinstance(value, datetime):
        return format_datetime_utc(value)
    return "-"


def sort_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return coerce_utc_datetime(value)
    return datetime.min.replace(tzinfo=timezone.utc)


def short_optional(value: Any, *, size: int = 96) -> str:
    text_value = text(value, "")
    if not text_value:
        return "-"
    if len(text_value) <= size:
        return text_value
    return f"{text_value[: max(12, size - 8)]}..."


def text(value: Any, default: str = "-") -> str:
    if value is None or value == "":
        return default
    if isinstance(value, datetime):
        return format_datetime_utc(value)
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple, set)):
        return join(value)
    if isinstance(value, dict):
        return short_json(value)
    return str(value)


def int_value(value: Any) -> int:
    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return 0


def first_text(*values: Any) -> str | None:
    for value in values:
        text_value = text(value, "")
        if text_value:
            return text_value
    return None


def join(values: Any) -> str:
    items = [text(value, "") for value in values if text(value, "")]
    return ", ".join(dict.fromkeys(items)) if items else "-"


def normalized_filter(value: str) -> str:
    normalized = str(value or "all").strip().lower().replace("_", "-")
    return normalized or "all"


def status_label(value: str) -> str:
    normalized = normalized_filter(value)
    if normalized == "all":
        return "-"
    return title(normalized.replace("-", " "))


def title(value: str) -> str:
    return " ".join(part.capitalize() for part in str(value).replace("_", " ").split())


def label_from_key(value: str) -> str:
    return title(value.replace("supports_", ""))


def display_text(value: Any, default: str = "-") -> str:
    return text(value, default)


def id_for(value: str) -> str:
    return (
        value.strip()
        .lower()
        .replace("/", " ")
        .replace(".", " ")
        .replace("-", " ")
        .replace("_", " ")
    ).replace(" ", "_") or "unknown"


def tone_for_status(value: str, *, default: str = "neutral") -> str:
    text_value = value.lower()
    if any(
        token in text_value
        for token in ("dead", "failed", "fail", "error", "offline", "blocked")
    ):
        return "danger"
    if any(
        token in text_value
        for token in ("stale", "warning", "pending", "retry", "control")
    ):
        return "warning"
    if any(
        token in text_value
        for token in (
            "online",
            "ready",
            "healthy",
            "success",
            "succeeded",
            "active",
            "enabled",
            "matched",
            "completed",
            "delivered",
        )
    ):
        return "success"
    if any(
        token in text_value
        for token in (
            "observe",
            "live",
            "broadcast",
            "info",
            "intake",
            "received",
            "submitted",
            "accepted",
            "running",
            "queued",
        )
    ):
        return "info"
    return default
