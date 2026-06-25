from __future__ import annotations

from typing import Any


def safe_tuple(target: Any, method_name: str, *args: Any, **kwargs: Any) -> tuple[Any, ...]:
    method = getattr(target, method_name, None)
    if not callable(method):
        return ()
    try:
        value = method(*args, **kwargs)
    except Exception:
        return ()
    if value is None:
        return ()
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    return tuple(value) if isinstance(value, set) else ()


def safe_list_event_topics(events_service: Any) -> tuple[str, ...]:
    method = getattr(events_service, "list_event_topics", None)
    if not callable(method):
        return ()
    try:
        value = method()
    except Exception:
        return ()
    return tuple(str(item) for item in value or () if isinstance(item, str) and item)
