from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Mapping
from urllib.parse import urlsplit

from .exceptions import BrowserValidationError
from .value_helpers import (
    _ensure_aware_utc,
    _normalize_header_mapping,
    _normalize_mapping,
    _normalize_network_body_kind,
    _normalize_network_capture_status,
    _normalize_network_filter_domain,
    _normalize_network_method,
    _normalize_network_resource_type,
    _normalize_optional_text,
    _normalize_profile_name,
    _normalize_required_text,
    _normalize_status_code,
    _require_non_negative_int,
    _require_positive_int,
)
from .value_types import BrowserNetworkBodyKind, BrowserNetworkCaptureStatus


@dataclass(frozen=True, slots=True)
class BrowserNetworkCapture:
    profile_name: str
    target_id: str
    capture_id: str
    status: BrowserNetworkCaptureStatus = "active"
    max_requests: int = 200
    max_body_bytes: int = 262_144
    request_count: int = 0
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    stopped_at: datetime | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "profile_name",
            _normalize_profile_name(self.profile_name),
        )
        object.__setattr__(
            self,
            "target_id",
            _normalize_required_text(self.target_id, label="target_id"),
        )
        object.__setattr__(
            self,
            "capture_id",
            _normalize_required_text(self.capture_id, label="capture_id"),
        )
        object.__setattr__(
            self,
            "status",
            _normalize_network_capture_status(self.status),
        )
        object.__setattr__(
            self,
            "max_requests",
            _require_positive_int(self.max_requests, label="max_requests") or 200,
        )
        object.__setattr__(
            self,
            "max_body_bytes",
            _require_non_negative_int(self.max_body_bytes, label="max_body_bytes"),
        )
        object.__setattr__(
            self,
            "request_count",
            _require_non_negative_int(self.request_count, label="request_count"),
        )
        started_at = _ensure_aware_utc(self.started_at, label="started_at")
        object.__setattr__(self, "started_at", started_at)
        if self.stopped_at is not None:
            stopped_at = _ensure_aware_utc(self.stopped_at, label="stopped_at")
            if stopped_at < started_at:
                raise BrowserValidationError(
                    "stopped_at must not be before started_at."
                )
            object.__setattr__(self, "stopped_at", stopped_at)
        object.__setattr__(self, "metadata", _normalize_mapping(self.metadata))


@dataclass(frozen=True, slots=True)
class BrowserNetworkBody:
    profile_name: str
    target_id: str
    capture_id: str
    request_id: str
    body_ref: str
    kind: BrowserNetworkBodyKind
    body: str
    mime_type: str | None = None
    base64_encoded: bool = False
    size_bytes: int = 0
    stored_size_bytes: int = 0
    truncated: bool = False
    redacted: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "profile_name",
            _normalize_profile_name(self.profile_name),
        )
        object.__setattr__(
            self,
            "target_id",
            _normalize_required_text(self.target_id, label="target_id"),
        )
        object.__setattr__(
            self,
            "capture_id",
            _normalize_required_text(self.capture_id, label="capture_id"),
        )
        object.__setattr__(
            self,
            "request_id",
            _normalize_required_text(self.request_id, label="request_id"),
        )
        object.__setattr__(
            self,
            "body_ref",
            _normalize_required_text(self.body_ref, label="body_ref"),
        )
        object.__setattr__(self, "kind", _normalize_network_body_kind(self.kind))
        object.__setattr__(self, "body", str(self.body))
        object.__setattr__(self, "mime_type", _normalize_optional_text(self.mime_type))
        object.__setattr__(self, "base64_encoded", bool(self.base64_encoded))
        object.__setattr__(
            self,
            "size_bytes",
            _require_non_negative_int(self.size_bytes, label="size_bytes"),
        )
        object.__setattr__(
            self,
            "stored_size_bytes",
            _require_non_negative_int(
                self.stored_size_bytes,
                label="stored_size_bytes",
            ),
        )
        object.__setattr__(self, "truncated", bool(self.truncated))
        object.__setattr__(self, "redacted", bool(self.redacted))
        object.__setattr__(
            self,
            "created_at",
            _ensure_aware_utc(self.created_at, label="created_at"),
        )


