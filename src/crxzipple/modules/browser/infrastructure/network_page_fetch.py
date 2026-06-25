from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from crxzipple.modules.browser.application.events import (
    BROWSER_NETWORK_FETCH_EXECUTED_EVENT,
    BROWSER_NETWORK_FETCH_FAILED_EVENT,
    BROWSER_NETWORK_REPLAY_EXECUTED_EVENT,
    BROWSER_NETWORK_REPLAY_FAILED_EVENT,
    BrowserEventEmitter,
)
from crxzipple.modules.browser.domain import BrowserValidationError
from crxzipple.modules.browser.domain.value_objects import (
    BrowserNetworkBody,
    BrowserNetworkRequest,
)

from .network_capture import DefaultBrowserNetworkRedactor
from .network_page_fetch_analysis import (
    build_fetch_safety,
    build_replay_suitability,
    build_request_diff,
)
from .network_page_fetch_common import response_summary
from .network_page_fetch_events import (
    emit_network_fetch_failure,
    emit_network_fetch_result,
)
from .network_page_fetch_request import (
    build_page_fetch_request,
    replay_body_source,
)
from .network_page_fetch_runtime import execute_page_network_fetch


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
            request = build_page_fetch_request(
                payload=payload,
                page_url=page_url,
                source_kind="manual",
                default_timeout_ms=self.default_timeout_ms,
                default_max_body_bytes=self.default_max_body_bytes,
            )
            result = execute_page_network_fetch(
                page=page,
                redactor=self.redactor,
                request=request,
                kind="network-fetch-as-page",
            )
            result["fetch_safety"] = build_fetch_safety(
                page_url=page_url,
                request=request,
            )
            result["response_summary"] = response_summary(result)
        except Exception as exc:
            emit_network_fetch_failure(
                event_emitter=self.event_emitter,
                redactor=self.redactor,
                event_name=BROWSER_NETWORK_FETCH_FAILED_EVENT,
                operation_kind="network-fetch-as-page",
                page_url=page_url,
                payload=payload,
                request=request,
                error=exc,
            )
            raise
        emit_network_fetch_result(
            event_emitter=self.event_emitter,
            redactor=self.redactor,
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
        body_source = replay_body_source(payload)
        try:
            if "body" not in merged and "json" not in merged and request_body is not None:
                if request_body.redacted:
                    raise BrowserValidationError(
                        "Captured request body was redacted; provide payload.body or payload.json to replay safely.",
                    )
                merged["body"] = request_body.body
                body_source = "captured"
            replay = build_page_fetch_request(
                payload=merged,
                page_url=page_url,
                source_kind="capture",
                default_timeout_ms=self.default_timeout_ms,
                default_max_body_bytes=self.default_max_body_bytes,
            )
            result = execute_page_network_fetch(
                page=page,
                redactor=self.redactor,
                request=replay,
                kind="network-replay-request",
            )
            result["source_request_id"] = request.request_id
            result["source_capture_id"] = request.capture_id
            result["replay_suitability"] = build_replay_suitability(
                page_url=page_url,
                request=request,
                request_body=request_body,
                replay=replay,
                body_source=body_source,
            )
            result["request_diff"] = build_request_diff(
                redactor=self.redactor,
                request=request,
                request_body=request_body,
                replay=replay,
                body_source=body_source,
            )
            result["response_summary"] = response_summary(result)
        except Exception as exc:
            emit_network_fetch_failure(
                event_emitter=self.event_emitter,
                redactor=self.redactor,
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
        emit_network_fetch_result(
            event_emitter=self.event_emitter,
            redactor=self.redactor,
            event_name=BROWSER_NETWORK_REPLAY_EXECUTED_EVENT,
            page_url=page_url,
            payload=merged,
            result=result,
        )
        return result


__all__ = ["BrowserPageNetworkFetchService"]
