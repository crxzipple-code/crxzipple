from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any, Mapping

from crxzipple.modules.browser.application.network_capture import (
    BrowserNetworkCaptureService,
)
from crxzipple.modules.browser.domain import (
    BrowserExecutionPlan,
    BrowserPageActionCommand,
    BrowserTab,
    BrowserValidationError,
)
from crxzipple.modules.browser.domain.value_objects import (
    BrowserNetworkBody,
    BrowserNetworkCapture,
    BrowserNetworkRequest,
    BrowserNetworkRequestFilter,
)

from .network_cdp_capture import CdpNetworkCaptureController
from .error_projection import display_safe_exception_message
from .network_insight import NETWORK_PERFORMANCE_EXPRESSION
from .network_page_fetch import BrowserPageNetworkFetchService


@dataclass(slots=True)
class BrowserNetworkActionService:
    network_capture_service: BrowserNetworkCaptureService
    network_page_fetch_service: BrowserPageNetworkFetchService
    network_capture_controller: CdpNetworkCaptureController | None = None

    def execute(
        self,
        *,
        plan: BrowserExecutionPlan,
        tab: BrowserTab,
        page: Any,
        command: BrowserPageActionCommand,
    ) -> dict[str, Any]:
        profile_name = plan.profile.name
        target_id = tab.target_id
        if command.kind == "network-start-capture":
            metadata = {
                "source": "browser.network.start_capture",
                "target_url": tab.url,
            }
            extra_metadata = _payload_mapping_any(command.payload, "metadata")
            if extra_metadata is not None:
                metadata.update(extra_metadata)
            capture = self.network_capture_service.start_capture(
                profile_name=profile_name,
                target_id=target_id,
                capture_id=_payload_text_any(
                    command.payload,
                    "capture_id",
                    "captureId",
                ),
                max_requests=(
                    _payload_int_any(command.payload, "max_requests", "maxRequests", minimum=1)
                    or 200
                ),
                max_body_bytes=(
                    _payload_int_any(command.payload, "max_body_bytes", "maxBodyBytes", minimum=0)
                    or 262_144
                ),
                metadata=metadata,
            )
            errors: list[dict[str, str]] = []
            if self.network_capture_controller is not None:
                errors.extend(
                    self.network_capture_controller.start_capture(
                        profile_name=profile_name,
                        target_id=target_id,
                        capture_id=capture.capture_id,
                        page=page,
                    )
                )
            return {
                "kind": command.kind,
                "capture": _serialize_network_capture(capture),
                "profile_name": profile_name,
                "target_id": target_id,
                "capture_id": capture.capture_id,
                "status": capture.status,
                "max_requests": capture.max_requests,
                "max_body_bytes": capture.max_body_bytes,
                "requests": [],
                "request_count": 0,
                "errors": errors,
            }

        if command.kind == "network-fetch-as-page":
            result = self.network_page_fetch_service.fetch_as_page(
                page=page,
                page_url=tab.url,
                payload={
                    **dict(command.payload),
                    "profile_name": profile_name,
                    "target_id": target_id,
                },
            )
            return {
                **result,
                "profile_name": profile_name,
                "target_id": target_id,
                "errors": [],
            }

        capture_id = self._network_capture_id(
            profile_name=profile_name,
            target_id=target_id,
            payload=command.payload,
            allow_missing_fallback=command.kind == "network-list-requests",
        )

        if command.kind == "network-stop-capture":
            if self.network_capture_controller is not None:
                self.network_capture_controller.stop_capture(
                    profile_name=profile_name,
                    target_id=target_id,
                    capture_id=capture_id,
                )
            capture = self.network_capture_service.stop_capture(
                profile_name=profile_name,
                target_id=target_id,
                capture_id=capture_id,
            )
            return {
                "kind": command.kind,
                "capture": _serialize_network_capture(capture),
                "requests": [],
                "request_count": capture.request_count,
                "errors": [],
            }

        if command.kind == "network-clear-capture":
            if self.network_capture_controller is not None:
                self.network_capture_controller.stop_capture(
                    profile_name=profile_name,
                    target_id=target_id,
                    capture_id=capture_id,
                )
            self.network_capture_service.clear(
                profile_name=profile_name,
                target_id=target_id,
                capture_id=capture_id,
            )
            return {
                "kind": command.kind,
                "capture_id": capture_id,
                "profile": profile_name,
                "target_id": target_id,
                "cleared": True,
                "errors": [],
            }

        if command.kind == "network-list-requests":
            capture = self._network_capture(
                profile_name=profile_name,
                target_id=target_id,
                capture_id=capture_id,
            )
            errors: list[dict[str, str]] = []
            subscribed = (
                self.network_capture_controller is not None
                and self.network_capture_controller.is_subscribed(
                    profile_name=profile_name,
                    target_id=target_id,
                    capture_id=capture_id,
                )
            )
            if capture.status == "active" and not subscribed:
                errors.extend(
                    self._harvest_performance_network_entries(
                        profile_name=profile_name,
                        target_id=target_id,
                        capture_id=capture_id,
                        page=page,
                        payload=command.payload,
                    )
                )
            filters = _network_request_filter_from_payload(command.payload)
            requests = self.network_capture_service.list_requests(
                profile_name=profile_name,
                target_id=target_id,
                capture_id=capture_id,
                filters=filters,
            )
            return {
                "kind": command.kind,
                "capture": _serialize_network_capture(
                    self._network_capture(
                        profile_name=profile_name,
                        target_id=target_id,
                        capture_id=capture_id,
                    )
                ),
                "requests": [
                    _serialize_network_request(request)
                    for request in requests
                ],
                "request_count": len(requests),
                "total_count": len(requests),
                "filters": _serialize_network_filters(filters),
                "errors": errors,
            }

        if command.kind == "network-get-request":
            request_id = _payload_text_any(
                command.payload,
                "request_id",
                "requestId",
            )
            if request_id is None:
                raise BrowserValidationError(
                    "payload.request_id is required for network-get-request.",
                )
            request = self.network_capture_service.get_request(
                profile_name=profile_name,
                target_id=target_id,
                capture_id=capture_id,
                request_id=request_id,
            )
            return {
                "kind": command.kind,
                "capture": _serialize_network_capture(
                    self._network_capture(
                        profile_name=profile_name,
                        target_id=target_id,
                        capture_id=capture_id,
                    )
                ),
                "request": _serialize_network_request(request),
                **_serialize_network_request(request),
                "errors": [],
            }

        if command.kind == "network-get-response-body":
            request_id = _payload_text_any(
                command.payload,
                "request_id",
                "requestId",
            )
            if request_id is None:
                raise BrowserValidationError(
                    "payload.request_id is required for network-get-response-body.",
                )
            request = self.network_capture_service.get_request(
                profile_name=profile_name,
                target_id=target_id,
                capture_id=capture_id,
                request_id=request_id,
            )
            errors: list[dict[str, str]] = []
            try:
                body = self.network_capture_service.get_response_body(
                    profile_name=profile_name,
                    target_id=target_id,
                    capture_id=capture_id,
                    request_id=request_id,
                )
            except BrowserValidationError:
                if self.network_capture_controller is None:
                    raise
                errors.extend(
                    self.network_capture_controller.fetch_response_body(
                        profile_name=profile_name,
                        target_id=target_id,
                        capture_id=capture_id,
                        request_id=request_id,
                        page=page,
                    )
                )
                body = self.network_capture_service.get_response_body(
                    profile_name=profile_name,
                    target_id=target_id,
                    capture_id=capture_id,
                    request_id=request_id,
                )
            return {
                "kind": command.kind,
                "capture": _serialize_network_capture(
                    self._network_capture(
                        profile_name=profile_name,
                        target_id=target_id,
                        capture_id=capture_id,
                    )
                ),
                "request": _serialize_network_request(request),
                **_serialize_network_body(body),
                "errors": errors,
            }

        if command.kind == "network-get-request-body":
            request_id = _payload_text_any(
                command.payload,
                "request_id",
                "requestId",
            )
            if request_id is None:
                raise BrowserValidationError(
                    "payload.request_id is required for network-get-request-body.",
                )
            request = self.network_capture_service.get_request(
                profile_name=profile_name,
                target_id=target_id,
                capture_id=capture_id,
                request_id=request_id,
            )
            body = self.network_capture_service.get_request_body(
                profile_name=profile_name,
                target_id=target_id,
                capture_id=capture_id,
                request_id=request_id,
            )
            return {
                "kind": command.kind,
                "capture": _serialize_network_capture(
                    self._network_capture(
                        profile_name=profile_name,
                        target_id=target_id,
                        capture_id=capture_id,
                    )
                ),
                "request": _serialize_network_request(request),
                **_serialize_network_body(body),
                "errors": [],
            }

        if command.kind == "network-replay-request":
            request_id = _payload_text_any(
                command.payload,
                "request_id",
                "requestId",
            )
            if request_id is None:
                raise BrowserValidationError(
                    "payload.request_id is required for network-replay-request.",
                )
            request = self.network_capture_service.get_request(
                profile_name=profile_name,
                target_id=target_id,
                capture_id=capture_id,
                request_id=request_id,
            )
            request_body = None
            if request.request_body_ref is not None:
                request_body = self.network_capture_service.get_request_body(
                    profile_name=profile_name,
                    target_id=target_id,
                    capture_id=capture_id,
                    request_id=request_id,
                )
            result = self.network_page_fetch_service.replay_request(
                page=page,
                page_url=tab.url,
                payload={
                    **dict(command.payload),
                    "profile_name": profile_name,
                    "target_id": target_id,
                },
                request=request,
                request_body=request_body,
            )
            return {
                **result,
                "capture": _serialize_network_capture(
                    self._network_capture(
                        profile_name=profile_name,
                        target_id=target_id,
                        capture_id=capture_id,
                    )
                ),
                "source_request": _serialize_network_request(request),
                "profile_name": profile_name,
                "target_id": target_id,
                "errors": [],
            }

        raise BrowserValidationError(f"Unsupported browser network kind '{command.kind}'.")

    def _network_capture_id(
        self,
        *,
        profile_name: str,
        target_id: str,
        payload: Mapping[str, Any],
        allow_missing_fallback: bool = False,
    ) -> str:
        capture_id = _payload_text_any(payload, "capture_id", "captureId")
        if capture_id is not None and capture_id.strip().lower() not in {
            "active",
            "latest",
        }:
            if allow_missing_fallback:
                captures = self.network_capture_service.list_captures(
                    profile_name=profile_name,
                    target_id=target_id,
                )
                if any(capture.capture_id == capture_id for capture in captures):
                    return capture_id
                active = [capture for capture in captures if capture.status == "active"]
                candidates = active or list(captures)
                if candidates:
                    return candidates[-1].capture_id
            return capture_id
        captures = self.network_capture_service.list_captures(
            profile_name=profile_name,
            target_id=target_id,
        )
        active = [capture for capture in captures if capture.status == "active"]
        candidates = active or list(captures)
        if not candidates:
            raise BrowserValidationError(
                "No browser network capture is active for the current tab. "
                "Run browser.network.start_capture first, trigger the page behavior, "
                "then call browser.network.list_requests with the returned capture_id "
                "or capture_id='active'.",
            )
        return candidates[-1].capture_id

    def _network_capture(
        self,
        *,
        profile_name: str,
        target_id: str,
        capture_id: str,
    ) -> BrowserNetworkCapture:
        for capture in self.network_capture_service.list_captures(
            profile_name=profile_name,
            target_id=target_id,
        ):
            if capture.capture_id == capture_id:
                return capture
        raise BrowserValidationError(
            f"Browser network capture '{capture_id}' was not found.",
        )

    def _harvest_performance_network_entries(
        self,
        *,
        profile_name: str,
        target_id: str,
        capture_id: str,
        page: Any,
        payload: Mapping[str, Any],
    ) -> list[dict[str, str]]:
        limit = _payload_int_any(payload, "limit", minimum=1) or 50
        errors: list[dict[str, str]] = []
        try:
            raw_entries = page.evaluate(
                NETWORK_PERFORMANCE_EXPRESSION,
                {
                    "limit": limit,
                    "include_navigation": True,
                    "include_resources": True,
                },
            )
        except Exception as exc:  # pragma: no cover - live browser variance
            return [
                {
                    "source": "performance_entries",
                    "message": display_safe_exception_message(exc),
                }
            ]
        entries = raw_entries.get("entries") if isinstance(raw_entries, dict) else None
        if not isinstance(entries, list):
            return errors
        for index, raw_entry in enumerate(entries):
            if not isinstance(raw_entry, Mapping):
                continue
            url = _payload_text_any(raw_entry, "name")
            if url is None:
                continue
            request_id = _performance_request_id(raw_entry, index=index)
            try:
                request = self.network_capture_service.record_request(
                    profile_name=profile_name,
                    target_id=target_id,
                    capture_id=capture_id,
                    request_id=request_id,
                    url=url,
                    method="GET",
                    resource_type=_performance_resource_type(raw_entry),
                    timing=dict(raw_entry),
                    initiator={
                        "type": _payload_text_any(raw_entry, "initiator_type")
                        or _payload_text_any(raw_entry, "entry_type")
                        or "performance",
                    },
                )
                status = _performance_status(raw_entry)
                if status is not None:
                    self.network_capture_service.record_response(
                        profile_name=profile_name,
                        target_id=target_id,
                        capture_id=capture_id,
                        request_id=request.request_id,
                        status=status,
                        timing=dict(raw_entry),
                    )
                encoded_length = _performance_encoded_length(raw_entry)
                self.network_capture_service.record_loading_finished(
                    profile_name=profile_name,
                    target_id=target_id,
                    capture_id=capture_id,
                    request_id=request.request_id,
                    encoded_data_length=encoded_length,
                )
            except BrowserValidationError as exc:
                errors.append(
                    {
                        "source": "performance_entry",
                        "message": display_safe_exception_message(exc),
                    }
                )
        return errors


