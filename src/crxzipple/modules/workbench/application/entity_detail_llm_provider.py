from __future__ import annotations

from crxzipple.modules.workbench.application.entity_detail_values import (
    copy_first_int,
    copy_first_text,
    int_value,
)


def llm_provider_render_report(
    provider_request_preview: dict[str, object],
) -> dict[str, object]:
    render_report = provider_request_preview.get("render_report")
    return dict(render_report) if isinstance(render_report, dict) else {}


def llm_provider_wire_preview(
    provider_request_preview: dict[str, object],
) -> dict[str, object]:
    if not provider_request_preview:
        return {}
    return {
        key: value
        for key, value in provider_request_preview.items()
        if key in _LLM_PROVIDER_WIRE_SAFE_KEYS and value not in (None, {}, [], ())
    }


def llm_provider_input_summary_payload(
    request_metadata: dict[str, object],
    provider_request_preview: dict[str, object] | None,
) -> dict[str, object]:
    preview = provider_request_preview or {}
    request_render_snapshot = request_metadata.get("request_render_snapshot")
    tool_surface = request_metadata.get("tool_surface")
    context_payload = request_render_snapshot if isinstance(request_render_snapshot, dict) else {}
    tool_payload = tool_surface if isinstance(tool_surface, dict) else {}
    payload: dict[str, object] = {}
    copy_first_text(
        payload,
        "request_render_snapshot_id",
        preview,
        request_metadata,
        context_payload,
        source_keys=("request_render_snapshot_id", "snapshot_id"),
    )
    copy_first_text(
        payload,
        "request_render_snapshot_schema_version",
        preview,
        context_payload,
        source_keys=("request_render_snapshot_schema_version", "tree_schema_version"),
    )
    copy_first_int(
        payload,
        "request_render_snapshot_included_node_count",
        preview,
        context_payload,
        source_keys=(
            "request_render_snapshot_included_node_count",
            "included_node_count",
        ),
    )
    if "request_render_snapshot_included_node_count" not in payload:
        included_node_ids = context_payload.get("included_node_ids")
        if isinstance(included_node_ids, list | tuple):
            payload["request_render_snapshot_included_node_count"] = len(
                included_node_ids,
            )
    copy_first_text(payload, "request_render_snapshot_fingerprint", preview)
    copy_first_text(
        payload,
        "tool_surface_id",
        preview,
        request_metadata,
        tool_payload,
        source_keys=("tool_surface_id", "id"),
    )
    copy_first_text(payload, "tool_surface_snapshot_id", preview, request_metadata)
    copy_first_int(payload, "tool_surface_function_count", preview, request_metadata)
    if "tool_surface_function_count" not in payload:
        functions = tool_payload.get("functions")
        if isinstance(functions, list | tuple):
            payload["tool_surface_function_count"] = len(functions)
    copy_first_int(
        payload,
        "tool_surface_mirrored_schema_count",
        preview,
        request_metadata,
    )
    if "tool_surface_mirrored_schema_count" not in payload:
        mirrored_schema_names = tool_payload.get("mirrored_schema_names")
        if isinstance(mirrored_schema_names, list | tuple):
            payload["tool_surface_mirrored_schema_count"] = len(mirrored_schema_names)
    copy_first_text(payload, "tool_surface_fingerprint", preview)
    return payload


def llm_runtime_observations_payload(
    provider_request_preview: dict[str, object],
) -> dict[str, object]:
    render_report = provider_request_preview.get("render_report")
    render_report_payload = render_report if isinstance(render_report, dict) else {}
    tool_protocol = render_report_payload.get("tool_protocol")
    tool_protocol_payload = tool_protocol if isinstance(tool_protocol, dict) else {}
    observation_count = int(bool(tool_protocol_payload))
    summary_parts: list[str] = []
    tool_protocol_summary = _tool_protocol_health_summary(tool_protocol_payload)
    if tool_protocol_summary is not None:
        summary_parts.append(f"tool protocol: {tool_protocol_summary}")
    return {
        "observation_count": observation_count,
        "summary": (
            "; ".join(summary_parts)
            if summary_parts
            else "No runtime observations."
        ),
        "tool_protocol": _tool_protocol_health_payload(tool_protocol_payload),
    }


def _tool_protocol_health_payload(payload: dict[str, object]) -> dict[str, object]:
    if not payload:
        return {
            "present": False,
            "replay_has_protocol_breaks": False,
            "source_had_protocol_breaks": False,
            "filtered_count": 0,
        }
    return {
        "present": True,
        "replay_has_protocol_breaks": payload.get("replay_has_protocol_breaks") is True,
        "source_had_protocol_breaks": payload.get("source_had_protocol_breaks") is True,
        "filtered_count": _tool_protocol_filtered_count(payload),
        "dropped_orphan_tool_output_count": int_value(
            payload.get("dropped_orphan_tool_output_count"),
        ),
        "dropped_missing_tool_output_count": int_value(
            payload.get("dropped_missing_tool_output_count"),
        ),
        "dropped_duplicate_tool_call_id_count": int_value(
            payload.get("dropped_duplicate_tool_call_id_count"),
        ),
        "dropped_duplicate_tool_output_id_count": int_value(
            payload.get("dropped_duplicate_tool_output_id_count"),
        ),
    }


def _tool_protocol_health_summary(payload: dict[str, object]) -> str | None:
    if not payload:
        return None
    replay_status = (
        "breaks"
        if payload.get("replay_has_protocol_breaks") is True
        else "clean"
    )
    filtered_count = _tool_protocol_filtered_count(payload)
    if filtered_count:
        return f"{replay_status}, filtered={filtered_count}"
    return replay_status


def _tool_protocol_filtered_count(payload: dict[str, object]) -> int:
    return sum(
        int_value(payload.get(key))
        for key in (
            "dropped_orphan_tool_output_count",
            "dropped_missing_tool_output_count",
            "dropped_duplicate_tool_call_id_count",
            "dropped_duplicate_tool_output_id_count",
        )
    )


_LLM_PROVIDER_WIRE_SAFE_KEYS = {
    "preview_source",
    "provider",
    "api_family",
    "model",
    "endpoint",
    "transport",
    "renderer_id",
    "render_strategy",
    "message_type",
    "payload_keys",
    "message_count",
    "content_count",
    "input_item_count",
    "input_item_types",
    "input_delta_mode",
    "input_baseline_count",
    "input_item_fingerprints",
    "input_baseline_fingerprints",
    "input_delta_count",
    "instructions_fingerprint",
    "tool_count",
    "tool_fingerprints",
    "tool_types",
    "has_previous_response_id",
    "previous_response_id",
    "has_system",
    "option_summary",
    "provider_input_summary",
    "runtime_context",
    "runtime_request_summary",
    "context_slice_summary",
}
