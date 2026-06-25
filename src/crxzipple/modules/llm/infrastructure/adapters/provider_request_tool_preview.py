from __future__ import annotations

from typing import Any

from crxzipple.modules.llm.infrastructure.adapters.tool_schemas import (
    normalize_openai_tool_name,
)


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


def _optional_preview_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
