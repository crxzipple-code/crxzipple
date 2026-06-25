from __future__ import annotations

from typing import Any, Mapping
from urllib.parse import urlsplit

from crxzipple.modules.browser.domain.value_objects import (
    BrowserNetworkBody,
    BrowserNetworkRequest,
)

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def normalize_header_items(value: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    items: list[tuple[str, str]] = []
    for key, item in value.items():
        normalized_key = str(key).strip().lower()
        if not normalized_key:
            continue
        items.append((normalized_key, "" if item is None else str(item)))
    return tuple(sorted(items))


def source_body_state(
    *,
    request: BrowserNetworkRequest,
    request_body: BrowserNetworkBody | None,
) -> dict[str, Any]:
    if request_body is not None:
        if request_body.redacted:
            return {
                "state": "redacted",
                "present": True,
                "redacted": True,
                "size_bytes": request_body.size_bytes,
                "stored_size_bytes": request_body.stored_size_bytes,
            }
        return {
            "state": "available",
            "present": True,
            "redacted": False,
            "size_bytes": request_body.size_bytes,
            "stored_size_bytes": request_body.stored_size_bytes,
        }
    if request.request_body_ref is not None:
        return {
            "state": "missing",
            "present": True,
            "redacted": False,
            "size_bytes": None,
            "stored_size_bytes": None,
        }
    return {
        "state": "none",
        "present": False,
        "redacted": False,
        "size_bytes": 0,
        "stored_size_bytes": 0,
    }


def response_summary(result: Mapping[str, Any]) -> dict[str, Any]:
    status = int_or_none(result.get("status"))
    body = result.get("body")
    body_preview = result.get("body_preview")
    return {
        "status": status,
        "ok": status is not None and 200 <= status < 400,
        "status_text": optional_text(result.get("status_text")),
        "redirected": bool(result.get("redirected")),
        "mime_type": optional_text(result.get("mime_type")),
        "size_bytes": int_or_none(result.get("size_bytes")),
        "stored_size_bytes": int_or_none(result.get("stored_size_bytes")),
        "body_present": bool(result.get("body_available")) or (isinstance(body, str) and bool(body)),
        "body_omitted": bool(result.get("body_omitted")),
        "body_preview_bytes": text_size(body_preview if body_preview is not None else body),
        "body_preview_truncated": bool(result.get("body_preview_truncated")),
        "truncated": bool(result.get("truncated")),
        "redacted": bool(result.get("redacted")),
    }


def text_size(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return len(str(value).encode("utf-8"))
    except Exception:
        return None


def text_contains_redaction_marker(value: Any) -> bool:
    if value is None:
        return False
    normalized = str(value).lower()
    return "[redacted]" in normalized or "%5bredacted%5d" in normalized


def mapping_contains_redaction_marker(value: Mapping[str, Any]) -> bool:
    return any(
        text_contains_redaction_marker(key) or text_contains_redaction_marker(item)
        for key, item in value.items()
    )


def origin(value: str) -> str:
    parsed = urlsplit(value)
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


def safe_origin(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return origin(value)
    except Exception:
        return None


def payload_value_any(payload: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload:
            return payload.get(key)
    return None


def payload_bool_any(payload: Mapping[str, Any], *keys: str) -> bool | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, bool):
            return value
    return None


def body_preview(value: str, *, max_bytes: int) -> tuple[str, bool]:
    if not value or max_bytes <= 0:
        return "", bool(value)
    encoded = value.encode("utf-8")
    if len(encoded) <= max_bytes:
        return value, False
    return encoded[:max_bytes].decode("utf-8", errors="ignore"), True


def string_mapping(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): "" if item is None else str(item) for key, item in value.items()}


def header_value(headers: Mapping[str, str], name: str) -> str | None:
    lowered = name.lower()
    for key, value in headers.items():
        if key.lower() == lowered:
            normalized = value.strip()
            return normalized or None
    return None


def int_or_none(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value)


def dict_value(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def optional_text(value: Any, default: str | None = None) -> str | None:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


__all__ = [
    "SAFE_METHODS",
    "body_preview",
    "dict_value",
    "header_value",
    "int_or_none",
    "mapping_contains_redaction_marker",
    "normalize_header_items",
    "optional_text",
    "origin",
    "payload_bool_any",
    "payload_value_any",
    "response_summary",
    "safe_origin",
    "source_body_state",
    "string_mapping",
    "text_contains_redaction_marker",
    "text_size",
]
