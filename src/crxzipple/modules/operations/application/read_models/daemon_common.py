from __future__ import annotations

from datetime import datetime
from typing import Any

from crxzipple.shared.time import coerce_utc_datetime, format_datetime_utc


def _status_label(value: Any) -> str:
    text = _text(value, "unknown").replace("_", " ").strip()
    if not text:
        return "-"
    return " ".join(part.capitalize() for part in text.split())


def _first_text(*values: Any) -> str:
    for value in values:
        text = _text(value, "")
        if text and text != "-":
            return text
    return "-"


def _text(value: Any, default: str = "-") -> str:
    if value is None:
        return default
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple, set)):
        return ", ".join(_text(item, "") for item in value if _text(item, ""))
    if isinstance(value, dict):
        return ", ".join(f"{key}={_text(item, '')}" for key, item in sorted(value.items()))
    text = str(value).strip()
    return text if text else default


def _short(value: Any, limit: int = 80) -> str:
    text = _text(value)
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 1)]}..."


def _short_optional(value: Any, limit: int = 80) -> str:
    text = _text(value, "")
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 1)]}..."


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _yes_no(value: bool) -> str:
    return "Yes" if value else "No"


def _datetime_text(value: Any) -> str:
    if isinstance(value, datetime):
        return format_datetime_utc(coerce_utc_datetime(value))
    return _text(value)


def _first_datetime(*values: Any) -> datetime | None:
    for value in values:
        parsed = _parse_datetime(value)
        if parsed is not None:
            return parsed
    return None


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return coerce_utc_datetime(value)
    if isinstance(value, str) and value.strip() and value.strip() != "-":
        try:
            return coerce_utc_datetime(
                datetime.fromisoformat(value.strip().replace("Z", "+00:00")),
            )
        except ValueError:
            return None
    return None


def _seconds_since_datetime(value: datetime, *, now: datetime) -> float:
    return max(0.0, (coerce_utc_datetime(now) - coerce_utc_datetime(value)).total_seconds())


def _normalized_filter(value: Any) -> str:
    text = _text(value, "all").strip().lower().replace(" ", "_")
    return text or "all"


def _string_values(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return tuple(item.strip().lower() for item in value.split(",") if item.strip())
    if isinstance(value, (list, tuple, set)):
        return tuple(_text(item, "").lower() for item in value if _text(item, ""))
    return ()


def _search_blob(*records: dict[str, Any]) -> str:
    values: list[str] = []
    for record in records:
        for value in record.values():
            values.append(_text(value, ""))
    return " ".join(values).lower()

