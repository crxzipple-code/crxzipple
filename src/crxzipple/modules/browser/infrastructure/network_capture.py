from __future__ import annotations

import base64
from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
import re
from typing import Mapping
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from crxzipple.modules.browser.application.ports import (
    BrowserNetworkCaptureStore,
    BrowserNetworkRedactor,
)
from crxzipple.modules.browser.domain import BrowserValidationError
from crxzipple.modules.browser.domain.value_objects import (
    BrowserNetworkBody,
    BrowserNetworkBodyKind,
    BrowserNetworkCapture,
    BrowserNetworkRequest,
    BrowserNetworkRequestFilter,
)

_REDACTED = "[redacted]"
_SENSITIVE_HEADER_NAMES = {
    "authorization",
    "cookie",
    "proxy-authorization",
    "set-cookie",
    "x-api-key",
}
_SENSITIVE_NAME_PARTS = {
    "api_key",
    "apikey",
    "auth",
    "authorization",
    "credential",
    "password",
    "passwd",
    "secret",
    "token",
}
_BODY_SECRET_RE = re.compile(
    r"(?i)([\"']?(?:api[_-]?key|authorization|credential|password|passwd|secret|token)[\"']?\s*[:=]\s*[\"']?)([^&\s,\"'}]+)",
)


@dataclass(frozen=True, slots=True)
class DefaultBrowserNetworkRedactor(BrowserNetworkRedactor):
    def redact_url(self, url: str) -> str:
        parsed = urlsplit(url)
        if not parsed.query:
            return url
        pairs = parse_qsl(parsed.query, keep_blank_values=True)
        redacted_pairs = [
            (key, _REDACTED if _is_sensitive_name(key) else value)
            for key, value in pairs
        ]
        return urlunsplit(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                urlencode(redacted_pairs),
                parsed.fragment,
            ),
        )

    def redact_headers(self, headers: Mapping[str, str]) -> dict[str, str]:
        redacted: dict[str, str] = {}
        for key, value in headers.items():
            redacted[key] = _REDACTED if _is_sensitive_header(key) else str(value)
        return redacted

    def redact_body(
        self,
        *,
        body: str,
        kind: BrowserNetworkBodyKind,
        mime_type: str | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> str:
        del kind, mime_type, headers
        return _BODY_SECRET_RE.sub(r"\1" + _REDACTED, body)


@dataclass(slots=True)
class _CaptureState:
    capture: BrowserNetworkCapture
    requests: OrderedDict[str, BrowserNetworkRequest] = field(
        default_factory=OrderedDict,
    )
    bodies: dict[str, BrowserNetworkBody] = field(default_factory=dict)


@dataclass(slots=True)
class InMemoryBrowserNetworkCaptureStore(BrowserNetworkCaptureStore):
    redactor: BrowserNetworkRedactor | None = field(
        default_factory=DefaultBrowserNetworkRedactor,
    )
    _captures: dict[tuple[str, str, str], _CaptureState] = field(default_factory=dict)

    def start_capture(self, capture: BrowserNetworkCapture) -> BrowserNetworkCapture:
        key = _capture_key(
            profile_name=capture.profile_name,
            target_id=capture.target_id,
            capture_id=capture.capture_id,
        )
        if key in self._captures:
            raise BrowserValidationError(
                f"Browser network capture '{capture.capture_id}' already exists.",
            )
        self._captures[key] = _CaptureState(capture=deepcopy(capture))
        return deepcopy(capture)

    def stop_capture(
        self,
        *,
        profile_name: str,
        target_id: str,
        capture_id: str,
        stopped_at: datetime,
    ) -> BrowserNetworkCapture | None:
        state = self._captures.get(
            _capture_key(
                profile_name=profile_name,
                target_id=target_id,
                capture_id=capture_id,
            ),
        )
        if state is None:
            return None
        state.capture = replace(
            state.capture,
            status="stopped",
            stopped_at=stopped_at,
        )
        return deepcopy(state.capture)

    def get_capture(
        self,
        *,
        profile_name: str,
        target_id: str,
        capture_id: str,
    ) -> BrowserNetworkCapture | None:
        state = self._captures.get(
            _capture_key(
                profile_name=profile_name,
                target_id=target_id,
                capture_id=capture_id,
            ),
        )
        if state is None:
            return None
        return deepcopy(state.capture)

    def list_captures(
        self,
        *,
        profile_name: str | None = None,
        target_id: str | None = None,
    ) -> tuple[BrowserNetworkCapture, ...]:
        normalized_profile = _optional_profile_name(profile_name)
        normalized_target = _optional_text(target_id)
        captures = []
        for (stored_profile, stored_target, _capture_id), state in self._captures.items():
            if normalized_profile is not None and stored_profile != normalized_profile:
                continue
            if normalized_target is not None and stored_target != normalized_target:
                continue
            captures.append(deepcopy(state.capture))
        return tuple(sorted(captures, key=lambda item: (item.started_at, item.capture_id)))

    def save_request(self, request: BrowserNetworkRequest) -> BrowserNetworkRequest:
        state = self._require_active_state(
            profile_name=request.profile_name,
            target_id=request.target_id,
            capture_id=request.capture_id,
        )
        sanitized = self._sanitize_request(request)
        state.requests[sanitized.request_id] = deepcopy(sanitized)
        self._trim_requests(state)
        state.capture = replace(state.capture, request_count=len(state.requests))
        return deepcopy(sanitized)

    def list_requests(
        self,
        *,
        profile_name: str,
        target_id: str,
        capture_id: str,
        filters: BrowserNetworkRequestFilter | None = None,
    ) -> tuple[BrowserNetworkRequest, ...]:
        state = self._captures.get(
            _capture_key(
                profile_name=profile_name,
                target_id=target_id,
                capture_id=capture_id,
            ),
        )
        if state is None:
            return ()
        records: list[BrowserNetworkRequest] = []
        for request in state.requests.values():
            if filters is not None and not filters.matches(request):
                continue
            records.append(deepcopy(request))
            if filters is not None and filters.limit is not None and len(records) >= filters.limit:
                break
        return tuple(records)

    def get_request(
        self,
        *,
        profile_name: str,
        target_id: str,
        capture_id: str,
        request_id: str,
    ) -> BrowserNetworkRequest | None:
        state = self._captures.get(
            _capture_key(
                profile_name=profile_name,
                target_id=target_id,
                capture_id=capture_id,
            ),
        )
        if state is None:
            return None
        request = state.requests.get(_required_text(request_id, label="request_id"))
        if request is None:
            return None
        return deepcopy(request)

    def store_body(
        self,
        *,
        profile_name: str,
        target_id: str,
        capture_id: str,
        request_id: str,
        kind: BrowserNetworkBodyKind,
        body: str | bytes,
        mime_type: str | None = None,
        headers: Mapping[str, str] | None = None,
        created_at: datetime | None = None,
    ) -> BrowserNetworkBody:
        state = self._require_active_state(
            profile_name=profile_name,
            target_id=target_id,
            capture_id=capture_id,
        )
        normalized_request_id = _required_text(request_id, label="request_id")
        body_ref = f"{normalized_request_id}:{kind}"
        prepared = _prepare_body(
            body=body,
            max_body_bytes=state.capture.max_body_bytes,
            kind=kind,
            mime_type=mime_type,
            headers=headers,
            redactor=self.redactor,
        )
        record = BrowserNetworkBody(
            profile_name=profile_name,
            target_id=target_id,
            capture_id=capture_id,
            request_id=normalized_request_id,
            body_ref=body_ref,
            kind=kind,
            mime_type=mime_type,
            body=prepared.body,
            base64_encoded=prepared.base64_encoded,
            size_bytes=prepared.size_bytes,
            stored_size_bytes=prepared.stored_size_bytes,
            truncated=prepared.truncated,
            redacted=prepared.redacted,
            created_at=created_at or datetime.now(timezone.utc),
        )
        state.bodies[record.body_ref] = deepcopy(record)
        self._attach_body_to_request(state, record)
        return deepcopy(record)

    def get_body(
        self,
        *,
        profile_name: str,
        target_id: str,
        capture_id: str,
        body_ref: str,
    ) -> BrowserNetworkBody | None:
        state = self._captures.get(
            _capture_key(
                profile_name=profile_name,
                target_id=target_id,
                capture_id=capture_id,
            ),
        )
        if state is None:
            return None
        body = state.bodies.get(_required_text(body_ref, label="body_ref"))
        if body is None:
            return None
        return deepcopy(body)

    def clear_capture(
        self,
        *,
        profile_name: str,
        target_id: str,
        capture_id: str,
    ) -> None:
        self._captures.pop(
            _capture_key(
                profile_name=profile_name,
                target_id=target_id,
                capture_id=capture_id,
            ),
            None,
        )

    def _require_active_state(
        self,
        *,
        profile_name: str,
        target_id: str,
        capture_id: str,
    ) -> _CaptureState:
        state = self._captures.get(
            _capture_key(
                profile_name=profile_name,
                target_id=target_id,
                capture_id=capture_id,
            ),
        )
        if state is None:
            raise BrowserValidationError(
                f"Browser network capture '{capture_id}' was not found.",
            )
        if state.capture.status != "active":
            raise BrowserValidationError(
                f"Browser network capture '{capture_id}' is not active.",
            )
        return state

    def _sanitize_request(self, request: BrowserNetworkRequest) -> BrowserNetworkRequest:
        if self.redactor is None:
            return request
        return replace(
            request,
            url=self.redactor.redact_url(request.url),
            request_headers=self.redactor.redact_headers(request.request_headers),
            response_headers=self.redactor.redact_headers(request.response_headers),
        )

    def _trim_requests(self, state: _CaptureState) -> None:
        while len(state.requests) > state.capture.max_requests:
            _request_id, evicted = state.requests.popitem(last=False)
            self._delete_request_bodies(state, request_id=evicted.request_id)

    def _delete_request_bodies(self, state: _CaptureState, *, request_id: str) -> None:
        stale_refs = [
            body_ref
            for body_ref, body in state.bodies.items()
            if body.request_id == request_id
        ]
        for body_ref in stale_refs:
            state.bodies.pop(body_ref, None)

    def _attach_body_to_request(
        self,
        state: _CaptureState,
        body: BrowserNetworkBody,
    ) -> None:
        request = state.requests.get(body.request_id)
        if request is None:
            return
        if body.kind == "request":
            updated = replace(
                request,
                request_body_ref=body.body_ref,
                request_post_data_preview=body.body,
            )
        else:
            updated = replace(
                request,
                body_ref=body.body_ref,
                mime_type=body.mime_type or request.mime_type,
            )
        state.requests[updated.request_id] = updated


@dataclass(frozen=True, slots=True)
class _PreparedBody:
    body: str
    base64_encoded: bool
    size_bytes: int
    stored_size_bytes: int
    truncated: bool
    redacted: bool


def _prepare_body(
    *,
    body: str | bytes,
    max_body_bytes: int,
    kind: BrowserNetworkBodyKind,
    mime_type: str | None,
    headers: Mapping[str, str] | None,
    redactor: BrowserNetworkRedactor | None,
) -> _PreparedBody:
    if isinstance(body, bytes):
        limited = body[:max_body_bytes]
        return _PreparedBody(
            body=base64.b64encode(limited).decode("ascii"),
            base64_encoded=True,
            size_bytes=len(body),
            stored_size_bytes=len(limited),
            truncated=len(body) > len(limited),
            redacted=False,
        )

    text = str(body)
    original_bytes = text.encode("utf-8")
    limited_text, truncated = _truncate_text(text, max_body_bytes)
    redacted_text = (
        redactor.redact_body(
            body=limited_text,
            kind=kind,
            mime_type=mime_type,
            headers=headers,
        )
        if redactor is not None
        else limited_text
    )
    redacted = redacted_text != limited_text
    final_text, redaction_truncated = _truncate_text(redacted_text, max_body_bytes)
    stored_size_bytes = len(final_text.encode("utf-8"))
    return _PreparedBody(
        body=final_text,
        base64_encoded=False,
        size_bytes=len(original_bytes),
        stored_size_bytes=stored_size_bytes,
        truncated=truncated or redaction_truncated,
        redacted=redacted,
    )


def _truncate_text(value: str, limit: int) -> tuple[str, bool]:
    if limit < 1:
        return "", bool(value)
    encoded = value.encode("utf-8")
    if len(encoded) <= limit:
        return value, False
    truncated = encoded[:limit].decode("utf-8", errors="ignore")
    return truncated, True


def _capture_key(
    *,
    profile_name: str,
    target_id: str,
    capture_id: str,
) -> tuple[str, str, str]:
    return (
        _required_text(profile_name, label="profile_name").lower(),
        _required_text(target_id, label="target_id"),
        _required_text(capture_id, label="capture_id"),
    )


def _optional_profile_name(value: str | None) -> str | None:
    normalized = _optional_text(value)
    return normalized.lower() if normalized is not None else None


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _required_text(value: str, *, label: str) -> str:
    normalized = _optional_text(value)
    if normalized is None:
        raise BrowserValidationError(f"{label} is required.")
    return normalized


def _is_sensitive_header(name: str) -> bool:
    return name.strip().lower() in _SENSITIVE_HEADER_NAMES


def _is_sensitive_name(name: str) -> bool:
    normalized = name.strip().lower().replace("-", "_")
    return any(part in normalized for part in _SENSITIVE_NAME_PARTS)