def _network_request_filter_from_payload(
    payload: Mapping[str, Any],
) -> BrowserNetworkRequestFilter:
    raw_filters = payload.get("filters")
    filters = dict(raw_filters) if isinstance(raw_filters, Mapping) else {}

    def text(*keys: str) -> str | None:
        return _payload_text_any(payload, *keys) or _payload_text_any(filters, *keys)

    def integer(*keys: str, minimum: int = 0) -> int | None:
        for source in (payload, filters):
            value = _payload_value_any(source, *keys)
            if value is None:
                continue
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise BrowserValidationError(f"payload.{keys[0]} must be an integer.")
            resolved = int(value)
            if resolved < minimum:
                raise BrowserValidationError(
                    f"payload.{keys[0]} must be greater than or equal to {minimum}.",
                )
            return resolved
        return None

    return BrowserNetworkRequestFilter(
        resource_type=text("resource_type", "resourceType"),
        domain=text("domain"),
        path=text("path"),
        method=text("method"),
        status=integer("status"),
        status_min=integer("status_min", "statusMin"),
        status_max=integer("status_max", "statusMax"),
        initiator=text("initiator"),
        mime_type=text("mime_type", "mimeType"),
        keyword=text("keyword"),
        limit=integer("limit", minimum=1),
    )


