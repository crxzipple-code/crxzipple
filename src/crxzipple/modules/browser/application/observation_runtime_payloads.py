from __future__ import annotations

from typing import Any, Mapping

from .observation_values import (
    _list_of_mappings,
    _mapping_payload,
    _payload_text,
    _safe_int,
)


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
    runtime_performance = (
        runtime.get("performance") if isinstance(runtime, Mapping) else None
    )
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
            "request_count": _safe_int(requests.get("request_count"))
            if isinstance(requests, Mapping)
            else None,
            "total_count": _safe_int(requests.get("total_count"))
            if isinstance(requests, Mapping)
            else None,
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
        "navigation_count": len(navigation)
        if isinstance(navigation, list | tuple)
        else 0,
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
