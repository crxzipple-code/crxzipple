from __future__ import annotations

import json
from typing import Any

from crxzipple.modules.llm.application.runtime_request_preview import (
    request_metadata_preview_payload,
    request_render_snapshot_preview_payload,
)
from crxzipple.modules.llm.domain import LlmInvocation
from crxzipple.modules.operations.application.read_models.llm_invocation_facts import (
    request_metadata,
)
from crxzipple.modules.operations.application.read_models.llm_invocation_labels import (
    provider_render_report,
    provider_request_preview,
)


def request_payload(invocation: LlmInvocation) -> dict[str, Any]:
    return _sanitize_payload(
        {
            "llm_id": invocation.llm_id,
            "messages": [
                message.to_payload() if hasattr(message, "to_payload") else message
                for message in invocation.messages
            ],
            "tool_schemas": [
                schema.to_payload() if hasattr(schema, "to_payload") else schema
                for schema in invocation.tool_schemas
            ],
            "response_format": invocation.response_format,
            "overrides": invocation.request_overrides,
            "request_metadata": request_metadata_preview_payload(
                invocation.request_metadata,
            ),
            "provider_request_payload_preview": dict(
                invocation.provider_request_payload_preview,
            ),
        },
    )


def runtime_request_summary(invocation: LlmInvocation) -> dict[str, Any]:
    metadata = request_metadata(invocation)
    summary: dict[str, Any] = {
        "message_count": len(invocation.messages),
        "input_item_count": len(invocation.input_items),
        "input_item_kinds": [item.kind.value for item in invocation.input_items],
        "tool_schema_count": len(invocation.tool_schemas),
        "response_format_configured": invocation.response_format is not None,
    }
    for key in (
        "request_render_snapshot_id",
        "request_render_snapshot_kind",
        "input_mode",
        "runtime_contract_version",
        "runtime_contract_hash",
        "draft_input_session_item_count",
        "tool_surface_id",
        "tool_surface_snapshot_id",
        "tool_surface_function_count",
        "tool_surface_mirrored_schema_count",
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
        "visible_input_summary",
        "request_render_timings",
    ):
        value = metadata.get(key)
        if value not in (None, "", {}, []):
            summary[key] = value
    request_render_snapshot = metadata.get("request_render_snapshot")
    if isinstance(request_render_snapshot, dict):
        surface = request_render_snapshot_preview_payload(request_render_snapshot)
        if surface:
            summary["request_render_snapshot"] = surface
            diagnostics = surface.get("diagnostics")
            if (
                "request_render_timings" not in summary
                and isinstance(diagnostics, dict)
            ):
                timings = diagnostics.get("request_render_timings")
                if timings not in (None, "", {}, []):
                    summary["request_render_timings"] = timings
    tool_surface = metadata.get("tool_surface")
    if isinstance(tool_surface, dict):
        surface = _tool_surface_summary(tool_surface)
        if surface:
            summary["tool_surface"] = surface
    render_report = provider_render_report(invocation)
    coverage = render_report.get("input_item_mapping_coverage")
    if isinstance(coverage, dict) and coverage:
        summary["provider_input_item_mapping_coverage"] = dict(coverage)
    return {
        key: value
        for key, value in summary.items()
        if value not in (None, "", {}, [])
    }


def provider_wire_preview(invocation: LlmInvocation) -> dict[str, Any]:
    preview = provider_request_preview(invocation)
    if not preview:
        return {}
    return {
        key: value
        for key, value in preview.items()
        if key != "render_report"
    }


def _tool_surface_summary(surface: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    surface_id = _text(surface.get("id"))
    if surface_id:
        summary["id"] = surface_id
    functions = surface.get("functions")
    if isinstance(functions, list | tuple):
        summary["function_count"] = len(functions)
    mirrored_schema_names = surface.get("mirrored_schema_names")
    if isinstance(mirrored_schema_names, list | tuple):
        summary["mirrored_schema_count"] = len(mirrored_schema_names)
    blocked_access_count = surface.get("blocked_access_count")
    if isinstance(blocked_access_count, int):
        summary["blocked_access_count"] = blocked_access_count
    return summary


def _sanitize_payload(value: Any, *, depth: int = 0) -> Any:
    if depth >= 4:
        return _truncate(value, 240)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _truncate(value, 512)
    if isinstance(value, dict):
        return {
            str(key): _sanitize_payload(item, depth=depth + 1)
            for key, item in list(value.items())[:40]
            if isinstance(key, str)
        }
    if isinstance(value, (list, tuple)):
        return [_sanitize_payload(item, depth=depth + 1) for item in list(value)[:40]]
    return _truncate(value, 240)


def _json_or_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return str(value)


def _truncate(value: Any, limit: int = 160) -> str:
    text = str(value)
    if len(text) <= limit:
        return text
    return text[: max(limit - 1, 0)] + "…"

def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