def _serialize_network_filters(filters: BrowserNetworkRequestFilter) -> dict[str, Any]:
    return {
        "resource_type": filters.resource_type,
        "domain": filters.domain,
        "path": filters.path,
        "method": filters.method,
        "status": filters.status,
        "status_min": filters.status_min,
        "status_max": filters.status_max,
        "initiator": filters.initiator,
        "mime_type": filters.mime_type,
        "keyword": filters.keyword,
        "limit": filters.limit,
    }


def _serialize_network_capture(capture: BrowserNetworkCapture) -> dict[str, Any]:
    return {
        "profile_name": capture.profile_name,
        "target_id": capture.target_id,
        "capture_id": capture.capture_id,
        "status": capture.status,
        "max_requests": capture.max_requests,
        "max_body_bytes": capture.max_body_bytes,
        "request_count": capture.request_count,
        "started_at": capture.started_at.isoformat(),
        "stopped_at": (
            capture.stopped_at.isoformat()
            if capture.stopped_at is not None
            else None
        ),
        "metadata": dict(capture.metadata),
    }


def _serialize_network_request(request: BrowserNetworkRequest) -> dict[str, Any]:
    return {
        "request_id": request.request_id,
        "capture_id": request.capture_id,
        "profile_name": request.profile_name,
        "target_id": request.target_id,
        "frame_id": request.frame_id,
        "loader_id": request.loader_id,
        "url": request.url,
        "method": request.method,
        "resource_type": request.resource_type,
        "request_headers": dict(request.request_headers),
        "request_post_data_preview": request.request_post_data_preview,
        "status": request.status,
        "response_headers": dict(request.response_headers),
        "mime_type": request.mime_type,
        "timing": dict(request.timing),
        "initiator": dict(request.initiator),
        "body_ref": request.body_ref,
        "request_body_ref": request.request_body_ref,
        "failure_text": request.failure_text,
        "encoded_data_length": request.encoded_data_length,
        "created_at": request.created_at.isoformat(),
        "completed_at": (
            request.completed_at.isoformat()
            if request.completed_at is not None
            else None
        ),
    }


