from __future__ import annotations

import hashlib
import json
from typing import Any

from crxzipple.modules.llm.application.runtime_request import (
    request_render_snapshot_preview_payload,
)
from crxzipple.modules.llm.domain.entities import LlmProfile
from crxzipple.modules.llm.domain.value_objects import (
    LlmInputItem,
    LlmInputItemKind,
)
from crxzipple.modules.llm.infrastructure.adapters.tool_schemas import (
    normalize_openai_tool_name,
)
from crxzipple.modules.llm.infrastructure.rendering.input_projection import (
    provider_safe_input_metadata,
)


def openai_provider_request_preview(
    *,
    profile: LlmProfile,
    endpoint: str,
    payload: dict[str, Any],
    renderer_id: str = "openai_responses",
    transport: str = "http",
    render_strategy: str = "full_wire_payload",
    message_type: str | None = None,
    input_delta_mode: bool | None = None,
    input_baseline_count: int | None = None,
    input_baseline_fingerprints: tuple[str, ...] | None = None,
    request_metadata: dict[str, Any] | None = None,
    runtime_context: dict[str, Any] | None = None,
    runtime_route: dict[str, Any] | None = None,
    runtime_policy: dict[str, Any] | None = None,
    canonical_input_items: tuple[LlmInputItem, ...] = (),
) -> dict[str, object]:
    input_items = payload.get("input") if isinstance(payload.get("input"), list) else []
    tools = payload.get("tools") if isinstance(payload.get("tools"), list) else []
    has_previous_response_id = bool(payload.get("previous_response_id"))
    delta_mode = has_previous_response_id if input_delta_mode is None else input_delta_mode
    input_fingerprints = openai_response_input_fingerprints(input_items)
    effective_render_strategy = (
        "provider_native_delta" if delta_mode else render_strategy
    )
    tool_render_report = provider_tool_render_report(
        payload=payload,
        request_metadata=request_metadata,
    )
    tool_protocol_report = provider_tool_protocol_render_report(
        request_metadata=request_metadata,
    )
    render_report = {
        "renderer_id": renderer_id,
        "transport": transport,
        "render_strategy": effective_render_strategy,
        "loss_report": {},
        "tool_surface": tool_render_report,
        "tool_protocol": tool_protocol_report,
    }
    input_item_mapping = provider_input_item_mapping(canonical_input_items)
    if input_item_mapping:
        render_report["input_item_mapping"] = input_item_mapping
        render_report["input_item_mapping_coverage"] = provider_input_item_mapping_coverage(
            input_item_mapping,
            provider_input_item_count=len(input_items),
        )
    return {
        "preview_source": "provider_adapter",
        "provider": profile.provider.value,
        "api_family": profile.api_family.value,
        "model": payload.get("model") or profile.model_name,
        "endpoint": endpoint,
        "transport": transport,
        "renderer_id": renderer_id,
        "render_strategy": effective_render_strategy,
        "render_report": render_report,
        "message_type": message_type or payload.get("type"),
        "payload_keys": sorted(str(key) for key in payload),
        "input_item_count": len(input_items),
        "input_item_types": tuple(
            _payload_item_type(item) for item in input_items[:40]
        ),
        "input_delta_mode": bool(delta_mode),
        "input_baseline_count": input_baseline_count,
        "input_item_fingerprints": input_fingerprints,
        "input_baseline_fingerprints": (
            input_baseline_fingerprints
            if input_baseline_fingerprints is not None
            else input_fingerprints
        ),
        "input_delta_count": len(input_items) if delta_mode else 0,
        "instructions_fingerprint": _payload_fingerprint_or_none(
            payload.get("instructions"),
        ),
        "tool_count": len(tools),
        "tool_fingerprints": tuple(
            openai_provider_payload_fingerprint(tool) for tool in tools
        ),
        "tool_types": tuple(_payload_item_type(item) for item in tools[:80]),
        "has_previous_response_id": has_previous_response_id,
        "previous_response_id": (
            str(payload.get("previous_response_id"))
            if payload.get("previous_response_id") is not None
            else None
        ),
        "option_summary": {
            "tool_choice": payload.get("tool_choice"),
            "parallel_tool_calls": payload.get("parallel_tool_calls"),
            "service_tier": payload.get("service_tier"),
            "prompt_cache_key": payload.get("prompt_cache_key"),
            "stream": payload.get("stream"),
            "store": payload.get("store"),
            "reasoning": _safe_preview_value(payload.get("reasoning")),
            "text": _safe_preview_value(payload.get("text")),
            "include": _safe_preview_value(payload.get("include")),
        },
        **provider_runtime_preview(
            runtime_route=runtime_route,
            runtime_policy=runtime_policy,
        ),
        "payload_preview": _safe_preview_value(payload),
        **provider_input_preview(
            runtime_context=runtime_context,
            request_metadata=request_metadata,
        ),
    }