@dataclass(frozen=True, slots=True)
class BrowserNetworkRequest:
    request_id: str
    capture_id: str
    profile_name: str
    target_id: str
    url: str
    method: str
    frame_id: str | None = None
    loader_id: str | None = None
    resource_type: str = "other"
    request_headers: Mapping[str, Any] = field(default_factory=dict)
    request_post_data_preview: str | None = None
    status: int | None = None
    response_headers: Mapping[str, Any] = field(default_factory=dict)
    mime_type: str | None = None
    timing: Mapping[str, Any] = field(default_factory=dict)
    initiator: Mapping[str, Any] = field(default_factory=dict)
    body_ref: str | None = None
    request_body_ref: str | None = None
    failure_text: str | None = None
    encoded_data_length: int | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "request_id",
            _normalize_required_text(self.request_id, label="request_id"),
        )
        object.__setattr__(
            self,
            "capture_id",
            _normalize_required_text(self.capture_id, label="capture_id"),
        )
        object.__setattr__(
            self,
            "profile_name",
            _normalize_profile_name(self.profile_name),
        )
        object.__setattr__(
            self,
            "target_id",
            _normalize_required_text(self.target_id, label="target_id"),
        )
        object.__setattr__(self, "url", _normalize_required_text(self.url, label="url"))
        object.__setattr__(self, "method", _normalize_network_method(self.method))
        object.__setattr__(self, "frame_id", _normalize_optional_text(self.frame_id))
        object.__setattr__(self, "loader_id", _normalize_optional_text(self.loader_id))
        object.__setattr__(
            self,
            "resource_type",
            _normalize_network_resource_type(self.resource_type),
        )
        object.__setattr__(
            self,
            "request_headers",
            _normalize_header_mapping(self.request_headers),
        )
        object.__setattr__(
            self,
            "request_post_data_preview",
            _normalize_optional_text(self.request_post_data_preview),
        )
        object.__setattr__(
            self,
            "status",
            _normalize_status_code(self.status, label="status"),
        )
        object.__setattr__(
            self,
            "response_headers",
            _normalize_header_mapping(self.response_headers),
        )
        object.__setattr__(self, "mime_type", _normalize_optional_text(self.mime_type))
        object.__setattr__(self, "timing", _normalize_mapping(self.timing))
        object.__setattr__(self, "initiator", _normalize_mapping(self.initiator))
        object.__setattr__(self, "body_ref", _normalize_optional_text(self.body_ref))
        object.__setattr__(
            self,
            "request_body_ref",
            _normalize_optional_text(self.request_body_ref),
        )
        object.__setattr__(
            self,
            "failure_text",
            _normalize_optional_text(self.failure_text),
        )
        if self.encoded_data_length is not None:
            object.__setattr__(
                self,
                "encoded_data_length",
                _require_non_negative_int(
                    self.encoded_data_length,
                    label="encoded_data_length",
                ),
            )
        created_at = _ensure_aware_utc(self.created_at, label="created_at")
        object.__setattr__(self, "created_at", created_at)
        if self.completed_at is not None:
            completed_at = _ensure_aware_utc(self.completed_at, label="completed_at")
            if completed_at < created_at:
                raise BrowserValidationError(
                    "completed_at must not be before created_at."
                )
            object.__setattr__(self, "completed_at", completed_at)


@dataclass(frozen=True, slots=True)
class BrowserNetworkRequestFilter:
    resource_type: str | None = None
    domain: str | None = None
    path: str | None = None
    method: str | None = None
    status: int | None = None
    status_min: int | None = None
    status_max: int | None = None
    initiator: str | None = None
    mime_type: str | None = None
    keyword: str | None = None
    created_after: datetime | None = None
    created_before: datetime | None = None
    limit: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "resource_type",
            _normalize_network_resource_type(self.resource_type)
            if self.resource_type is not None
            else None,
        )
        object.__setattr__(
            self,
            "domain",
            _normalize_network_filter_domain(self.domain),
        )
        object.__setattr__(self, "path", _normalize_optional_text(self.path))
        object.__setattr__(
            self,
            "method",
            (
                _normalize_network_method(self.method)
                if self.method is not None
                else None
            ),
        )
        object.__setattr__(
            self,
            "status",
            _normalize_status_code(self.status, label="status"),
        )
        object.__setattr__(
            self,
            "status_min",
            _normalize_status_code(self.status_min, label="status_min"),
        )
        object.__setattr__(
            self,
            "status_max",
            _normalize_status_code(self.status_max, label="status_max"),
        )
        if (
            self.status_min is not None
            and self.status_max is not None
            and self.status_max < self.status_min
        ):
            raise BrowserValidationError("status_max must not be less than status_min.")
        object.__setattr__(self, "initiator", _normalize_optional_text(self.initiator))
        object.__setattr__(self, "mime_type", _normalize_optional_text(self.mime_type))
        object.__setattr__(self, "keyword", _normalize_optional_text(self.keyword))
        if self.created_after is not None:
            object.__setattr__(
                self,
                "created_after",
                _ensure_aware_utc(self.created_after, label="created_after"),
            )
        if self.created_before is not None:
            object.__setattr__(
                self,
                "created_before",
                _ensure_aware_utc(self.created_before, label="created_before"),
            )
        if (
            self.created_after is not None
            and self.created_before is not None
            and self.created_before < self.created_after
        ):
            raise BrowserValidationError(
                "created_before must not be before created_after.",
            )
        object.__setattr__(
            self,
            "limit",
            _require_positive_int(self.limit, label="limit"),
        )

    def matches(self, request: BrowserNetworkRequest) -> bool:
        if (
            self.resource_type is not None
            and request.resource_type != self.resource_type
        ):
            return False
        parsed = urlsplit(request.url)
        if self.domain is not None and self.domain not in parsed.netloc.lower():
            return False
        if self.path is not None and self.path not in parsed.path:
            return False
        if self.method is not None and request.method != self.method:
            return False
        if self.status is not None and request.status != self.status:
            return False
        if self.status_min is not None and (
            request.status is None or request.status < self.status_min
        ):
            return False
        if self.status_max is not None and (
            request.status is None or request.status > self.status_max
        ):
            return False
        if (
            self.initiator is not None
            and self.initiator.lower()
            not in str(
                request.initiator,
            ).lower()
        ):
            return False
        if self.mime_type is not None and (
            request.mime_type is None
            or self.mime_type.lower() not in request.mime_type.lower()
        ):
            return False
        if self.created_after is not None and request.created_at < self.created_after:
            return False
        if self.created_before is not None and request.created_at > self.created_before:
            return False
        if (
            self.keyword is not None
            and self.keyword.lower()
            not in _request_search_text(
                request,
            )
        ):
            return False
        return True


def _request_search_text(request: BrowserNetworkRequest) -> str:
    parts: list[str] = [
        request.request_id,
        request.url,
        request.method,
        request.resource_type,
        str(request.status or ""),
        request.mime_type or "",
        request.request_post_data_preview or "",
        request.failure_text or "",
        str(request.initiator),
    ]
    parts.extend(request.request_headers.keys())
    parts.extend(request.response_headers.keys())
    return "\n".join(parts).lower()
