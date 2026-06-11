from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping
from urllib.parse import urljoin, urlsplit

from crxzipple.modules.browser.application.events import (
    BROWSER_NETWORK_FETCH_EXECUTED_EVENT,
    BROWSER_NETWORK_FETCH_FAILED_EVENT,
    BROWSER_NETWORK_REPLAY_EXECUTED_EVENT,
    BROWSER_NETWORK_REPLAY_FAILED_EVENT,
    BrowserEventEmitter,
    emit_browser_event,
)
from crxzipple.modules.browser.domain import BrowserValidationError
from crxzipple.modules.browser.domain.value_objects import (
    BrowserNetworkBody,
    BrowserNetworkRequest,
)

from .network_capture import DefaultBrowserNetworkRedactor

_PAGE_FETCH_MARKER = "__crxzipple_browser_network_page_fetch__"
_PAGE_FETCH_EXPRESSION = f"""
/*{_PAGE_FETCH_MARKER}*/
async (raw) => {{
  const input = JSON.parse(String(raw || "{{}}"));
  const method = String(input.method || "GET").toUpperCase();
  const headers = input.headers && typeof input.headers === "object" ? input.headers : {{}};
  const maxBodyBytes = Number.isFinite(Number(input.max_body_bytes)) && Number(input.max_body_bytes) >= 0
    ? Math.floor(Number(input.max_body_bytes))
    : 262144;
  const timeoutMs = Number.isFinite(Number(input.timeout_ms)) && Number(input.timeout_ms) > 0
    ? Math.floor(Number(input.timeout_ms))
    : 30000;
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeoutMs);
  const options = {{
    method,
    headers,
    credentials: "include",
    redirect: "follow",
    signal: controller.signal,
  }};
  if (input.body !== null && input.body !== undefined && method !== "GET" && method !== "HEAD") {{
    options.body = String(input.body);
  }}
  try {{
    const response = await fetch(String(input.url), options);
    const responseHeaders = {{}};
    response.headers.forEach((value, key) => {{
      responseHeaders[key] = value;
    }});
    const bodyText = await response.text();
    const encodedSize = new TextEncoder().encode(bodyText).length;
    const truncated = encodedSize > maxBodyBytes;
    const body = truncated ? bodyText.slice(0, maxBodyBytes) : bodyText;
    return {{
      ok: true,
      url: response.url,
      status: response.status,
      status_text: response.statusText || "",
      redirected: response.redirected,
      headers: responseHeaders,
      body,
      size_bytes: encodedSize,
      stored_size_bytes: new TextEncoder().encode(body).length,
      truncated,
    }};
  }} catch (error) {{
    return {{
      ok: false,
      error: error && error.message ? String(error.message) : String(error),
      error_name: error && error.name ? String(error.name) : null,
    }};
  }} finally {{
    clearTimeout(timeoutId);
  }}
}}
""".strip()