def provider_wire_request_preview(
    *,
    profile: LlmProfile,
    endpoint: str,
    payload: dict[str, Any],
    renderer_id: str,
    transport: str = "http",
    render_strategy: str = "full_wire_payload",
    loss_report: dict[str, Any] | None = None,
    request_metadata: dict[str, Any] | None = None,
    runtime_context: dict[str, Any] | None = None,
    runtime_route: dict[str, Any] | None = None,
    runtime_policy: dict[str, Any] | None = None,
    canonical_input_items: tuple[LlmInputItem, ...] = (),
) -> dict[str, object]:
    messages = payload.get("messages")
    contents = payload.get("contents")
    input_items = payload.get("input")
    tools = payload.get("tools")
    message_count = len(messages) if isinstance(messages, list) else None
    content_count = len(contents) if isinstance(contents, list) else None
    input_item_count = len(input_items) if isinstance(input_items, list) else None
    tool_count = len(tools) if isinstance(tools, list) else 0
    tool_render_report = provider_tool_render_report(
        payload=payload,
        request_metadata=request_metadata,
    )
    tool_protocol_report = provider_tool_protocol_render_report(
        request_metadata=request_metadata,
    )
    render_report = {
        "renderer_id": renderer_id,
        "transport": transport,
        "render_strategy": render_strategy,
        "loss_report": dict(loss_report or {}),
        "tool_surface": tool_render_report,
        "tool_protocol": tool_protocol_report,
    }
    input_item_mapping = provider_input_item_mapping(canonical_input_items)
    if input_item_mapping:
        render_report["input_item_mapping"] = input_item_mapping
        render_report["input_item_mapping_coverage"] = provider_input_item_mapping_coverage(
            input_item_mapping,
            provider_input_item_count=(
                input_item_count
                if input_item_count is not None
                else message_count
                if message_count is not None
                else content_count
                if content_count is not None
                else 0
            ),
        )
    return {
        "preview_source": "provider_adapter",
        "provider": profile.provider.value,
        "api_family": profile.api_family.value,
        "model": payload.get("model") or profile.model_name,
        "endpoint": endpoint,
        "transport": transport,
        "renderer_id": renderer_id,
        "render_strategy": render_strategy,
        "render_report": render_report,
        "payload_keys": sorted(str(key) for key in payload),
        "message_count": message_count,
        "content_count": content_count,
        "input_item_count": input_item_count,
        "tool_count": tool_count,
        "has_system": (
            payload.get("system") not in (None, "", [], {})
            or payload.get("system_instruction") not in (None, "", [], {})
        ),
        "option_summary": {
            "temperature": payload.get("temperature"),
            "top_p": payload.get("top_p"),
            "topP": payload.get("topP"),
            "max_tokens": payload.get("max_tokens"),
            "maxOutputTokens": (
                payload.get("generationConfig", {}).get("maxOutputTokens")
                if isinstance(payload.get("generationConfig"), dict)
                else None
            ),
            "response_format": _safe_preview_value(payload.get("response_format")),
            "generationConfig": _safe_preview_value(payload.get("generationConfig")),
            "toolConfig": _safe_preview_value(payload.get("toolConfig")),
        },
        **provider_runtime_preview(
            runtime_route=runtime_route,
            runtime_policy=runtime_policy,
        ),
        "payload_preview": _safe_preview_value(payload),
        **provider_input_preview(
            runtime_context=runtime_context,
            request_metadata=request_metadata,
        ),
    }


def provider_runtime_preview(
    *,
    runtime_route: dict[str, Any] | None,
    runtime_policy: dict[str, Any] | None,
) -> dict[str, object]:
    preview: dict[str, object] = {}
    if isinstance(runtime_route, dict) and runtime_route:
        preview["runtime_route"] = _safe_preview_value(runtime_route)
    if isinstance(runtime_policy, dict) and runtime_policy:
        preview["runtime_policy"] = _safe_preview_value(runtime_policy)
    return preview


