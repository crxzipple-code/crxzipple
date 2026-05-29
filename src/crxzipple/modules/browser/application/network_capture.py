from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any, Mapping
from uuid import uuid4

from crxzipple.modules.browser.application.events import (
    BROWSER_NETWORK_CAPTURE_STARTED_EVENT,
    BROWSER_NETWORK_CAPTURE_STOPPED_EVENT,
    BROWSER_NETWORK_REQUEST_FAILED_EVENT,
    BROWSER_NETWORK_REQUEST_OBSERVED_EVENT,
    BrowserEventEmitter,
    emit_browser_event,
)
from crxzipple.modules.browser.domain import BrowserValidationError
from crxzipple.modules.browser.domain.value_objects import (
    BrowserNetworkBody,
    BrowserNetworkCapture,
    BrowserNetworkRequest,
    BrowserNetworkRequestFilter,
)

from .ports import BrowserNetworkCaptureStore


def _default_capture_id() -> str:
    return uuid4().hex


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class BrowserNetworkCaptureService:
    capture_store: BrowserNetworkCaptureStore
    capture_id_factory: Callable[[], str] = _default_capture_id
    clock: Callable[[], datetime] = _utc_now
    event_emitter: BrowserEventEmitter | None = None

    def start_capture(
        self,
        *,
        profile_name: str,
        target_id: str,
        capture_id: str | None = None,
        max_requests: int = 200,
        max_body_bytes: int = 262_144,
        metadata: Mapping[str, Any] | None = None,
    ) -> BrowserNetworkCapture:
        capture = BrowserNetworkCapture(
            profile_name=profile_name,
            target_id=target_id,
            capture_id=capture_id or self.capture_id_factory(),
            max_requests=max_requests,
            max_body_bytes=max_body_bytes,
            started_at=self.clock(),
            metadata=metadata or {},
        )
        stored = self.capture_store.start_capture(capture)
        self._emit_capture_event(BROWSER_NETWORK_CAPTURE_STARTED_EVENT, stored, status="started")
        return stored

    def stop_capture(
        self,
        *,
        profile_name: str,
        target_id: str,
        capture_id: str,
    ) -> BrowserNetworkCapture:
        capture = self.capture_store.stop_capture(
            profile_name=profile_name,
            target_id=target_id,
            capture_id=capture_id,
            stopped_at=self.clock(),
        )
        if capture is None:
            raise BrowserValidationError(
                f"Browser network capture '{capture_id}' was not found.",
            )
        self._emit_capture_event(BROWSER_NETWORK_CAPTURE_STOPPED_EVENT, capture, status="stopped")
        return capture

    def list_captures(
        self,
        *,
        profile_name: str | None = None,
        target_id: str | None = None,
    ) -> tuple[BrowserNetworkCapture, ...]:
        return self.capture_store.list_captures(
            profile_name=profile_name,
            target_id=target_id,
        )

    def record_request(
        self,
        *,
        profile_name: str,
        target_id: str,
        capture_id: str,
        request_id: str,
        url: str,
        method: str,
        resource_type: str = "other",
        frame_id: str | None = None,
        loader_id: str | None = None,
        request_headers: Mapping[str, Any] | None = None,
        request_post_data: str | bytes | None = None,
        timing: Mapping[str, Any] | None = None,
        initiator: Mapping[str, Any] | None = None,
        created_at: datetime | None = None,
    ) -> BrowserNetworkRequest:
        self._require_capture(
            profile_name=profile_name,
            target_id=target_id,
            capture_id=capture_id,
            active_required=True,
        )
        observed_at = created_at or self.clock()
        request = BrowserNetworkRequest(
            request_id=request_id,
            capture_id=capture_id,
            profile_name=profile_name,
            target_id=target_id,
            frame_id=frame_id,
            loader_id=loader_id,
            url=url,
            method=method,
            resource_type=resource_type,
            request_headers=request_headers or {},
            timing=timing or {},
            initiator=initiator or {},
            created_at=observed_at,
        )
        if request_post_data is not None:
            request_body = self.capture_store.store_body(
                profile_name=profile_name,
                target_id=target_id,
                capture_id=capture_id,
                request_id=request.request_id,
                kind="request",
                body=request_post_data,
                headers=_string_headers(request_headers),
                created_at=observed_at,
            )
            request = replace(
                request,
                request_post_data_preview=request_body.body,
                request_body_ref=request_body.body_ref,
            )
        stored = self.capture_store.save_request(request)
        self._emit_request_event(
            BROWSER_NETWORK_REQUEST_OBSERVED_EVENT,
            stored,
            status="observed",
        )
        return stored

    def record_response(
        self,
        *,
        profile_name: str,
        target_id: str,
        capture_id: str,
        request_id: str,
        status: int,
        response_headers: Mapping[str, Any] | None = None,
        mime_type: str | None = None,
        timing: Mapping[str, Any] | None = None,
        completed_at: datetime | None = None,
    ) -> BrowserNetworkRequest:
        request = self._require_request(
            profile_name=profile_name,
            target_id=target_id,
            capture_id=capture_id,
            request_id=request_id,
        )
        updated = replace(
            request,
            status=status,
            response_headers=response_headers or {},
            mime_type=mime_type,
            timing={**request.timing, **dict(timing or {})},
            completed_at=completed_at or request.completed_at,
        )
        return self.capture_store.save_request(updated)

    def record_loading_finished(
        self,
        *,
        profile_name: str,
        target_id: str,
        capture_id: str,
        request_id: str,
        encoded_data_length: int | None = None,
        completed_at: datetime | None = None,
    ) -> BrowserNetworkRequest:
        request = self._require_request(
            profile_name=profile_name,
            target_id=target_id,
            capture_id=capture_id,
            request_id=request_id,
        )
        updated = replace(
            request,
            encoded_data_length=encoded_data_length,
            completed_at=completed_at or self.clock(),
        )
        return self.capture_store.save_request(updated)

    def record_failure(
        self,
        *,
        profile_name: str,
        target_id: str,
        capture_id: str,
        request_id: str,
        failure_text: str,
        completed_at: datetime | None = None,
    ) -> BrowserNetworkRequest:
        request = self._require_request(
            profile_name=profile_name,
            target_id=target_id,
            capture_id=capture_id,
            request_id=request_id,
        )
        updated = replace(
            request,
            failure_text=failure_text,
            completed_at=completed_at or self.clock(),
        )
        stored = self.capture_store.save_request(updated)
        self._emit_request_event(
            BROWSER_NETWORK_REQUEST_FAILED_EVENT,
            stored,
            status="failed",
            level="warning",
        )
        return stored

    def record_response_body(
        self,
        *,
        profile_name: str,
        target_id: str,
        capture_id: str,
        request_id: str,
        body: str | bytes,
        mime_type: str | None = None,
        created_at: datetime | None = None,
    ) -> BrowserNetworkBody:
        request = self._require_request(
            profile_name=profile_name,
            target_id=target_id,
            capture_id=capture_id,
            request_id=request_id,
        )
        return self.capture_store.store_body(
            profile_name=profile_name,
            target_id=target_id,
            capture_id=capture_id,
            request_id=request_id,
            kind="response",
            body=body,
            mime_type=mime_type or request.mime_type,
            headers=request.response_headers,
            created_at=created_at or self.clock(),
        )

    def list_requests(
        self,
        *,
        profile_name: str,
        target_id: str,
        capture_id: str,
        filters: BrowserNetworkRequestFilter | None = None,
        resource_type: str | None = None,
        domain: str | None = None,
        path: str | None = None,
        method: str | None = None,
        status: int | None = None,
        status_min: int | None = None,
        status_max: int | None = None,
        initiator: str | None = None,
        mime_type: str | None = None,
        keyword: str | None = None,
        created_after: datetime | None = None,
        created_before: datetime | None = None,
        limit: int | None = None,
    ) -> tuple[BrowserNetworkRequest, ...]:
        self._require_capture(
            profile_name=profile_name,
            target_id=target_id,
            capture_id=capture_id,
        )
        request_filter = filters or BrowserNetworkRequestFilter(
            resource_type=resource_type,
            domain=domain,
            path=path,
            method=method,
            status=status,
            status_min=status_min,
            status_max=status_max,
            initiator=initiator,
            mime_type=mime_type,
            keyword=keyword,
            created_after=created_after,
            created_before=created_before,
            limit=limit,
        )
        return self.capture_store.list_requests(
            profile_name=profile_name,
            target_id=target_id,
            capture_id=capture_id,
            filters=request_filter,
        )

    def get_request(
        self,
        *,
        profile_name: str,
        target_id: str,
        capture_id: str,
        request_id: str,
    ) -> BrowserNetworkRequest:
        return self._require_request(
            profile_name=profile_name,
            target_id=target_id,
            capture_id=capture_id,
            request_id=request_id,
        )

    def get_request_body(
        self,
        *,
        profile_name: str,
        target_id: str,
        capture_id: str,
        request_id: str,
    ) -> BrowserNetworkBody:
        request = self._require_request(
            profile_name=profile_name,
            target_id=target_id,
            capture_id=capture_id,
            request_id=request_id,
        )
        if request.request_body_ref is None:
            raise BrowserValidationError(
                f"Browser network request '{request_id}' has no stored request body.",
            )
        return self._require_body(
            profile_name=profile_name,
            target_id=target_id,
            capture_id=capture_id,
            body_ref=request.request_body_ref,
        )

    def get_response_body(
        self,
        *,
        profile_name: str,
        target_id: str,
        capture_id: str,
        request_id: str,
    ) -> BrowserNetworkBody:
        request = self._require_request(
            profile_name=profile_name,
            target_id=target_id,
            capture_id=capture_id,
            request_id=request_id,
        )
        if request.body_ref is None:
            raise BrowserValidationError(
                f"Browser network request '{request_id}' has no stored response body.",
            )
        return self._require_body(
            profile_name=profile_name,
            target_id=target_id,
            capture_id=capture_id,
            body_ref=request.body_ref,
        )

    def clear(
        self,
        *,
        profile_name: str,
        target_id: str,
        capture_id: str,
    ) -> None:
        self.capture_store.clear_capture(
            profile_name=profile_name,
            target_id=target_id,
            capture_id=capture_id,
        )

    def _require_capture(
        self,
        *,
        profile_name: str,
        target_id: str,
        capture_id: str,
        active_required: bool = False,
    ) -> BrowserNetworkCapture:
        capture = self.capture_store.get_capture(
            profile_name=profile_name,
            target_id=target_id,
            capture_id=capture_id,
        )
        if capture is None:
            raise BrowserValidationError(
                f"Browser network capture '{capture_id}' was not found.",
            )
        if active_required and capture.status != "active":
            raise BrowserValidationError(
                f"Browser network capture '{capture_id}' is not active.",
            )
        return capture

    def _require_request(
        self,
        *,
        profile_name: str,
        target_id: str,
        capture_id: str,
        request_id: str,
    ) -> BrowserNetworkRequest:
        request = self.capture_store.get_request(
            profile_name=profile_name,
            target_id=target_id,
            capture_id=capture_id,
            request_id=request_id,
        )
        if request is None:
            raise BrowserValidationError(
                f"Browser network request '{request_id}' was not found.",
            )
        return request

    def _require_body(
        self,
        *,
        profile_name: str,
        target_id: str,
        capture_id: str,
        body_ref: str,
    ) -> BrowserNetworkBody:
        body = self.capture_store.get_body(
            profile_name=profile_name,
            target_id=target_id,
            capture_id=capture_id,
            body_ref=body_ref,
        )
        if body is None:
            raise BrowserValidationError(
                f"Browser network body '{body_ref}' was not found.",
            )
        return body

    def _emit_capture_event(
        self,
        event_name: str,
        capture: BrowserNetworkCapture,
        *,
        status: str,
    ) -> None:
        emit_browser_event(
            self.event_emitter,
            event_name,
            status=status,
            level="info",
            payload={
                "profile_name": capture.profile_name,
                "target_id": capture.target_id,
                "capture_id": capture.capture_id,
                "request_count": capture.request_count,
                "max_requests": capture.max_requests,
                "max_body_bytes": capture.max_body_bytes,
            },
        )

    def _emit_request_event(
        self,
        event_name: str,
        request: BrowserNetworkRequest,
        *,
        status: str,
        level: str = "info",
    ) -> None:
        emit_browser_event(
            self.event_emitter,
            event_name,
            status=status,
            level=level,
            payload={
                "profile_name": request.profile_name,
                "target_id": request.target_id,
                "capture_id": request.capture_id,
                "request_id": request.request_id,
                "url": request.url,
                "method": request.method,
                "resource_type": request.resource_type,
                "status_code": request.status,
                "failure_text": request.failure_text,
            },
        )


def _string_headers(headers: Mapping[str, Any] | None) -> dict[str, str]:
    return {
        str(key): "" if value is None else str(value)
        for key, value in dict(headers or {}).items()
    }