_SENSITIVE_HEADER_NAMES = {
    "authorization",
    "cookie",
    "proxy-authorization",
    "set-cookie",
    "x-api-key",
}
_FORBIDDEN_REQUEST_HEADER_NAMES = {
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
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_SUPPORTED_METHODS = {"GET", "HEAD", "OPTIONS", "POST", "PUT", "PATCH", "DELETE"}
_DEFAULT_BODY_PREVIEW_BYTES = 1200


@dataclass(slots=True)
class BrowserPageNetworkFetchService:
    redactor: DefaultBrowserNetworkRedactor = field(default_factory=DefaultBrowserNetworkRedactor)
    default_timeout_ms: int = 30_000
    default_max_body_bytes: int = 262_144
    event_emitter: BrowserEventEmitter | None = None

    def fetch_as_page(
        self,
        *,
        page: Any,
        page_url: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        request: dict[str, Any] | None = None
        try:
            request = self._request_from_payload(
                payload=payload,
                page_url=page_url,
                source_kind="manual",
            )
            result = self._execute(page=page, request=request, kind="network-fetch-as-page")
            result["fetch_safety"] = self._fetch_safety(
                page_url=page_url,
                request=request,
            )
            result["response_summary"] = _response_summary(result)
        except Exception as exc:
            self._emit_failure(
                event_name=BROWSER_NETWORK_FETCH_FAILED_EVENT,
                operation_kind="network-fetch-as-page",
                page_url=page_url,
                payload=payload,
                request=request,
                error=exc,
            )
            raise
        self._emit_result(
            event_name=BROWSER_NETWORK_FETCH_EXECUTED_EVENT,
            page_url=page_url,
            payload=payload,
            result=result,
        )
        return result

    def replay_request(
        self,
        *,
        page: Any,
        page_url: str,
        payload: Mapping[str, Any],
        request: BrowserNetworkRequest,
        request_body: BrowserNetworkBody | None,
    ) -> dict[str, Any]:
        replay: dict[str, Any] | None = None
        merged: dict[str, Any] = {
            "url": request.url,
            "method": request.method,
            "headers": dict(request.request_headers),
            **dict(payload),
        }
        body_source = _replay_body_source(payload)
        try:
            if "body" not in merged and "json" not in merged and request_body is not None:
                if request_body.redacted:
                    raise BrowserValidationError(
                        "Captured request body was redacted; provide payload.body or payload.json to replay safely.",
                    )
                merged["body"] = request_body.body
                body_source = "captured"
            replay = self._request_from_payload(
                payload=merged,
                page_url=page_url,
                source_kind="capture",
            )
            result = self._execute(page=page, request=replay, kind="network-replay-request")
            result["source_request_id"] = request.request_id
            result["source_capture_id"] = request.capture_id
            result["replay_suitability"] = self._replay_suitability(
                page_url=page_url,
                request=request,
                request_body=request_body,
                replay=replay,
                body_source=body_source,
            )
            result["request_diff"] = self._request_diff(
                request=request,
                request_body=request_body,
                replay=replay,
                body_source=body_source,
            )
            result["response_summary"] = _response_summary(result)
        except Exception as exc:
            self._emit_failure(
                event_name=BROWSER_NETWORK_REPLAY_FAILED_EVENT,
                operation_kind="network-replay-request",
                page_url=page_url,
                payload=merged,
                request=replay,
                error=exc,
                source_request_id=request.request_id,
                source_capture_id=request.capture_id,
            )
            raise
        self._emit_result(
            event_name=BROWSER_NETWORK_REPLAY_EXECUTED_EVENT,
            page_url=page_url,
            payload=merged,
            result=result,
        )
        return result

    def _request_from_payload(
        self,
        *,
        payload: Mapping[str, Any],
        page_url: str,
        source_kind: str,
    ) -> dict[str, Any]:
        url = _normalize_url(
            payload.get("url"),
            page_url=page_url,
            allow_cross_origin=bool(payload.get("allow_cross_origin")),
        )
        method = _normalize_method(payload.get("method"))
        allow_mutating = bool(payload.get("allow_mutating"))
        if method not in _SAFE_METHODS and not allow_mutating:
            raise BrowserValidationError(
                "browser network fetch/replay with a mutating HTTP method requires payload.allow_mutating=true.",
            )
        headers = _sanitize_request_headers(payload.get("headers"))
        body = _body_from_payload(payload)
        if body is not None and method in {"GET", "HEAD"}:
            raise BrowserValidationError("GET and HEAD browser network fetches cannot include a body.")
        if body is not None and not _has_header(headers, "content-type"):
            headers["content-type"] = "application/json" if _payload_has_json(payload) else "text/plain"
        return {
            "url": url,
            "method": method,
            "headers": headers,
            "body": body,
            "source_kind": source_kind,
            "timeout_ms": _positive_int(payload.get("timeout_ms"), self.default_timeout_ms),
            "max_body_bytes": _non_negative_int(
                payload.get("max_body_bytes"),
                self.default_max_body_bytes,
                label="max_body_bytes",
            ),
            "body_preview_bytes": _non_negative_int(
                _payload_value_any(payload, "body_preview_bytes", "bodyPreviewBytes"),
                _DEFAULT_BODY_PREVIEW_BYTES,
                label="body_preview_bytes",
            ),
            "include_body": _payload_bool_any(payload, "include_body", "includeBody") or False,
            "allow_cross_origin": bool(payload.get("allow_cross_origin")),
            "allow_mutating": allow_mutating,
        }

    def _execute(
        self,
        *,
        page: Any,
        request: dict[str, Any],
        kind: str,
    ) -> dict[str, Any]:
        raw_result = page.evaluate(_PAGE_FETCH_EXPRESSION, json.dumps(request))
        if not isinstance(raw_result, Mapping):
            raise BrowserValidationError("Browser page fetch returned an invalid result.")
        if raw_result.get("ok") is not True:
            raise BrowserValidationError(
                f"Browser page fetch failed: {raw_result.get('error') or 'unknown error'}",
            )
        headers = _string_mapping(raw_result.get("headers"))
        body = str(raw_result.get("body") or "")
        mime_type = _header_value(headers, "content-type")
        redacted_body = self.redactor.redact_body(
            body=body,
            kind="response",
            mime_type=mime_type,
            headers=headers,
        )
        body_preview, body_preview_truncated = _body_preview(
            redacted_body,
            max_bytes=int(request.get("body_preview_bytes") or 0),
        )
        include_body = bool(request.get("include_body"))
        result = {
            "kind": kind,
            "request": {
                "url": self.redactor.redact_url(str(request["url"])),
                "method": request["method"],
                "headers": self.redactor.redact_headers(request["headers"]),
                "source_kind": request["source_kind"],
                "allow_cross_origin": request["allow_cross_origin"],
                "allow_mutating": request["allow_mutating"],
                "include_body": include_body,
                "body_preview_bytes": request.get("body_preview_bytes"),
            },
            "url": self.redactor.redact_url(str(raw_result.get("url") or request["url"])),
            "status": int(raw_result.get("status") or 0),
            "status_text": str(raw_result.get("status_text") or ""),
            "redirected": bool(raw_result.get("redirected")),
            "headers": self.redactor.redact_headers(headers),
            "body_preview": body_preview,
            "body_available": bool(redacted_body),
            "body_omitted": bool(redacted_body) and not include_body,
            "body_preview_truncated": body_preview_truncated,
            "mime_type": mime_type,
            "body_kind": "response",
            "base64_encoded": False,
            "size_bytes": _int_or_none(raw_result.get("size_bytes")),
            "stored_size_bytes": _int_or_none(raw_result.get("stored_size_bytes")),
            "truncated": bool(raw_result.get("truncated")),
            "redacted": redacted_body != body,
        }
        if include_body:
            result["body"] = redacted_body
        return result

    def _emit_result(
        self,
        *,
        event_name: str,
        page_url: str,
        payload: Mapping[str, Any],
        result: Mapping[str, Any],
    ) -> None:
        request = _dict(result.get("request"))
        url = _optional_text(result.get("url")) or _optional_text(request.get("url"))
        method = _optional_text(request.get("method"), "GET")
        operation_kind = _optional_text(result.get("kind"), "browser-network")
        status_code = _int_or_none(result.get("status"))
        source_request_id = _optional_text(result.get("source_request_id")) or _optional_text(
            payload.get("request_id"),
        )
        source_capture_id = _optional_text(result.get("source_capture_id")) or _optional_text(
            payload.get("capture_id"),
        )
        emit_browser_event(
            self.event_emitter,
            event_name,
            payload={
                **_event_context(
                    page_url=self.redactor.redact_url(page_url),
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
                "body_size_bytes": _int_or_none(result.get("size_bytes")),
                "stored_size_bytes": _int_or_none(result.get("stored_size_bytes")),
                "summary": _event_summary(method=method, status_code=status_code, url=url),
                "display_label": _event_label(operation_kind),
                "display_summary": _event_summary(method=method, status_code=status_code, url=url),
            },
            status="succeeded",
        )

    def _emit_failure(
        self,
        *,
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
        url = _optional_text(request_payload.get("url")) or _safe_payload_url(
            self.redactor,
            payload=payload,
            page_url=page_url,
        )
        emit_browser_event(
            self.event_emitter,
            event_name,
            payload={
                **_event_context(
                    page_url=self.redactor.redact_url(page_url),
                    payload=payload,
                    request=request_payload,
                    url=url,
                    operation_kind=operation_kind,
                    source_request_id=source_request_id or _optional_text(payload.get("request_id")),
                    source_capture_id=source_capture_id or _optional_text(payload.get("capture_id")),
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

    def _replay_suitability(
        self,
        *,
        page_url: str,
        request: BrowserNetworkRequest,
        request_body: BrowserNetworkBody | None,
        replay: Mapping[str, Any],
        body_source: str,
    ) -> dict[str, Any]:
        method = _optional_text(replay.get("method"), request.method) or "GET"
        page_origin = _safe_origin(page_url)
        target_origin = _safe_origin(_optional_text(replay.get("url")))
        cross_origin_required = (
            page_origin is not None
            and target_origin is not None
            and page_origin != target_origin
        )
        mutating_required = method.upper() not in _SAFE_METHODS
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

        if _text_contains_redaction_marker(request.url):
            warnings.append("Source request URL contains redacted values; replay may not match the original request.")
        if _mapping_contains_redaction_marker(request.request_headers):
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

    def _fetch_safety(
        self,
        *,
        page_url: str,
        request: Mapping[str, Any],
    ) -> dict[str, Any]:
        method = _optional_text(request.get("method"), "GET") or "GET"
        page_origin = _safe_origin(page_url)
        target_origin = _safe_origin(_optional_text(request.get("url")))
        cross_origin_required = (
            page_origin is not None
            and target_origin is not None
            and page_origin != target_origin
        )
        mutating_required = method.upper() not in _SAFE_METHODS
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
                    "size_bytes": _text_size(body),
                },
                "credentials": {
                    "included": True,
                    "source": "browser-page",
                },
            },
        }

    def _request_diff(
        self,
        *,
        request: BrowserNetworkRequest,
        request_body: BrowserNetworkBody | None,
        replay: Mapping[str, Any],
        body_source: str,
    ) -> dict[str, Any]:
        replay_url = _optional_text(replay.get("url")) or ""
        replay_method = _optional_text(replay.get("method"), request.method) or "GET"
        source_headers = _normalize_header_items(_sanitize_request_headers(request.request_headers))
        replay_headers = _normalize_header_items(_dict(replay.get("headers")))
        source_body_state = _source_body_state(request=request, request_body=request_body)
        replay_body = replay.get("body")
        body_changed: bool | None
        if source_body_state["state"] == "available":
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
                "url": self.redactor.redact_url(request.url),
                "method": request.method,
                "header_names": [key for key, _value in source_headers],
                "body": source_body_state,
            },
            "replay": {
                "url": self.redactor.redact_url(replay_url),
                "method": replay_method,
                "header_names": [key for key, _value in replay_headers],
                "body": {
                    "present": replay_body is not None,
                    "size_bytes": _text_size(replay_body),
                },
            },
        }


def _replay_body_source(payload: Mapping[str, Any]) -> str:
    if _payload_has_json(payload):
        return "override-json"
    if "body" in payload and payload.get("body") is not None:
        return "override-body"
    return "none"


def _normalize_header_items(value: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    items: list[tuple[str, str]] = []
    for key, item in value.items():
        normalized_key = str(key).strip().lower()
        if not normalized_key:
            continue
        items.append((normalized_key, "" if item is None else str(item)))
    return tuple(sorted(items))


def _source_body_state(
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


def _response_summary(result: Mapping[str, Any]) -> dict[str, Any]:
    status = _int_or_none(result.get("status"))
    body = result.get("body")
    body_preview = result.get("body_preview")
    return {
        "status": status,
        "ok": status is not None and 200 <= status < 400,
        "status_text": _optional_text(result.get("status_text")),
        "redirected": bool(result.get("redirected")),
        "mime_type": _optional_text(result.get("mime_type")),
        "size_bytes": _int_or_none(result.get("size_bytes")),
        "stored_size_bytes": _int_or_none(result.get("stored_size_bytes")),
        "body_present": bool(result.get("body_available")) or (isinstance(body, str) and bool(body)),
        "body_omitted": bool(result.get("body_omitted")),
        "body_preview_bytes": _text_size(body_preview if body_preview is not None else body),
        "body_preview_truncated": bool(result.get("body_preview_truncated")),
        "truncated": bool(result.get("truncated")),
        "redacted": bool(result.get("redacted")),
    }


def _text_size(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return len(str(value).encode("utf-8"))
    except Exception:
        return None


def _text_contains_redaction_marker(value: Any) -> bool:
    if value is None:
        return False
    normalized = str(value).lower()
    return "[redacted]" in normalized or "%5bredacted%5d" in normalized


def _mapping_contains_redaction_marker(value: Mapping[str, Any]) -> bool:
    return any(
        _text_contains_redaction_marker(key) or _text_contains_redaction_marker(item)
        for key, item in value.items()
    )


def _normalize_url(value: Any, *, page_url: str, allow_cross_origin: bool) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise BrowserValidationError("payload.url is required for browser network fetch.")
    resolved = urljoin(page_url, normalized)
    parsed = urlsplit(resolved)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise BrowserValidationError("browser network fetch only supports http(s) URLs.")
    if not allow_cross_origin and _origin(resolved) != _origin(page_url):
        raise BrowserValidationError(
            "cross-origin browser network fetch requires payload.allow_cross_origin=true.",
        )
    return resolved


def _origin(value: str) -> str:
    parsed = urlsplit(value)
    return f"{parsed.scheme.lower()}://{parsed.netloc.lower()}"


def _normalize_method(value: Any) -> str:
    method = str(value or "GET").strip().upper()
    if method not in _SUPPORTED_METHODS:
        supported = ", ".join(sorted(_SUPPORTED_METHODS))
        raise BrowserValidationError(f"payload.method must be one of: {supported}.")
    return method


def _sanitize_request_headers(value: Any) -> dict[str, str]:
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
        if lowered in _FORBIDDEN_REQUEST_HEADER_NAMES:
            continue
        if lowered in _SENSITIVE_HEADER_NAMES:
            continue
        if item is None:
            continue
        headers[name] = str(item)
    return headers


def _body_from_payload(payload: Mapping[str, Any]) -> str | None:
    if _payload_has_json(payload):
        return json.dumps(payload.get("json"), ensure_ascii=False, separators=(",", ":"))
    body = payload.get("body")
    if body is None:
        return None
    if isinstance(body, (dict, list)):
        return json.dumps(body, ensure_ascii=False, separators=(",", ":"))
    return str(body)


def _payload_has_json(payload: Mapping[str, Any]) -> bool:
    return "json" in payload and payload.get("json") is not None


def _has_header(headers: Mapping[str, str], name: str) -> bool:
    lowered = name.lower()
    return any(key.lower() == lowered for key in headers)


def _positive_int(value: Any, default: int) -> int:
    if value in (None, ""):
        return default
    try:
        resolved = int(value)
    except (TypeError, ValueError) as exc:
        raise BrowserValidationError("payload.timeout_ms must be an integer.") from exc
    if resolved < 1:
        raise BrowserValidationError("payload.timeout_ms must be greater than or equal to 1.")
    return resolved


def _non_negative_int(value: Any, default: int, *, label: str) -> int:
    if value in (None, ""):
        return default
    try:
        resolved = int(value)
    except (TypeError, ValueError) as exc:
        raise BrowserValidationError(f"payload.{label} must be an integer.") from exc
    if resolved < 0:
        raise BrowserValidationError(f"payload.{label} must be greater than or equal to 0.")
    return resolved


def _payload_value_any(payload: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload:
            return payload.get(key)
    return None


def _payload_bool_any(payload: Mapping[str, Any], *keys: str) -> bool | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, bool):
            return value
    return None


def _body_preview(value: str, *, max_bytes: int) -> tuple[str, bool]:
    if not value or max_bytes <= 0:
        return "", bool(value)
    encoded = value.encode("utf-8")
    if len(encoded) <= max_bytes:
        return value, False
    return encoded[:max_bytes].decode("utf-8", errors="ignore"), True


def _string_mapping(value: Any) -> dict[str, str]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): "" if item is None else str(item) for key, item in value.items()}


def _header_value(headers: Mapping[str, str], name: str) -> str | None:
    lowered = name.lower()
    for key, value in headers.items():
        if key.lower() == lowered:
            normalized = value.strip()
            return normalized or None
    return None


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value)


def _dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _optional_text(value: Any, default: str | None = None) -> str | None:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


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
    profile_name = _optional_text(payload.get("profile_name"))
    target_id = _optional_text(payload.get("target_id"))
    capture_id = source_capture_id or _optional_text(payload.get("capture_id"))
    request_method = _optional_text(request.get("method")) or _optional_text(payload.get("method"), "GET")
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
        "source_kind": _optional_text(request.get("source_kind")),
        "allow_cross_origin": bool(request.get("allow_cross_origin") or payload.get("allow_cross_origin")),
        "allow_mutating": bool(request.get("allow_mutating") or payload.get("allow_mutating")),
        "origin": _safe_origin(page_url),
        "target_origin": _safe_origin(url),
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
    raw_url = _optional_text(payload.get("url"))
    if raw_url is None:
        return None
    try:
        return redactor.redact_url(urljoin(page_url, raw_url))
    except Exception:
        return redactor.redact_url(raw_url)


def _safe_origin(value: str | None) -> str | None:
    if value is None:
        return None
    try:
        return _origin(value)
    except Exception:
        return None


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


__all__ = ["BrowserPageNetworkFetchService"]
