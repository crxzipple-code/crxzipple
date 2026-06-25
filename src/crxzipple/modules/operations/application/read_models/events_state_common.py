from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from crxzipple.shared.time import format_datetime_utc


def safe_operations_observation_snapshot(operations_observation: Any | None) -> Any | None:
    if operations_observation is None:
        return None
    snapshot = getattr(operations_observation, "snapshot", None)
    if not callable(snapshot):
        return None
    try:
        return snapshot()
    except Exception:
        return None


def seconds_since_datetime(updated_at: Any, *, now: datetime) -> float:
    if not isinstance(updated_at, datetime):
        return 0.0
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    return max(0.0, (now - updated_at.astimezone(timezone.utc)).total_seconds())


def compare_event_cursors(left: str | None, right: str | None) -> int:
    left_cursor = parse_event_cursor(left)
    right_cursor = parse_event_cursor(right)
    if left_cursor == right_cursor:
        return 0
    return 1 if left_cursor > right_cursor else -1


def cursor_gap(latest: str | None, current: str | None) -> int:
    left = parse_event_cursor(latest)
    right = parse_event_cursor(current)
    if left[0] != right[0]:
        return max(0, left[0] - right[0])
    return max(0, left[1] - right[1])


def parse_event_cursor(cursor: str | None) -> tuple[int, int]:
    if not isinstance(cursor, str) or not cursor.strip():
        return (0, 0)
    if "-" not in cursor:
        try:
            return (int(cursor), 0)
        except ValueError:
            return (0, 0)
    left, right = cursor.split("-", 1)
    try:
        return (int(left), int(right))
    except ValueError:
        return (0, 0)


def jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return format_datetime_utc(value)
    if isinstance(value, dict):
        return {str(key): jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set)):
        return [jsonable(item) for item in value]
    to_payload = getattr(value, "to_payload", None)
    if callable(to_payload):
        try:
            return jsonable(to_payload())
        except Exception:
            return display(value)
    return display(value)


def display(value: Any, fallback: str = "-") -> str:
    if value is None:
        return fallback
    if isinstance(value, str):
        return value.strip() or fallback
    if isinstance(value, (tuple, list, set)):
        return join(tuple(display(item) for item in value))
    return str(value)


def join(values: tuple[Any, ...] | list[Any]) -> str:
    rendered = [
        str(value).strip()
        for value in values
        if str(value).strip() and str(value).strip() != "-"
    ]
    return ", ".join(rendered) if rendered else "-"