def _serialize_network_body(body: BrowserNetworkBody) -> dict[str, Any]:
    return {
        "body_ref": body.body_ref,
        "request_id": body.request_id,
        "capture_id": body.capture_id,
        "profile_name": body.profile_name,
        "target_id": body.target_id,
        "body_kind": body.kind,
        "body": body.body,
        "mime_type": body.mime_type,
        "base64_encoded": body.base64_encoded,
        "size_bytes": body.size_bytes,
        "stored_size_bytes": body.stored_size_bytes,
        "truncated": body.truncated,
        "redacted": body.redacted,
        "created_at": body.created_at.isoformat(),
    }


def _performance_request_id(entry: Mapping[str, Any], *, index: int) -> str:
    seed = "|".join(
        str(entry.get(key) or "")
        for key in ("name", "entry_type", "initiator_type", "start_time")
    )
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()[:16]
    return f"perf-{index}-{digest}"


def _performance_resource_type(entry: Mapping[str, Any]) -> str:
    initiator = str(entry.get("initiator_type") or "").strip().lower()
    entry_type = str(entry.get("entry_type") or "").strip().lower()
    if entry_type == "navigation":
        return "document"
    if initiator in {"xmlhttprequest", "xhr"}:
        return "xhr"
    if initiator in {"fetch", "script", "img", "image", "css", "link"}:
        return "stylesheet" if initiator in {"css", "link"} else initiator
    return entry_type or initiator or "other"


def _performance_status(entry: Mapping[str, Any]) -> int | None:
    value = entry.get("response_status")
    if value is None or isinstance(value, bool):
        return None
    if not isinstance(value, (int, float)):
        return None
    status = int(value)
    return status if status > 0 else None


def _performance_encoded_length(entry: Mapping[str, Any]) -> int | None:
    for key in ("encoded_body_size", "transfer_size", "decoded_body_size"):
        value = entry.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        numeric = int(value)
        if numeric >= 0:
            return numeric
    return None


def _payload_text_any(
    payload: Mapping[str, Any],
    *keys: str,
) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _payload_mapping_any(
    payload: Mapping[str, Any],
    *keys: str,
) -> dict[str, Any] | None:
    value = _payload_value_any(payload, *keys)
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise BrowserValidationError(f"payload.{keys[0]} must be an object.")
    return _json_safe_payload(dict(value))


def _payload_value_any(
    payload: Mapping[str, Any],
    *keys: str,
) -> Any:
    for key in keys:
        if key in payload:
            return payload.get(key)
    return None


def _json_safe_payload(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_safe_payload(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe_payload(item) for item in value]
    return str(value)


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
