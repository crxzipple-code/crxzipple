from __future__ import annotations

from typing import Any, Mapping

from crxzipple.modules.browser.domain import BrowserValidationError


def payload_text_list(payload: Mapping[str, Any], *keys: str) -> list[str]:
    raw_value = payload_value_any(payload, *keys)
    if raw_value is None:
        return []
    if isinstance(raw_value, str):
        return [item.strip() for item in raw_value.split(",") if item.strip()]
    if isinstance(raw_value, (list, tuple)):
        return [str(item).strip() for item in raw_value if str(item).strip()]
    raise BrowserValidationError("Browser script insight text lists must be a string or list.")


def payload_text_any(
    payload: Mapping[str, Any],
    *keys: str,
) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def payload_bool_any(
    payload: Mapping[str, Any],
    *keys: str,
) -> bool | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, bool):
            return value
    return None


def payload_value_any(
    payload: Mapping[str, Any],
    *keys: str,
) -> Any:
    for key in keys:
        if key in payload:
            return payload.get(key)
    return None


def payload_int_any(
    payload: Mapping[str, Any],
    *keys: str,
    minimum: int = 0,
) -> int | None:
    value = payload_value_any(payload, *keys)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise BrowserValidationError(f"payload.{keys[0]} must be an integer.")
    resolved = int(value)
    if resolved < minimum:
        raise BrowserValidationError(
            f"payload.{keys[0]} must be greater than or equal to {minimum}.",
        )
    return resolved


def json_safe_payload(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): json_safe_payload(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe_payload(item) for item in value]
    return str(value)
