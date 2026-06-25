from __future__ import annotations

import hashlib
import re
from typing import Any, Mapping

from crxzipple.modules.browser.domain import BrowserValidationError


def _snapshot_result(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise BrowserValidationError(
            "Browser action trace snapshot returned an invalid result."
        )
    return dict(value)


def _mapping_result(value: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise BrowserValidationError(
            "Browser action trace callback returned an invalid result."
        )
    return dict(value)


def _trace_capture_id(trace_id: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_.:-]+", "-", trace_id).strip("-")
    if not normalized:
        normalized = hashlib.sha1(trace_id.encode("utf-8")).hexdigest()[:12]
    return f"{normalized}-network"


def _trace_error_message(exc: Exception) -> str:
    message = " ".join(str(exc).split())
    if not message:
        message = exc.__class__.__name__
    if len(message) > 500:
        return f"{message[:497].rstrip()}..."
    return message


def _trace_error_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [_json_safe_payload(item) for item in value if isinstance(item, Mapping)]


def _bounded_text(value: str, *, limit: int) -> str:
    normalized = value.strip()
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 3].rstrip()}..."


def _payload_text_any(
    payload: Mapping[str, Any],
    *keys: str,
) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _payload_bool_any(
    payload: Mapping[str, Any],
    *keys: str,
) -> bool | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, bool):
            return value
    return None


def _payload_value_any(
    payload: Mapping[str, Any],
    *keys: str,
) -> Any:
    for key in keys:
        if key in payload:
            return payload.get(key)
    return None


def _payload_int_any(
    payload: Mapping[str, Any],
    *keys: str,
    minimum: int = 0,
) -> int | None:
    value = _payload_value_any(payload, *keys)
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


def _json_safe_payload(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_safe_payload(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe_payload(item) for item in value]
    return str(value)
