from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .evidence_paths import (
    browser_evidence_path_alternatives,
    browser_evidence_path_ladder_payload,
    browser_evidence_path_payload,
)
from .tool_application import (
    BrowserToolApplicationError,
    BrowserToolApplicationService,
    BrowserToolExecutionResult,
)

_FORM_FIELD_ROLES = frozenset(
    {
        "textbox",
        "searchbox",
        "combobox",
        "spinbutton",
        "checkbox",
        "radio",
        "switch",
        "listbox",
    }
)
_FORM_FIELD_TAGS = frozenset({"input", "textarea", "select"})
_FORM_ACTION_ROLES = frozenset({"button", "link", "menuitem", "tab"})
_FORM_ACTION_TAGS = frozenset({"button", "a"})
_OVERLAY_CANDIDATE_ROLES = frozenset(
    {
        "option",
        "menuitem",
        "listitem",
        "treeitem",
        "gridcell",
    }
)
_OVERLAY_CANDIDATE_EVIDENCE = frozenset({"picker-choice", "visual-fallback"})


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
        resolved_target_id = _payload_text(snapshot.payload.get("target_id")) or target_id
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
            include=_payload_bool(normalized_payload, "include_page_errors", default=False),
            payload={
                "limit": _payload_int(normalized_payload, "page_error_limit", default=20),
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
        include_runtime = _payload_bool(normalized_payload, "include_runtime", default=True)
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
                "wait_ms": _payload_int(normalized_payload, "script_wait_ms", default=50),
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
                "limit": _payload_int(normalized_payload, "code_search_limit", default=10),
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
            include=(request_script_query is not None or request_url is not None or request_path is not None)
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


def _build_observation_payload(
    *,
    profile_name: str,
    target_id: str | None,
    tabs: dict[str, Any] | None,
    snapshot: dict[str, Any],
    console: dict[str, Any] | None,
    page_errors: dict[str, Any] | None,
    runtime: dict[str, Any] | None,
    network_runtime: dict[str, Any] | None,
    network_requests: dict[str, Any] | None,
    scripts: dict[str, Any] | None,
    code_search: dict[str, Any] | None,
    request_matches: dict[str, Any] | None,
) -> dict[str, Any]:
    snapshot_result = _result_payload(snapshot)
    page = _page_payload(snapshot, tabs=tabs, target_id=target_id)
    refs = _snapshot_refs(snapshot_result)
    frames = _snapshot_frames(snapshot_result)
    runtime_result = _successful_result_payload(runtime)
    network_runtime_result = (
        _successful_result_payload(network_runtime)
    )
    network_requests_result = (
        _successful_result_payload(network_requests)
    )
    scripts_result = _successful_result_payload(scripts)
    code_search_result = _successful_result_payload(code_search)
    request_matches_result = (
        _successful_result_payload(request_matches)
    )
    runtime_payload = (
        _runtime_payload(
            runtime_result,
            network_runtime=network_runtime_result,
        )
        if runtime_result or network_runtime_result
        else None
    )
    network_payload = _network_payload(
        runtime=network_runtime_result,
        requests=network_requests_result,
    )
    code_payload = _code_payload(
        scripts=scripts_result,
        search=code_search_result,
        request_matches=request_matches_result,
    )
    errors = [
        item
        for item in (
            _optional_error(console),
            _optional_error(page_errors),
            _optional_error(runtime),
            _optional_error(network_runtime),
            _optional_error(network_requests),
            _optional_error(scripts),
            _optional_error(code_search),
            _optional_error(request_matches),
        )
        if item is not None
    ]
    form_payload = _form_payload(refs=refs)
    overlay_payload = _overlay_payload(snapshot_result=snapshot_result, refs=refs)
    return {
        "ok": True,
        "kind": "observe",
        "profile_name": profile_name,
        "target_id": target_id,
        "message": _observation_message(page=page, refs=refs),
        "page": page,
        "tabs": _tabs_payload(tabs),
        "frames": {
            "count": len(frames),
            "items": frames,
        },
        "interaction": {
            "ref_count": _safe_int(snapshot_result.get("ref_count")),
            "frame_count": _safe_int(snapshot_result.get("frame_count")),
            "refs": list(refs),
            "evidence": _evidence_summary(refs),
        },
        "snapshot": snapshot_result,
        "console": _successful_result_payload(console),
        "page_errors": _successful_result_payload(page_errors),
        "runtime": runtime_payload,
        "network": network_payload,
        "code": code_payload,
        "form": form_payload,
        "overlay": overlay_payload,
        "guidance": _observation_guidance(
            refs=refs,
            errors=errors,
            runtime=runtime_payload,
            network=network_payload,
            code=code_payload,
            form=form_payload,
            overlay=overlay_payload,
        ),
        "errors": errors,
    }


def _result_payload(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    value = payload.get("value")
    if isinstance(value, dict):
        result = value.get("result")
        if isinstance(result, dict):
            return result
    return payload


def _successful_result_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict) or payload.get("ok") is False:
        return None
    return _result_payload(payload)


def _tabs_payload(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    value = payload.get("value")
    if not isinstance(value, list):
        return None
    tabs = tuple(item for item in value if isinstance(item, dict))
    return {
        "count": len(tabs),
        "items": tabs[:12],
    }


def _page_payload(
    snapshot: dict[str, Any],
    *,
    tabs: dict[str, Any] | None,
    target_id: str | None,
) -> dict[str, Any]:
    value = snapshot.get("value")
    tab = value.get("tab") if isinstance(value, dict) else None
    if isinstance(tab, dict):
        return {
            "target_id": _payload_text(tab.get("target_id")) or target_id,
            "title": _payload_text(tab.get("title")),
            "url": _payload_text(tab.get("url")),
            "type": _payload_text(tab.get("type")),
        }
    tab_payload = _tab_by_target_id(tabs, target_id=target_id)
    if tab_payload is not None:
        return tab_payload
    return {"target_id": target_id, "title": None, "url": None, "type": None}


def _tab_by_target_id(
    tabs: dict[str, Any] | None,
    *,
    target_id: str | None,
) -> dict[str, Any] | None:
    tab_list = _tabs_payload(tabs)
    if tab_list is None:
        return None
    items = tab_list.get("items")
    if not isinstance(items, tuple | list):
        return None
    for item in items:
        if not isinstance(item, dict):
            continue
        if target_id is None or _payload_text(item.get("target_id")) == target_id:
            return {
                "target_id": _payload_text(item.get("target_id")) or target_id,
                "title": _payload_text(item.get("title")),
                "url": _payload_text(item.get("url")),
                "type": _payload_text(item.get("type")),
            }
    return None


def _snapshot_refs(snapshot_result: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    value = snapshot_result.get("value")
    if not isinstance(value, Mapping):
        return ()
    refs = value.get("refs")
    if not isinstance(refs, list | tuple):
        return ()
    normalized: list[dict[str, Any]] = []
    for item in refs[:40]:
        if isinstance(item, Mapping):
            normalized.append({str(key): value for key, value in item.items()})
    return tuple(normalized)


def _snapshot_frames(snapshot_result: Mapping[str, Any]) -> list[dict[str, Any]]:
    value = snapshot_result.get("value")
    if not isinstance(value, Mapping):
        return []
    frames = value.get("frames")
    if not isinstance(frames, list | tuple):
        return []
    normalized: list[dict[str, Any]] = []
    for frame in frames[:20]:
        if not isinstance(frame, Mapping):
            continue
        refs = frame.get("refs")
        normalized.append(
            {
                "frame_path": frame.get("frame_path"),
                "snapshot_chars": len(str(frame.get("snapshot") or "")),
                "ref_count": len(refs) if isinstance(refs, list | tuple) else None,
            }
        )
    return normalized


def _evidence_summary(refs: tuple[dict[str, Any], ...]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in refs:
        evidence = item.get("evidence")
        if not isinstance(evidence, tuple | list):
            continue
        for entry in evidence:
            normalized = _payload_text(entry)
            if normalized is None:
                continue
            counts[normalized] = counts.get(normalized, 0) + 1
    return counts


def _runtime_payload(
    result: Mapping[str, Any] | None,
    *,
    network_runtime: Mapping[str, Any] | None,
) -> dict[str, Any]:
    runtime_result = result if isinstance(result, Mapping) else {}
    network_result = network_runtime if isinstance(network_runtime, Mapping) else {}
    cdp = network_result.get("cdp")
    cdp_payload = cdp if isinstance(cdp, Mapping) else {}
    resource_tree = cdp_payload.get("resource_tree")
    performance_metrics = cdp_payload.get("metrics")
    errors = network_result.get("errors")
    return {
        "kind": _payload_text(runtime_result.get("kind"))
        or _payload_text(network_result.get("kind"))
        or "runtime",
        "url": _payload_text(runtime_result.get("url"))
        or _payload_text(network_result.get("url")),
        "page_state": _mapping_payload(runtime_result.get("page_state")),
        "frameworks": _framework_summary(runtime_result.get("frameworks")),
        "route_hints": _list_of_mappings(runtime_result.get("route_hints"), limit=12),
        "globals": _runtime_globals_summary(runtime_result.get("globals")),
        "resources": _resource_tree_summary(resource_tree),
        "performance": _performance_summary(performance_metrics),
        "errors": list(errors) if isinstance(errors, list | tuple) else [],
    }


def _mapping_payload(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): item for key, item in value.items()}


def _list_of_mappings(value: Any, *, limit: int) -> list[dict[str, Any]]:
    if not isinstance(value, list | tuple):
        return []
    return [
        {str(key): item for key, item in raw_item.items()}
        for raw_item in value[:limit]
        if isinstance(raw_item, Mapping)
    ]


def _framework_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {"detected": [], "items": []}
    detected = value.get("detected")
    return {
        "detected": [
            item
            for item in (_payload_text(entry) for entry in (detected or ()))
            if item is not None
        ]
        if isinstance(detected, list | tuple)
        else [],
        "items": _list_of_mappings(value.get("items"), limit=12),
    }


def _runtime_globals_summary(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list | tuple):
        return []
    normalized: list[dict[str, Any]] = []
    for raw_item in value[:20]:
        if not isinstance(raw_item, Mapping):
            continue
        item = {
            "name": _payload_text(raw_item.get("name")),
            "exists": raw_item.get("exists") is True,
        }
        if raw_item.get("exists") is True:
            item.update(
                {
                    "type": _payload_text(raw_item.get("type")),
                    "constructor_name": _payload_text(raw_item.get("constructor_name")),
                    "keys": [
                        key
                        for key in (
                            _payload_text(entry)
                            for entry in (
                                raw_item.get("keys")
                                if isinstance(raw_item.get("keys"), list | tuple)
                                else []
                            )
                        )
                        if key is not None
                    ][:12],
                }
            )
        normalized.append(item)
    return normalized


def _network_payload(
    *,
    runtime: Mapping[str, Any] | None,
    requests: Mapping[str, Any] | None,
) -> dict[str, Any]:
    runtime_performance = runtime.get("performance") if isinstance(runtime, Mapping) else None
    request_items = requests.get("requests") if isinstance(requests, Mapping) else None
    normalized_requests = [
        _network_request_summary(item)
        for item in (request_items if isinstance(request_items, list | tuple) else [])
        if isinstance(item, Mapping)
    ][:20]
    return {
        "performance": _network_performance_summary(runtime_performance),
        "capture": {
            "enabled": requests is not None,
            "request_count": _safe_int(requests.get("request_count")) if isinstance(requests, Mapping) else None,
            "total_count": _safe_int(requests.get("total_count")) if isinstance(requests, Mapping) else None,
            "requests": normalized_requests,
        },
    }


def _code_payload(
    *,
    scripts: Mapping[str, Any] | None,
    search: Mapping[str, Any] | None,
    request_matches: Mapping[str, Any] | None,
) -> dict[str, Any]:
    return {
        "scripts": _script_list_payload(scripts) if scripts is not None else None,
        "search": _code_search_payload(search) if search is not None else None,
        "request_matches": (
            _script_request_matches_payload(request_matches)
            if request_matches is not None
            else None
        ),
    }


def _script_list_payload(result: Mapping[str, Any]) -> dict[str, Any]:
    scripts = result.get("scripts")
    return {
        "kind": _payload_text(result.get("kind")) or "script-list",
        "scripts_count": _safe_int(result.get("scripts_count")),
        "matched_scripts": _safe_int(result.get("matched_scripts")),
        "returned_scripts": _safe_int(result.get("returned_scripts")),
        "scripts": [
            _script_summary(item)
            for item in (scripts if isinstance(scripts, list | tuple) else [])
            if isinstance(item, Mapping)
        ][:20],
        "errors": _list_of_mappings(result.get("errors"), limit=20),
    }


def _script_summary(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "script_id": _payload_text(item.get("script_id")),
        "url": _payload_text(item.get("url")),
        "line_count": _safe_int(item.get("line_count")),
        "execution_context_id": _safe_int(item.get("execution_context_id")),
        "is_module": item.get("is_module") is True,
        "source_map_url": _payload_text(item.get("source_map_url")),
    }


def _code_search_payload(result: Mapping[str, Any]) -> dict[str, Any]:
    matches = result.get("matches")
    return {
        "kind": _payload_text(result.get("kind")) or "code-search",
        "query": _payload_text(result.get("query")),
        "regex": result.get("regex") is True,
        "case_sensitive": result.get("case_sensitive") is True,
        "scripts_count": _safe_int(result.get("scripts_count")),
        "searched_scripts": _safe_int(result.get("searched_scripts")),
        "matched_scripts": _safe_int(result.get("matched_scripts")),
        "match_count": _safe_int(result.get("match_count")),
        "matches": [
            _script_match_group(item)
            for item in (matches if isinstance(matches, list | tuple) else [])
            if isinstance(item, Mapping)
        ][:12],
        "errors": _list_of_mappings(result.get("errors"), limit=20),
    }


def _script_request_matches_payload(result: Mapping[str, Any]) -> dict[str, Any]:
    candidates = result.get("candidates")
    return {
        "kind": _payload_text(result.get("kind")) or "script-find-request",
        "request": _mapping_payload(result.get("request")),
        "case_sensitive": result.get("case_sensitive") is True,
        "scripts_count": _safe_int(result.get("scripts_count")),
        "searched_scripts": _safe_int(result.get("searched_scripts")),
        "candidate_count": _safe_int(result.get("candidate_count")),
        "match_count": _safe_int(result.get("match_count")),
        "candidates": [
            _script_match_group(item)
            for item in (candidates if isinstance(candidates, list | tuple) else [])
            if isinstance(item, Mapping)
        ][:12],
        "errors": _list_of_mappings(result.get("errors"), limit=20),
    }


def _script_match_group(item: Mapping[str, Any]) -> dict[str, Any]:
    raw_matches = item.get("matches")
    script = item.get("script")
    script_payload = script if isinstance(script, Mapping) else item
    return {
        "script_id": _payload_text(item.get("script_id")),
        "url": _payload_text(item.get("url")),
        "script": _script_summary(script_payload),
        "source_available": item.get("source_available") is True,
        "source_chars": _safe_int(item.get("source_chars")),
        "score": _safe_int(item.get("score")),
        "matched_terms": [
            term
            for term in (
                _payload_text(entry)
                for entry in (
                    item.get("matched_terms")
                    if isinstance(item.get("matched_terms"), list | tuple)
                    else []
                )
            )
            if term is not None
        ][:12],
        "matches": [
            _script_match_summary(match)
            for match in (raw_matches if isinstance(raw_matches, list | tuple) else [])
            if isinstance(match, Mapping)
        ][:12],
    }


def _script_match_summary(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "field": _payload_text(item.get("field")),
        "term": _payload_text(item.get("term")),
        "line_number": _safe_int(item.get("line_number")),
        "column": _safe_int(item.get("column")),
        "snippet": _payload_text(item.get("snippet")),
    }


def _resource_tree_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {"frame_count": 0, "resource_count": 0, "types": {}}
    frame_tree = value.get("frameTree")
    frames: list[Mapping[str, Any]] = []
    resources: list[Mapping[str, Any]] = []
    _collect_resource_tree(frame_tree, frames=frames, resources=resources)
    types: dict[str, int] = {}
    for resource in resources:
        resource_type = _payload_text(resource.get("type")) or "unknown"
        types[resource_type] = types.get(resource_type, 0) + 1
    return {
        "frame_count": len(frames),
        "resource_count": len(resources),
        "types": types,
    }


def _collect_resource_tree(
    node: Any,
    *,
    frames: list[Mapping[str, Any]],
    resources: list[Mapping[str, Any]],
) -> None:
    if not isinstance(node, Mapping):
        return
    frame = node.get("frame")
    if isinstance(frame, Mapping):
        frames.append(frame)
    raw_resources = node.get("resources")
    if isinstance(raw_resources, list | tuple):
        resources.extend(item for item in raw_resources if isinstance(item, Mapping))
    children = node.get("childFrames")
    if isinstance(children, list | tuple):
        for child in children:
            _collect_resource_tree(child, frames=frames, resources=resources)


def _performance_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {"metric_count": 0, "names": []}
    metrics = value.get("metrics")
    if not isinstance(metrics, list | tuple):
        return {"metric_count": 0, "names": []}
    names = [
        str(item.get("name"))
        for item in metrics
        if isinstance(item, Mapping) and item.get("name") is not None
    ][:20]
    return {"metric_count": len(metrics), "names": names}


def _network_performance_summary(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {"navigation_count": 0, "resource_count": 0}
    navigation = value.get("navigation")
    resources = value.get("resources")
    return {
        "navigation_count": len(navigation) if isinstance(navigation, list | tuple) else 0,
        "resource_count": len(resources) if isinstance(resources, list | tuple) else 0,
    }


def _network_request_summary(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "request_id": _payload_text(item.get("request_id")),
        "method": _payload_text(item.get("method")),
        "url": _payload_text(item.get("url")),
        "resource_type": _payload_text(item.get("resource_type")),
        "status": _safe_int(item.get("status")),
    }


def _optional_error(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(payload, dict) or payload.get("ok") is not False:
        return None
    error = payload.get("error")
    if isinstance(error, dict):
        return error
    return {"message": "Browser observation section failed."}


def _form_payload(*, refs: tuple[dict[str, Any], ...]) -> dict[str, Any]:
    fields: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    for item in refs:
        ref = _interaction_ref_summary(item)
        if _is_form_field_ref(item):
            fields.append(ref)
            continue
        if _is_overlay_candidate_ref(item):
            candidates.append(ref)
            continue
        if _is_form_action_ref(item):
            actions.append(ref)
    return {
        "field_count": len(fields),
        "action_count": len(actions),
        "candidate_count": len(candidates),
        "fields": fields[:24],
        "actions": actions[:16],
        "candidates": candidates[:24],
        "guidance": _form_guidance(fields=fields, actions=actions, candidates=candidates),
    }


def _overlay_payload(
    *,
    snapshot_result: Mapping[str, Any],
    refs: tuple[dict[str, Any], ...],
) -> dict[str, Any]:
    root_selector = _payload_text(snapshot_result.get("root_selector"))
    active_overlay = snapshot_result.get("active_overlay") is True
    candidates = [
        _interaction_ref_summary(item)
        for item in refs
        if _is_overlay_candidate_ref(item)
        or (
            root_selector is not None
            and _payload_text(item.get("scope_selector")) == root_selector
        )
    ]
    return {
        "active": bool(active_overlay or root_selector),
        "selector": root_selector,
        "candidate_count": len(candidates),
        "candidates": candidates[:32],
        "guidance": _overlay_guidance(
            active=bool(active_overlay or root_selector),
            candidates=candidates,
        ),
    }


def _interaction_ref_summary(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "ref": _payload_text(item.get("ref")),
        "label": _payload_text(item.get("label")) or _payload_text(item.get("text")),
        "role": _payload_text(item.get("role")),
        "tag": _payload_text(item.get("tag")),
        "selector": _payload_text(item.get("selector")),
        "scope_selector": _payload_text(item.get("scope_selector")),
        "text": _payload_text(item.get("text")),
        "evidence": _text_list(item.get("evidence"), limit=8),
        "confidence": item.get("confidence"),
    }


def _is_form_field_ref(item: Mapping[str, Any]) -> bool:
    role = (_payload_text(item.get("role")) or "").lower()
    tag = (_payload_text(item.get("tag")) or "").lower()
    evidence = set(_text_list(item.get("evidence"), limit=20))
    return bool(role in _FORM_FIELD_ROLES or tag in _FORM_FIELD_TAGS or "editable" in evidence)


def _is_form_action_ref(item: Mapping[str, Any]) -> bool:
    role = (_payload_text(item.get("role")) or "").lower()
    tag = (_payload_text(item.get("tag")) or "").lower()
    return bool(role in _FORM_ACTION_ROLES or tag in _FORM_ACTION_TAGS)


def _is_overlay_candidate_ref(item: Mapping[str, Any]) -> bool:
    role = (_payload_text(item.get("role")) or "").lower()
    evidence = set(_text_list(item.get("evidence"), limit=20))
    return bool(role in _OVERLAY_CANDIDATE_ROLES or evidence & _OVERLAY_CANDIDATE_EVIDENCE)


def _form_guidance(
    *,
    fields: list[dict[str, Any]],
    actions: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    if candidates:
        return {
            "next_action": "select-overlay-candidate",
            "reason": "Overlay candidates are visible; select one with browser.action.trace.",
            "suggested_tools": ["browser.action.trace", "browser.overlay.observe"],
        }
    if fields:
        return {
            "next_action": "trace-form-field-action",
            "reason": "Form fields are visible; trace fill/type/click to verify page state.",
            "suggested_tools": ["browser.action.trace", "browser.dom.inspect"],
        }
    if actions:
        return {
            "next_action": "trace-form-submit-action",
            "reason": "Action controls are visible but no fields were detected.",
            "suggested_tools": ["browser.action.trace", "browser.dom.clickability"],
        }
    return {
        "next_action": "observe-page-or-runtime",
        "reason": "No form fields, actions, or overlay candidates were detected.",
        "suggested_tools": ["browser.observe", "browser.runtime.inspect"],
    }


def _overlay_guidance(*, active: bool, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    if candidates:
        return {
            "next_action": "select-overlay-candidate",
            "reason": "The overlay exposes selectable candidates.",
            "suggested_tools": ["browser.action.trace", "browser.click"],
        }
    if active:
        return {
            "next_action": "inspect-overlay-dom",
            "reason": "An overlay root is active but no selectable candidates were detected.",
            "suggested_tools": ["browser.snapshot", "browser.dom.inspect"],
        }
    return {
        "next_action": "open-overlay",
        "reason": "No active overlay was detected.",
        "suggested_tools": ["browser.action.trace", "browser.click", "browser.type"],
    }


def _observation_guidance(
    *,
    refs: tuple[dict[str, Any], ...],
    errors: list[dict[str, Any]],
    runtime: Mapping[str, Any] | None,
    network: Mapping[str, Any],
    code: Mapping[str, Any],
    form: Mapping[str, Any],
    overlay: Mapping[str, Any],
) -> dict[str, Any]:
    primary = _primary_observation_guidance(
        refs=refs,
        errors=errors,
        runtime=runtime,
        network=network,
        code=code,
        form=form,
        overlay=overlay,
    )
    primary_key = _payload_text(primary.get("evidence_path_key"))
    primary_path = browser_evidence_path_payload(primary_key)
    guidance = dict(primary)
    guidance["primary"] = dict(primary)
    guidance["primary_evidence_path"] = primary_path
    guidance["alternative_evidence_paths"] = browser_evidence_path_alternatives(primary_key)
    guidance["evidence_paths"] = browser_evidence_path_ladder_payload()
    return guidance


def _primary_observation_guidance(
    *,
    refs: tuple[dict[str, Any], ...],
    errors: list[dict[str, Any]],
    runtime: Mapping[str, Any] | None,
    network: Mapping[str, Any],
    code: Mapping[str, Any],
    form: Mapping[str, Any],
    overlay: Mapping[str, Any],
) -> dict[str, Any]:
    if errors:
        return {
            "next_action": "inspect-observation-errors",
            "reason": "One or more observation sections failed.",
            "suggested_tools": ["browser.diagnostics.collect", "browser.runtime.inspect"],
            "evidence_path_key": "diagnose_blockers",
        }
    if (_safe_int(overlay.get("candidate_count")) or 0) > 0:
        return {
            "next_action": "select-overlay-candidate",
            "reason": "A visible overlay contains selectable candidates.",
            "suggested_tools": ["browser.action.trace", "browser.overlay.observe"],
            "evidence_path_key": "stateful_interaction",
        }
    capture = network.get("capture") if isinstance(network, Mapping) else None
    if isinstance(capture, Mapping):
        request_count = _safe_int(capture.get("request_count")) or 0
        if request_count > 0:
            return {
                "next_action": "inspect-network-capture",
                "reason": "Network capture already contains request activity.",
                "suggested_tools": [
                    "browser.network.list_requests",
                    "browser.network.get_response_body",
                    "browser.script.find_request",
                    "browser.script.extract_request",
                    "browser.runtime.probe_client",
                    "browser.runtime.call_client",
                ],
                "evidence_path_key": "network_truth",
            }
    request_matches = code.get("request_matches") if isinstance(code, Mapping) else None
    if isinstance(request_matches, Mapping) and (_safe_int(request_matches.get("match_count")) or 0) > 0:
        return {
            "next_action": "inspect-request-script",
            "reason": "Script request candidates are available.",
            "suggested_tools": [
                "browser.script.extract_request",
                "browser.runtime.probe_client",
                "browser.runtime.call_client",
                "browser.script.inspect",
                "browser.network.replay_request",
            ],
            "evidence_path_key": "runtime_and_code",
        }
    search = code.get("search") if isinstance(code, Mapping) else None
    if isinstance(search, Mapping) and (_safe_int(search.get("match_count")) or 0) > 0:
        return {
            "next_action": "inspect-code-search-result",
            "reason": "Code search matched page scripts.",
            "suggested_tools": [
                "browser.script.extract_request",
                "browser.runtime.probe_client",
                "browser.runtime.call_client",
                "browser.script.inspect",
                "browser.code.search",
            ],
            "evidence_path_key": "runtime_and_code",
        }
    if _has_runtime_or_script_signal(runtime=runtime, code=code):
        return {
            "next_action": "inspect-runtime-or-scripts",
            "reason": (
                "Runtime or script facts are available; inspect them before "
                "choosing state-changing page actions."
            ),
            "suggested_tools": [
                "browser.runtime.inspect",
                "browser.script.find_request",
                "browser.code.search",
                "browser.script.extract_request",
                "browser.runtime.probe_client",
                "browser.runtime.call_client",
                "browser.network.inspect",
            ],
            "evidence_path_key": "runtime_and_code",
        }
    if (_safe_int(form.get("field_count")) or 0) > 0:
        return {
            "next_action": "trace-form-field-action",
            "reason": "Visible form fields are available.",
            "suggested_tools": ["browser.action.trace", "browser.form.inspect"],
            "evidence_path_key": "stateful_interaction",
        }
    if refs:
        return {
            "next_action": "trace-meaningful-action",
            "reason": "Interactive refs are available; use action trace to verify page effect.",
            "suggested_tools": ["browser.action.trace", "browser.dom.inspect"],
            "evidence_path_key": "stateful_interaction",
        }
    return {
        "next_action": "capture-current-state",
        "reason": "No strong interactive, network, runtime, or script signal was found.",
        "suggested_tools": ["browser.snapshot", "browser.screenshot"],
        "evidence_path_key": "orient",
    }


def _has_runtime_or_script_signal(
    *,
    runtime: Mapping[str, Any] | None,
    code: Mapping[str, Any],
) -> bool:
    scripts = code.get("scripts") if isinstance(code, Mapping) else None
    script_count = (
        _safe_int(scripts.get("returned_scripts"))
        if isinstance(scripts, Mapping)
        else 0
    )
    if (script_count or 0) > 0:
        return True
    if not isinstance(runtime, Mapping):
        return False
    frameworks = runtime.get("frameworks")
    if isinstance(frameworks, Mapping) and _text_list(
        frameworks.get("detected"),
        limit=10,
    ):
        return True
    if isinstance(runtime.get("route_hints"), list | tuple) and runtime.get(
        "route_hints",
    ):
        return True
    if isinstance(runtime.get("globals"), list | tuple) and runtime.get("globals"):
        return True
    return False


def _text_list(value: Any, *, limit: int) -> list[str]:
    if not isinstance(value, list | tuple):
        return []
    return [
        item
        for item in (_payload_text(entry) for entry in value[:limit])
        if item is not None
    ]


def _observation_message(*, page: Mapping[str, Any], refs: tuple[dict[str, Any], ...]) -> str:
    title = _payload_text(page.get("title"))
    url = _payload_text(page.get("url"))
    label = title or url or "current page"
    return f"Observed {label} with {len(refs)} interactive ref(s)."


def _payload_text(value: Any) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _payload_text_list(value: Any) -> list[str]:
    if not isinstance(value, list | tuple):
        return []
    return [
        item
        for item in (_payload_text(entry) for entry in value)
        if item is not None
    ]


def _payload_bool(payload: Mapping[str, Any], key: str, *, default: bool) -> bool:
    value = payload.get(key)
    if value is None:
        return default
    return bool(value)


def _payload_int(
    payload: Mapping[str, Any],
    key: str,
    *,
    default: int | None,
) -> int | None:
    value = payload.get(key)
    if value is None:
        return default
    if isinstance(value, bool):
        return default
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return default
    return normalized if normalized >= 0 else default


def _safe_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
