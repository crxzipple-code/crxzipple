from __future__ import annotations

from typing import Any, Mapping

from crxzipple.modules.browser.domain.value_objects import (
    BrowserNetworkBody,
    BrowserNetworkRequest,
)

from .network_capture import DefaultBrowserNetworkRedactor
from .network_page_fetch_common import (
    SAFE_METHODS,
    mapping_contains_redaction_marker,
    normalize_header_items,
    optional_text,
    safe_origin,
    source_body_state,
    text_contains_redaction_marker,
    text_size,
)
from .network_page_fetch_request import sanitize_request_headers


def build_replay_suitability(
    *,
    page_url: str,
    request: BrowserNetworkRequest,
    request_body: BrowserNetworkBody | None,
    replay: Mapping[str, Any],
    body_source: str,
) -> dict[str, Any]:
    method = optional_text(replay.get("method"), request.method) or "GET"
    page_origin = safe_origin(page_url)
    target_origin = safe_origin(optional_text(replay.get("url")))
    cross_origin_required = (
        page_origin is not None
        and target_origin is not None
        and page_origin != target_origin
    )
    mutating_required = method.upper() not in SAFE_METHODS
    captured_body_expected = request.request_body_ref is not None
    captured_body_available = request_body is not None
    captured_body_redacted = bool(request_body.redacted) if request_body is not None else False
    warnings: list[str] = []
    reasons: list[str] = []

    if cross_origin_required:
        reasons.append("Cross-origin replay was explicitly allowed.")
    else:
        reasons.append("Replay target stays within the page origin.")

    if mutating_required:
        reasons.append("Mutating HTTP method was explicitly allowed.")
    else:
        reasons.append("Replay uses a safe HTTP method.")

    if body_source == "captured":
        reasons.append("Captured request body was reused.")
    elif body_source in {"override-body", "override-json"}:
        reasons.append("Request body was supplied by the replay payload.")
    elif captured_body_expected:
        warnings.append("Captured request body was not available to replay.")
    else:
        reasons.append("Source request did not require a body.")

    if text_contains_redaction_marker(request.url):
        warnings.append("Source request URL contains redacted values; replay may not match the original request.")
    if mapping_contains_redaction_marker(request.request_headers):
        warnings.append(
            "Source request headers contain redacted values; sensitive headers were not reused.",
        )
    if captured_body_redacted:
        warnings.append("Captured request body was redacted; replay requires an explicit replacement body.")
    if request.failure_text is not None:
        warnings.append("Source request had a captured failure.")

    level = "ready" if not warnings else "warning"
    return {
        "level": level,
        "reasons": reasons,
        "warnings": warnings,
        "gates": {
            "cross_origin": {
                "required": cross_origin_required,
                "allowed": bool(replay.get("allow_cross_origin")),
                "page_origin": page_origin,
                "target_origin": target_origin,
            },
            "mutating_method": {
                "required": mutating_required,
                "allowed": bool(replay.get("allow_mutating")),
                "method": method,
            },
            "captured_body": {
                "required": captured_body_expected,
                "available": captured_body_available,
                "redacted": captured_body_redacted,
                "reused": body_source == "captured",
                "source": body_source,
            },
        },
    }


def build_fetch_safety(
    *,
    page_url: str,
    request: Mapping[str, Any],
) -> dict[str, Any]:
    method = optional_text(request.get("method"), "GET") or "GET"
    page_origin = safe_origin(page_url)
    target_origin = safe_origin(optional_text(request.get("url")))
    cross_origin_required = (
        page_origin is not None
        and target_origin is not None
        and page_origin != target_origin
    )
    mutating_required = method.upper() not in SAFE_METHODS
    body = request.get("body")
    reasons: list[str] = []
    warnings: list[str] = []

    if cross_origin_required:
        warnings.append("Cross-origin page fetch was explicitly allowed.")
    else:
        reasons.append("Fetch target stays within the page origin.")

    if mutating_required:
        warnings.append("Mutating HTTP method was explicitly allowed.")
    else:
        reasons.append("Fetch uses a safe HTTP method.")

    if body is not None:
        reasons.append("Fetch includes an explicit request body.")
    else:
        reasons.append("Fetch has no request body.")

    reasons.append("Fetch runs inside the browser page and includes page credentials.")
    return {
        "level": "ready" if not warnings else "warning",
        "reasons": reasons,
        "warnings": warnings,
        "gates": {
            "cross_origin": {
                "required": cross_origin_required,
                "allowed": bool(request.get("allow_cross_origin")),
                "page_origin": page_origin,
                "target_origin": target_origin,
            },
            "mutating_method": {
                "required": mutating_required,
                "allowed": bool(request.get("allow_mutating")),
                "method": method,
            },
            "body": {
                "present": body is not None,
                "size_bytes": text_size(body),
            },
            "credentials": {
                "included": True,
                "source": "browser-page",
            },
        },
    }


def build_request_diff(
    *,
    redactor: DefaultBrowserNetworkRedactor,
    request: BrowserNetworkRequest,
    request_body: BrowserNetworkBody | None,
    replay: Mapping[str, Any],
    body_source: str,
) -> dict[str, Any]:
    replay_url = optional_text(replay.get("url")) or ""
    replay_method = optional_text(replay.get("method"), request.method) or "GET"
    source_headers = normalize_header_items(sanitize_request_headers(request.request_headers))
    replay_headers = normalize_header_items(_dict(replay.get("headers")))
    source_body = source_body_state(request=request, request_body=request_body)
    replay_body = replay.get("body")
    body_changed: bool | None
    if source_body["state"] == "available":
        body_changed = str(request_body.body) != ("" if replay_body is None else str(replay_body))
    elif request.request_body_ref is None and replay_body is None:
        body_changed = False
    else:
        body_changed = None

    changed_fields: list[str] = []
    if request.url != replay_url:
        changed_fields.append("url")
    if request.method.upper() != replay_method.upper():
        changed_fields.append("method")
    if source_headers != replay_headers:
        changed_fields.append("headers")
    if body_changed is True:
        changed_fields.append("body")
    elif body_changed is None:
        changed_fields.append("body_unknown")

    return {
        "changed_fields": changed_fields,
        "url_changed": request.url != replay_url,
        "method_changed": request.method.upper() != replay_method.upper(),
        "headers_changed": source_headers != replay_headers,
        "body_changed": body_changed,
        "body_source": body_source,
        "source": {
            "url": redactor.redact_url(request.url),
            "method": request.method,
            "header_names": [key for key, _value in source_headers],
            "body": source_body,
        },
        "replay": {
            "url": redactor.redact_url(replay_url),
            "method": replay_method,
            "header_names": [key for key, _value in replay_headers],
            "body": {
                "present": replay_body is not None,
                "size_bytes": text_size(replay_body),
            },
        },
    }


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


__all__ = [
    "build_fetch_safety",
    "build_replay_suitability",
    "build_request_diff",
]
