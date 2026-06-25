from __future__ import annotations

from typing import Any


def safe_profiles(target: Any | None) -> tuple[Any, ...]:
    method = getattr(target, "list_profiles", None)
    if not callable(method):
        return ()
    try:
        return tuple(method())
    except Exception:
        return ()


def safe_tuple(target: Any | None, method_name: str, **kwargs: Any) -> tuple[Any, ...]:
    method = getattr(target, method_name, None)
    if not callable(method):
        return ()
    try:
        return tuple(method(**kwargs))
    except Exception:
        return ()
