from __future__ import annotations

from typing import Any, Mapping
from urllib.parse import urljoin

from crxzipple.modules.browser.application.events import (
    BrowserEventEmitter,
    emit_browser_event,
)

from .network_capture import DefaultBrowserNetworkRedactor
from .network_page_fetch_common import (
    dict_value,
    int_or_none,
    optional_text,
    safe_origin,
)


def emit_network_fetch_result(
    *,
    event_emitter: BrowserEventEmitter | None,
    redactor: DefaultBrowserNetworkRedactor,
    event_name: str,
    page_url: str,
    payload: Mapping[str, Any],
    result: Mapping[str, Any],
) -> None:
    request = dict_value(result.get("request"))
    url = optional_text(result.get("url")) or optional_text(request.get("url"))
    method = optional_text(request.get("method"), "GET")
    operation_kind = optional_text(result.get("kind"), "browser-network")
    status_code = int_or_none(result.get("status"))
    source_request_id = optional_text(result.get("source_request_id")) or optional_text(
        payload.get("request_id"),
    )
    source_capture_id = optional_text(result.get("source_capture_id")) or optional_text(
        payload.get("capture_id"),
    )
    emit_browser_event(
        event_emitter,
        event_name,
        payload={
            **_event_context(
                page_url=redactor.redact_url(page_url),
                payload=payload,
                request=request,
                url=url,
                operation_kind=operation_kind,
                source_request_id=source_request_id,
                source_capture_id=source_capture_id,
            ),
            "status_code": status_code,
            "redacted": bool(result.get("redacted")),
            "truncated": bool(result.get("truncated")),
            "body_size_bytes": int_or_none(result.get("size_bytes")),
            "stored_size_bytes": int_or_none(result.get("stored_size_bytes")),
            "summary": _event_summary(method=method, status_code=status_code, url=url),
            "display_label": _event_label(operation_kind),
            "display_summary": _event_summary(method=method, status_code=status_code, url=url),
        },
        status="succeeded",
    )


def emit_network_fetch_failure(
    *,
    event_emitter: BrowserEventEmitter | None,
    redactor: DefaultBrowserNetworkRedactor,
    event_name: str,
    operation_kind: str,
    page_url: str,
    payload: Mapping[str, Any],
    request: Mapping[str, Any] | None,
    error: Exception,
    source_request_id: str | None = None,
    source_capture_id: str | None = None,
) -> None:
    request_payload = dict(request or {})
    url = optional_text(request_payload.get("url")) or _safe_payload_url(
        redactor,
        payload=payload,
        page_url=page_url,
    )
    emit_browser_event(
        event_emitter,
        event_name,
        payload={
            **_event_context(
                page_url=redactor.redact_url(page_url),
                payload=payload,
                request=request_payload,
                url=url,
                operation_kind=operation_kind,
                source_request_id=source_request_id or optional_text(payload.get("request_id")),
                source_capture_id=source_capture_id or optional_text(payload.get("capture_id")),
            ),
            "error_type": type(error).__name__,
            "error_message": _safe_error_message(error),
            "summary": _failure_summary(operation_kind=operation_kind, url=url),
            "display_label": _event_label(operation_kind),
            "display_summary": _failure_summary(operation_kind=operation_kind, url=url),
        },
        status="failed",
        level="error",
    )


def _event_context(
    *,
    page_url: str,
    payload: Mapping[str, Any],
    request: Mapping[str, Any],
    url: str | None,
    operation_kind: str,
    source_request_id: str | None,
    source_capture_id: str | None,
) -> dict[str, Any]:
    profile_name = optional_text(payload.get("profile_name"))
    target_id = optional_text(payload.get("target_id"))
    capture_id = source_capture_id or optional_text(payload.get("capture_id"))
    request_method = optional_text(request.get("method")) or optional_text(payload.get("method"), "GET")
    return {
        "entity_type": "browser.network_operation",
        "entity_id": _network_operation_entity_id(
            operation_kind=operation_kind,
            profile_name=profile_name,
            target_id=target_id,
            source_request_id=source_request_id,
        ),
        "operation_kind": operation_kind,
        "profile_name": profile_name,
        "target_id": target_id,
        "capture_id": capture_id,
        "request_id": source_request_id,
        "source_request_id": source_request_id,
        "source_capture_id": source_capture_id,
        "page_url": page_url,
        "url": url,
        "method": request_method,
        "source_kind": optional_text(request.get("source_kind")),
        "allow_cross_origin": bool(request.get("allow_cross_origin") or payload.get("allow_cross_origin")),
        "allow_mutating": bool(request.get("allow_mutating") or payload.get("allow_mutating")),
        "origin": safe_origin(page_url),
        "target_origin": safe_origin(url),
    }


def _network_operation_entity_id(
    *,
    operation_kind: str,
    profile_name: str | None,
    target_id: str | None,
    source_request_id: str | None,
) -> str:
    parts = [
        operation_kind,
        profile_name or "unknown-profile",
        target_id or "unknown-target",
    ]
    if source_request_id is not None:
        parts.append(source_request_id)
    return ":".join(parts)


def _safe_payload_url(
    redactor: DefaultBrowserNetworkRedactor,
    *,
    payload: Mapping[str, Any],
    page_url: str,
) -> str | None:
    raw_url = optional_text(payload.get("url"))
    if raw_url is None:
        return None
    try:
        return redactor.redact_url(urljoin(page_url, raw_url))
    except Exception:
        return redactor.redact_url(raw_url)


def _event_label(operation_kind: str) -> str:
    if operation_kind == "network-replay-request":
        return "Browser network replay"
    if operation_kind == "network-fetch-as-page":
        return "Browser page fetch"
    return "Browser network operation"


def _event_summary(*, method: str | None, status_code: int | None, url: str | None) -> str:
    method_label = method or "GET"
    status_label = str(status_code) if status_code is not None else "-"
    url_label = url or "-"
    return f"{method_label} {url_label} -> {status_label}"


def _failure_summary(*, operation_kind: str, url: str | None) -> str:
    return f"{operation_kind} failed for {url or '-'}"


def _safe_error_message(error: Exception) -> str:
    text = str(error).strip()
    if not text:
        text = type(error).__name__
    return text[:500]


__all__ = ["emit_network_fetch_failure", "emit_network_fetch_result"]
