from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .observation_projection import _build_observation_payload
from .observation_values import (
    _payload_bool,
    _payload_int,
    _payload_text,
    _payload_text_list,
)
from .tool_application import (
    BrowserToolApplicationError,
    BrowserToolApplicationService,
    BrowserToolExecutionResult,
)


@dataclass(slots=True)
class BrowserObservationService:
    """Build an agent-friendly browser page observation from owner applications."""

    tool_application_service: BrowserToolApplicationService

    def observe(
        self,
        *,
        profile_name: str,
        target_id: str | None = None,
        payload: Mapping[str, Any] | None = None,
        timeout_ms: int | None = None,
    ) -> BrowserToolExecutionResult:
        normalized_payload = dict(payload or {})
        tabs = self._tabs(
            profile_name=profile_name,
            include=_payload_bool(normalized_payload, "include_tabs", default=True),
            timeout_ms=timeout_ms,
        )
        snapshot = self._snapshot(
            profile_name=profile_name,
            target_id=target_id,
            payload=normalized_payload,
            timeout_ms=timeout_ms,
        )
        resolved_target_id = (
            _payload_text(snapshot.payload.get("target_id")) or target_id
        )
        console = self._optional_page_action(
            profile_name=profile_name,
            target_id=resolved_target_id,
            kind="console",
            include=_payload_bool(normalized_payload, "include_console", default=True),
            payload={
                "limit": _payload_int(normalized_payload, "console_limit", default=20),
            },
            timeout_ms=timeout_ms,
        )
        page_errors = self._optional_page_action(
            profile_name=profile_name,
            target_id=resolved_target_id,
            kind="page-errors",
            include=_payload_bool(
                normalized_payload, "include_page_errors", default=False
            ),
            payload={
                "limit": _payload_int(
                    normalized_payload, "page_error_limit", default=20
                ),
                "console_limit": _payload_int(
                    normalized_payload,
                    "console_error_limit",
                    default=50,
                ),
                "page_error_limit": _payload_int(
                    normalized_payload,
                    "page_exception_limit",
                    default=50,
                ),
            },
            timeout_ms=timeout_ms,
        )
        include_runtime = _payload_bool(
            normalized_payload, "include_runtime", default=True
        )
        runtime = self._optional_page_action(
            profile_name=profile_name,
            target_id=resolved_target_id,
            kind="runtime-inspect",
            include=include_runtime,
            payload={
                "limit": _payload_int(normalized_payload, "runtime_limit", default=40),
                "include_storage": _payload_bool(
                    normalized_payload,
                    "include_storage",
                    default=False,
                ),
                "include_performance": False,
                "global_names": _payload_text_list(
                    normalized_payload.get("runtime_global_names"),
                ),
            },
            timeout_ms=timeout_ms,
        )
        network_runtime = self._optional_page_action(
            profile_name=profile_name,
            target_id=resolved_target_id,
            kind="network-inspect",
            include=include_runtime
            and _payload_bool(
                normalized_payload,
                "include_network_runtime",
                default=True,
            ),
            payload={
                "limit": _payload_int(normalized_payload, "runtime_limit", default=40),
                "include_navigation": True,
                "include_resources": True,
                "include_cdp_tree": _payload_bool(
                    normalized_payload,
                    "include_resource_tree",
                    default=True,
                ),
                "include_performance_metrics": _payload_bool(
                    normalized_payload,
                    "include_performance_metrics",
                    default=True,
                ),
            },
            timeout_ms=timeout_ms,
        )
        network_requests = self._optional_page_action(
            profile_name=profile_name,
            target_id=resolved_target_id,
            kind="network-list-requests",
            include=_payload_bool(
                normalized_payload,
                "include_network_capture",
                default=False,
            ),
            payload={
                "capture_id": _payload_text(normalized_payload.get("capture_id"))
                or "default",
                "limit": _payload_int(normalized_payload, "network_limit", default=20),
            },
            timeout_ms=timeout_ms,
        )
        scripts = self._optional_page_action(
            profile_name=profile_name,
            target_id=resolved_target_id,
            kind="script-list",
            include=_payload_bool(normalized_payload, "include_scripts", default=True),
            payload={
                "limit": _payload_int(normalized_payload, "script_limit", default=12),
                "wait_ms": _payload_int(
                    normalized_payload, "script_wait_ms", default=50
                ),
                "url_contains": _payload_text(
                    normalized_payload.get("script_url_contains"),
                ),
            },
            timeout_ms=timeout_ms,
        )
        code_search_query = _payload_text(normalized_payload.get("code_search_query"))
        code_search = self._optional_page_action(
            profile_name=profile_name,
            target_id=resolved_target_id,
            kind="code-search",
            include=code_search_query is not None
            and _payload_bool(
                normalized_payload,
                "include_code_search",
                default=True,
            ),
            payload={
                "query": code_search_query,
                "limit": _payload_int(
                    normalized_payload, "code_search_limit", default=10
                ),
                "max_scripts": _payload_int(
                    normalized_payload,
                    "code_search_max_scripts",
                    default=20,
                ),
                "context_lines": _payload_int(
                    normalized_payload,
                    "code_search_context_lines",
                    default=1,
                ),
                "case_sensitive": _payload_bool(
                    normalized_payload,
                    "code_search_case_sensitive",
                    default=False,
                ),
                "regex": _payload_bool(
                    normalized_payload,
                    "code_search_regex",
                    default=False,
                ),
                "url_contains": _payload_text(
                    normalized_payload.get("code_search_url_contains"),
                ),
            },
            timeout_ms=timeout_ms,
        )
        request_script_query = _payload_text(
            normalized_payload.get("script_request_query"),
        )
        request_url = _payload_text(normalized_payload.get("script_request_url"))
        request_path = _payload_text(normalized_payload.get("script_request_path"))
        request_matches = self._optional_page_action(
            profile_name=profile_name,
            target_id=resolved_target_id,
            kind="script-find-request",
            include=(
                request_script_query is not None
                or request_url is not None
                or request_path is not None
            )
            and _payload_bool(
                normalized_payload,
                "include_script_request_matches",
                default=True,
            ),
            payload={
                "query": request_script_query,
                "request_url": request_url,
                "path": request_path,
                "limit": _payload_int(
                    normalized_payload,
                    "script_request_limit",
                    default=10,
                ),
                "max_scripts": _payload_int(
                    normalized_payload,
                    "script_request_max_scripts",
                    default=40,
                ),
                "context_lines": _payload_int(
                    normalized_payload,
                    "script_request_context_lines",
                    default=1,
                ),
                "case_sensitive": _payload_bool(
                    normalized_payload,
                    "script_request_case_sensitive",
                    default=False,
                ),
            },
            timeout_ms=timeout_ms,
        )

        observation = _build_observation_payload(
            profile_name=profile_name,
            target_id=resolved_target_id,
            tabs=tabs,
            snapshot=snapshot.payload,
            console=console,
            page_errors=page_errors,
            runtime=runtime,
            network_runtime=network_runtime,
            network_requests=network_requests,
            scripts=scripts,
            code_search=code_search,
            request_matches=request_matches,
        )
        return BrowserToolExecutionResult(
            payload=observation,
            runtime_metadata={
                **dict(snapshot.runtime_metadata),
                "browser_observation_target_id": resolved_target_id,
            },
        )

    def _tabs(
        self,
        *,
        profile_name: str,
        include: bool,
        timeout_ms: int | None,
    ) -> dict[str, Any] | None:
        if not include:
            return None
        result = self.tool_application_service.execute_control(
            profile_name=profile_name,
            kind="list-tabs",
            timeout_ms=timeout_ms,
        )
        return result.payload

    def _snapshot(
        self,
        *,
        profile_name: str,
        target_id: str | None,
        payload: Mapping[str, Any],
        timeout_ms: int | None,
    ) -> BrowserToolExecutionResult:
        snapshot_payload = {
            "format": _payload_text(payload.get("format")) or "interactive",
            "mode": _payload_text(payload.get("mode")) or "efficient",
            "compact": _payload_bool(payload, "compact", default=True),
        }
        limit = _payload_int(payload, "limit", default=None)
        if limit is not None:
            snapshot_payload["limit"] = limit
        depth = _payload_int(payload, "depth", default=None)
        if depth is not None:
            snapshot_payload["depth"] = depth
        for key in (
            "active_overlay",
            "overlay_source_ref",
            "overlay_source_selector",
            "frame_selector",
        ):
            value = payload.get(key)
            if value is not None:
                snapshot_payload[key] = value
        selector = _payload_text(payload.get("selector"))
        return self.tool_application_service.execute_page_action(
            profile_name=profile_name,
            kind="snapshot",
            target_id=target_id,
            selector=selector,
            payload=snapshot_payload,
            timeout_ms=timeout_ms,
        )

    def _optional_page_action(
        self,
        *,
        profile_name: str,
        target_id: str | None,
        kind: str,
        include: bool,
        payload: Mapping[str, Any],
        timeout_ms: int | None,
    ) -> dict[str, Any] | None:
        if not include:
            return None
        try:
            result = self.tool_application_service.execute_page_action(
                profile_name=profile_name,
                kind=kind,
                target_id=target_id,
                payload=payload,
                timeout_ms=timeout_ms,
            )
        except BrowserToolApplicationError as exc:
            return {
                "ok": False,
                "error": exc.to_payload(),
            }
        return result.payload
