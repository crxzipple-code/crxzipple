from __future__ import annotations

import json
from typing import Any, Mapping
from urllib.parse import urljoin, urlsplit

from crxzipple.modules.browser.domain import BrowserValidationError

from .network_page_fetch_common import (
    SAFE_METHODS,
    origin,
    payload_bool_any,
    payload_value_any,
)

SENSITIVE_HEADER_NAMES = {
    "authorization",
    "cookie",
    "proxy-authorization",
    "set-cookie",
    "x-api-key",
}
FORBIDDEN_REQUEST_HEADER_NAMES = {
    "connection",
    "content-length",
    "cookie",
    "host",
    "origin",
    "proxy-authorization",
    "referer",
    "set-cookie",
    "user-agent",
}
SUPPORTED_METHODS = {"GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"}
DEFAULT_BODY_PREVIEW_BYTES = 1200


def build_page_fetch_request(
    *,
    payload: Mapping[str, Any],
    page_url: str,
    source_kind: str,
    default_timeout_ms: int,
    default_max_body_bytes: int,
) -> dict[str, Any]:
    url = normalize_url(
        payload.get("url"),
        page_url=page_url,
        allow_cross_origin=bool(payload.get("allow_cross_origin")),
    )
    method = normalize_method(payload.get("method"))
    allow_mutating = bool(payload.get("allow_mutating"))
    if method not in SAFE_METHODS and not allow_mutating:
        raise BrowserValidationError(
            "browser network fetch/replay with a mutating HTTP method requires payload.allow_mutating=true.",
        )
    headers = sanitize_request_headers(payload.get("headers"))
    body = body_from_payload(payload)
    if body is not None and method in {"GET", "HEAD"}:
        raise BrowserValidationError("GET and HEAD browser network fetches cannot include a body.")
    if body is not None and not has_header(headers, "content-type"):
        headers["content-type"] = "application/json" if payload_has_json(payload) else "text/plain"
    return {
        "url": url,
        "method": method,
        "headers": headers,
        "body": body,
        "source_kind": source_kind,
        "timeout_ms": positive_int(payload.get("timeout_ms"), default_timeout_ms),
        "max_body_bytes": non_negative_int(
            payload.get("max_body_bytes"),
            default_max_body_bytes,
            label="max_body_bytes",
        ),
        "body_preview_bytes": non_negative_int(
            payload_value_any(payload, "body_preview_bytes", "bodyPreviewBytes"),
            DEFAULT_BODY_PREVIEW_BYTES,
            label="body_preview_bytes",
        ),
        "include_body": payload_bool_any(payload, "include_body", "includeBody") or False,
        "allow_cross_origin": bool(payload.get("allow_cross_origin")),
        "allow_mutating": allow_mutating,
    }


def replay_body_source(payload: Mapping[str, Any]) -> str:
    if payload_has_json(payload):
        return "override-json"
    if "body" in payload and payload.get("body") is not None:
        return "override-body"
    return "none"


def normalize_url(value: Any, *, page_url: str, allow_cross_origin: bool) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise BrowserValidationError("payload.url is required for browser network fetch.")
    resolved = urljoin(page_url, normalized)
    parsed = urlsplit(resolved)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise BrowserValidationError("browser network fetch only supports http(s) URLs.")
    if not allow_cross_origin and origin(resolved) != origin(page_url):
        raise BrowserValidationError(
            "cross-origin browser network fetch requires payload.allow_cross_origin=true.",
        )
    return resolved


def normalize_method(value: Any) -> str:
    method = str(value or "GET").strip().upper()
    if method not in SUPPORTED_METHODS:
        supported = ", ".join(sorted(SUPPORTED_METHODS))
        raise BrowserValidationError(f"payload.method must be one of: {supported}.")
    return method


def sanitize_request_headers(value: Any) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, Mapping):
        raise BrowserValidationError("payload.headers must be an object.")
    headers: dict[str, str] = {}
    for key, item in value.items():
        name = str(key).strip()
        if not name:
            continue
        lowered = name.lower()
        if lowered in FORBIDDEN_REQUEST_HEADER_NAMES:
            continue
        if lowered in SENSITIVE_HEADER_NAMES:
            continue
        if item is None:
            continue
        headers[name] = str(item)
    return headers


def body_from_payload(payload: Mapping[str, Any]) -> str | None:
    if payload_has_json(payload):
        return json.dumps(payload.get("json"), ensure_ascii=False, separators=(",", ":"))
    body = payload.get("body")
    if body is None:
        return None
    if isinstance(body, (dict, list)):
        return json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    return str(body)


def payload_has_json(payload: Mapping[str, Any]) -> bool:
    return "json" in payload and payload.get("json") is not None


def has_header(headers: Mapping[str, str], name: str) -> bool:
    lowered = name.lower()
    return any(key.lower() == lowered for key in headers)


def positive_int(value: Any, default: int) -> int:
    if value in (None, ""):
        return default
    try:
        resolved = int(value)
    except (TypeError, ValueError) as exc:
        raise BrowserValidationError("payload.timeout_ms must be an integer.") from exc
    if resolved < 1:
        raise BrowserValidationError("payload.timeout_ms must be greater than or equal to 1.")
    return resolved


def non_negative_int(value: Any, default: int, *, label: str) -> int:
    if value in (None, ""):
        return default
    try:
        resolved = int(value)
    except (TypeError, ValueError) as exc:
        raise BrowserValidationError(f"payload.{label} must be an integer.") from exc
    if resolved < 0:
        raise BrowserValidationError(f"payload.{label} must be greater than or equal to 0.")
    return resolved


__all__ = [
    "DEFAULT_BODY_PREVIEW_BYTES",
    "build_page_fetch_request",
    "replay_body_source",
    "sanitize_request_headers",
]