def provider_input_item_mapping(
    input_items: tuple[LlmInputItem, ...],
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    provider_index = 0
    for index, item in enumerate(input_items[:120]):
        if (
            item.kind is LlmInputItemKind.MESSAGE
            and str(item.payload.get("role") or "").strip() == "system"
        ):
            continue
        metadata = provider_safe_input_metadata(item.metadata)
        row: dict[str, object] = {
            "provider_payload_index": provider_index,
            "input_item_index": index,
            "input_item_kind": item.kind.value,
            "input_item_source": item.source,
        }
        for key in (
            "node_id",
            "owner",
            "kind",
            "session_item_id",
            "tool_call_id",
            "tool_run_id",
            "llm_response_item_id",
        ):
            value = metadata.get(key)
            if value not in (None, "", {}, []):
                row[key] = str(value)
        rows.append(row)
        provider_index += 1
    return rows


def provider_input_item_mapping_coverage(
    rows: list[dict[str, object]],
    *,
    provider_input_item_count: int,
) -> dict[str, object]:
    traced_count = 0
    generated_or_unattributed: list[dict[str, object]] = []
    for row in rows:
        if row.get("session_item_id"):
            traced_count += 1
            row["trace_status"] = "runtime_input_item"
            continue
        source = str(row.get("input_item_source") or "").strip()
        if source:
            traced_count += 1
            row["trace_status"] = "input_item_source"
            row["trace_reason"] = source
            continue
        row["trace_status"] = "provider_renderer_generated_or_unattributed"
        generated_or_unattributed.append(
            {
                "provider_payload_index": row.get("provider_payload_index"),
                "input_item_index": row.get("input_item_index"),
                "input_item_kind": row.get("input_item_kind"),
            },
        )
    return {
        "provider_input_item_count": provider_input_item_count,
        "canonical_input_item_count": len(rows),
        "traced_input_item_count": traced_count,
        "untraced_input_item_count": len(rows) - traced_count,
        "provider_generated_or_unattributed": generated_or_unattributed,
    }


def provider_input_preview(
    *,
    runtime_context: dict[str, Any] | None,
    request_metadata: dict[str, Any] | None,
) -> dict[str, object]:
    preview = provider_input_preview_from_request_metadata(request_metadata)
    if not isinstance(runtime_context, dict):
        return preview
    for key, value in runtime_context.items():
        if value not in (None, "", {}, []):
            preview[key] = value
    if runtime_context:
        preview["runtime_context_source"] = "adapter_request"
    return preview


def provider_input_preview_from_request_metadata(
    request_metadata: dict[str, Any] | None,
) -> dict[str, object]:
    if not isinstance(request_metadata, dict):
        return {}
    request_render_snapshot = request_metadata.get("request_render_snapshot")
    tool_surface = request_metadata.get("tool_surface")
    preview: dict[str, object] = {}
    if isinstance(request_render_snapshot, dict):
        preview_request_render_snapshot = request_render_snapshot_preview_payload(
            request_render_snapshot,
        )
        request_render_snapshot_id = _optional_preview_text(
            request_render_snapshot.get("snapshot_id"),
        )
        if request_render_snapshot_id is not None:
            preview["request_render_snapshot_id"] = request_render_snapshot_id
        context_schema = _optional_preview_text(
            request_render_snapshot.get("tree_schema_version"),
        )
        if context_schema is not None:
            preview["request_render_snapshot_schema_version"] = context_schema
        included_node_ids = request_render_snapshot.get("included_node_ids")
        if isinstance(included_node_ids, list | tuple):
            preview["request_render_snapshot_included_node_count"] = len(
                included_node_ids,
            )
        preview["request_render_snapshot_fingerprint"] = _stable_payload_fingerprint(
            preview_request_render_snapshot,
        )
    if isinstance(tool_surface, dict):
        tool_surface_id = _optional_preview_text(tool_surface.get("id"))
        if tool_surface_id is not None:
            preview["tool_surface_id"] = tool_surface_id
        functions = tool_surface.get("functions")
        if isinstance(functions, list | tuple):
            preview["tool_surface_function_count"] = len(functions)
        mirrored_schema_names = tool_surface.get("mirrored_schema_names")
        if isinstance(mirrored_schema_names, list | tuple):
            preview["tool_surface_mirrored_schema_count"] = len(mirrored_schema_names)
        preview["tool_surface_fingerprint"] = _stable_payload_fingerprint(tool_surface)
    for key in (
        "request_context_source",
        "context_slice_id",
        "context_slice_item_count",
        "context_slice_included_node_count",
        "context_slice_omitted_node_count",
        "context_slice_active_tool_count",
        "context_slice_projected_input_item_count",
        "context_slice_archived_ref_count",
        "context_slice_redacted_ref_count",
        "context_slice_unresolved_ref_count",
        "context_slice_loss",
        "request_render_snapshot_id",
        "tool_surface_snapshot_id",
        "tool_surface_function_count",
        "tool_surface_mirrored_schema_count",
    ):
        value = request_metadata.get(key)
        if key not in preview and value not in (None, "", {}, []):
            preview[key] = value
    return preview


def provider_tool_render_report(
    *,
    payload: dict[str, Any],
    request_metadata: dict[str, Any] | None,
) -> dict[str, object]:
    provider_visible_tool_names = _provider_visible_tool_names(payload.get("tools"))
    provider_count = len(provider_visible_tool_names)
    source_count = _source_tool_count_from_request_metadata(request_metadata)
    if source_count is None:
        source_count = provider_count
    provider_tool_mapping = _provider_tool_surface_mapping(
        provider_visible_tool_names,
        request_metadata=request_metadata,
    )
    return {
        "source_tool_schema_count": source_count,
        "provider_visible_tool_count": provider_count,
        "provider_visible_tool_names": tuple(provider_visible_tool_names),
        "dropped_tool_schema_count": max(source_count - provider_count, 0),
        "provider_tool_mapping": provider_tool_mapping,
    }


def provider_tool_protocol_render_report(
    *,
    request_metadata: dict[str, Any] | None,
) -> dict[str, object]:
    if not isinstance(request_metadata, dict):
        return _empty_tool_protocol_render_report()
    payload = request_metadata.get("runtime_input_filter")
    if not isinstance(payload, dict):
        return _empty_tool_protocol_render_report()
    dropped_orphan_function_call_count = _int_preview_value(
        payload.get("dropped_orphan_function_call_count"),
    )
    return {
        "schema_version": "2026-06-19.runtime_input_filter.v1",
        "source_had_protocol_breaks": False,
        "replay_has_protocol_breaks": False,
        "replay_orphan_tool_output_count": _int_preview_value(
            payload.get("replay_orphan_tool_output_count"),
        ),
        "replay_missing_tool_output_count": _int_preview_value(
            payload.get("replay_missing_tool_output_count"),
        ),
        "replay_duplicate_tool_call_id_count": _int_preview_value(
            payload.get("replay_duplicate_tool_call_id_count"),
        ),
        "replay_duplicate_tool_output_id_count": _int_preview_value(
            payload.get("replay_duplicate_tool_output_id_count"),
        ),
        "dropped_orphan_tool_output_count": 0,
        "dropped_missing_tool_output_count": dropped_orphan_function_call_count,
        "dropped_duplicate_tool_call_id_count": 0,
        "dropped_duplicate_tool_output_id_count": _int_preview_value(
            payload.get("dropped_duplicate_tool_output_id_count"),
        ),
    }


def openai_response_input_fingerprints(
    payloads: list[dict[str, Any]],
) -> tuple[str, ...]:
    return tuple(openai_provider_payload_fingerprint(payload) for payload in payloads)


def openai_provider_payload_fingerprint(payload: Any) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _empty_tool_protocol_render_report() -> dict[str, object]:
    return {
        "schema_version": None,
        "source_had_protocol_breaks": False,
        "replay_has_protocol_breaks": False,
        "replay_orphan_tool_output_count": 0,
        "replay_missing_tool_output_count": 0,
        "replay_duplicate_tool_call_id_count": 0,
        "replay_duplicate_tool_output_id_count": 0,
        "dropped_orphan_tool_output_count": 0,
        "dropped_missing_tool_output_count": 0,
        "dropped_duplicate_tool_call_id_count": 0,
        "dropped_duplicate_tool_output_id_count": 0,
    }


def _int_preview_value(value: object) -> int:
    return value if isinstance(value, int) else 0


def _source_tool_count_from_request_metadata(
    request_metadata: dict[str, Any] | None,
) -> int | None:
    if not isinstance(request_metadata, dict):
        return None
    tool_surface = request_metadata.get("tool_surface")
    if isinstance(tool_surface, dict):
        functions = tool_surface.get("functions")
        if isinstance(functions, list | tuple):
            return len(functions)
        mirrored_schema_names = tool_surface.get("mirrored_schema_names")
        if isinstance(mirrored_schema_names, list | tuple):
            return len(mirrored_schema_names)
    value = request_metadata.get("tool_surface_function_count")
    if isinstance(value, int):
        return value
    return None


def _provider_tool_surface_mapping(
    provider_visible_tool_names: list[str],
    *,
    request_metadata: dict[str, Any] | None,
) -> list[dict[str, object]]:
    functions = _tool_surface_functions_from_request_metadata(request_metadata)
    if not provider_visible_tool_names or not functions:
        return []
    function_by_provider_name: dict[str, dict[str, object]] = {}
    for function in functions:
        for name in _provider_name_candidates_for_tool_surface_function(function):
            function_by_provider_name.setdefault(name, function)
    rows: list[dict[str, object]] = []
    for provider_name in provider_visible_tool_names:
        function = function_by_provider_name.get(provider_name)
        if function is None:
            rows.append(
                {
                    "provider_name": provider_name,
                    "trace_status": "provider_tool_unattributed",
                },
            )
            continue
        row: dict[str, object] = {
            "provider_name": provider_name,
            "runtime_tool_name": str(function.get("name") or ""),
            "tool_id": str(function.get("tool_id") or ""),
            "trace_status": "runtime_tool_surface",
        }
        for key in ("source_id", "group_key", "source", "node_id", "tool_ref_id"):
            value = _tool_surface_function_metadata_value(function, key)
            if value is not None:
                row[key] = value
        rows.append(
            {
                key: value
                for key, value in row.items()
                if value not in (None, "", {}, [])
            },
        )
    return rows


def _tool_surface_functions_from_request_metadata(
    request_metadata: dict[str, Any] | None,
) -> tuple[dict[str, object], ...]:
    if not isinstance(request_metadata, dict):
        return ()
    tool_surface = request_metadata.get("tool_surface")
    if not isinstance(tool_surface, dict):
        return ()
    functions = tool_surface.get("functions")
    if not isinstance(functions, (list, tuple)):
        return ()
    return tuple(dict(item) for item in functions if isinstance(item, dict))


def _provider_name_candidates_for_tool_surface_function(
    function: dict[str, object],
) -> tuple[str, ...]:
    raw_name = _optional_preview_text(function.get("name"))
    if raw_name is None:
        return ()
    names = [raw_name]
    normalized = normalize_openai_tool_name(raw_name)
    if normalized not in names:
        names.append(normalized)
    return tuple(names)


def _tool_surface_function_metadata_value(
    function: dict[str, object],
    key: str,
) -> str | None:
    value = _optional_preview_text(function.get(key))
    if value is not None:
        return value
    metadata = function.get("metadata")
    if isinstance(metadata, dict):
        return _optional_preview_text(metadata.get(key))
    return None


def _provider_visible_tool_names(tools: object) -> list[str]:
    if not isinstance(tools, list | tuple):
        return []
    names: list[str] = []
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        direct_name = tool.get("name")
        if direct_name not in (None, ""):
            names.append(str(direct_name))
            continue
        function_payload = tool.get("function")
        if isinstance(function_payload, dict) and function_payload.get("name") not in (
            None,
            "",
        ):
            names.append(str(function_payload["name"]))
            continue
        declarations = tool.get("functionDeclarations")
        if isinstance(declarations, list | tuple):
            for declaration in declarations:
                if isinstance(declaration, dict) and declaration.get("name") not in (
                    None,
                    "",
                ):
                    names.append(str(declaration["name"]))
    return names


def _stable_payload_fingerprint(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _optional_preview_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _payload_item_type(item: object) -> str:
    if isinstance(item, dict):
        item_type = item.get("type")
        if item_type is not None:
            return str(item_type)
        role = item.get("role")
        if role is not None:
            return str(role)
    return type(item).__name__


def _safe_preview_value(value: object, *, depth: int = 0) -> object:
    if depth >= 5:
        return _truncate_preview(value, 240)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _truncate_preview(value, 512)
    if isinstance(value, dict):
        return {
            str(key): _safe_preview_value(item, depth=depth + 1)
            for key, item in list(value.items())[:60]
        }
    if isinstance(value, (list, tuple)):
        return [_safe_preview_value(item, depth=depth + 1) for item in value[:80]]
    return _truncate_preview(value, 240)


def _truncate_preview(value: object, limit: int) -> str:
    text = str(value)
    if len(text) <= limit:
        return text
    return text[: max(limit - 3, 0)] + "..."


def _payload_fingerprint_or_none(payload: Any) -> str | None:
    if payload is None:
        return None
    return openai_provider_payload_fingerprint(payload)
