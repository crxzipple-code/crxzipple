from __future__ import annotations

from collections.abc import Mapping


OMITTED_METADATA_KEYS = {
    "artifact_content_blocks",
    "content",
    "context_slice",
    "files",
    "input",
    "messages",
    "prompt_body",
    "provider_attachment_mirror",
    "provider_attachments",
    "raw_tree_body",
    "rendered_prompt",
    "text",
    "tool_schemas",
}


def estimate_summary(estimate: Mapping[str, object]) -> dict[str, object]:
    summary: dict[str, object] = {}
    for key in (
        "estimated_tokens",
        "text_tokens",
        "tool_schema_tokens",
        "file_tokens",
        "text_chars",
        "image_count",
        "file_count",
        "provider_attachment_count",
        "truncated",
        "status",
    ):
        value = estimate.get(key)
        if value not in (None, "", {}, []):
            summary[key] = value
    breakdown = estimate.get("breakdown")
    if isinstance(breakdown, Mapping):
        by_kind = breakdown.get("by_kind")
        if isinstance(by_kind, Mapping):
            summary["kind_count"] = len(by_kind)
        by_owner = breakdown.get("by_owner")
        if isinstance(by_owner, Mapping):
            summary["owner_count"] = len(by_owner)
    top_nodes = estimate.get("top_nodes_by_tokens")
    if isinstance(top_nodes, list | tuple):
        summary["top_node_count"] = len(top_nodes)
    return summary


def request_render_snapshot_preview_payload(
    request_render_snapshot: Mapping[str, object],
) -> dict[str, object]:
    allowed_keys = {
        "snapshot_id",
        "included_node_count",
        "mirrored_node_count",
        "included_ref_count",
        "collapsed_ref_count",
        "protocol_required_ref_count",
        "estimate",
        "diagnostics",
        "tree_schema_version",
        "kind",
    }
    payload: dict[str, object] = {}
    for key, value in request_render_snapshot.items():
        if key not in allowed_keys or value in (None, "", {}, []):
            continue
        payload[key] = value
    return {
        key: value
        for key, value in payload.items()
        if value not in (None, "", {}, [])
    }


def request_metadata_preview_payload(
    request_metadata: Mapping[str, object],
) -> dict[str, object]:
    payload: dict[str, object] = {}
    for key, value in request_metadata.items():
        if not isinstance(key, str) or value in (None, "", {}, []):
            continue
        if _is_omitted_metadata_key(key):
            continue
        if key == "request_render_snapshot" and isinstance(value, Mapping):
            request_render_snapshot = request_render_snapshot_preview_payload(value)
            if request_render_snapshot:
                payload["request_render_snapshot"] = request_render_snapshot
            continue
        if key == "tool_surface" and isinstance(value, Mapping):
            tool_surface = _tool_surface_preview_payload(value)
            if tool_surface:
                payload[key] = tool_surface
            continue
        preview_value = _metadata_preview_value(value)
        if preview_value not in (None, "", {}, []):
            payload[key] = preview_value
    return payload


def request_render_snapshot_diagnostics(
    metadata: Mapping[str, object],
) -> dict[str, object]:
    diagnostics: dict[str, object] = {}
    for key in (
        "tool_schema_mirror_budget_status",
        "tool_schema_mirror_skipped_count",
        "tool_schema_mirror_duplicate_count",
        "tool_schema_mirror_skipped_by_reason",
        "duplicate_tool_delivery_risk",
        "session_budget_status",
        "visible_input_summary",
        "request_render_timings",
        "context_slice_omitted_node_count",
        "context_slice_archived_ref_count",
        "context_slice_redacted_ref_count",
        "context_slice_unresolved_ref_count",
        "context_slice_loss",
    ):
        value = metadata.get(key)
        if value not in (None, "", {}, []):
            diagnostics[key] = value
    return diagnostics


def _metadata_preview_value(value: object, *, depth: int = 0) -> object:
    if isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Mapping):
        if depth >= 3:
            return {"field_count": len(value)}
        payload: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                continue
            if _is_omitted_metadata_key(key):
                continue
            preview_item = _metadata_preview_value(item, depth=depth + 1)
            if preview_item not in (None, "", {}, []):
                payload[key] = preview_item
        return payload
    if isinstance(value, list | tuple):
        if depth >= 3:
            return {"item_count": len(value)}
        preview_items: list[object] = []
        for item in value[:80]:
            preview_item = _metadata_preview_value(item, depth=depth + 1)
            if preview_item not in (None, "", {}, []):
                preview_items.append(preview_item)
        if len(value) > len(preview_items):
            return {
                "item_count": len(value),
                "items": preview_items,
            }
        return preview_items
    return None


def _is_omitted_metadata_key(key: str) -> bool:
    return key in OMITTED_METADATA_KEYS or key.startswith("debug_")


def _tool_surface_preview_payload(tool_surface: Mapping[str, object]) -> dict[str, object]:
    payload: dict[str, object] = {}
    surface_id = tool_surface.get("id")
    if isinstance(surface_id, str) and surface_id.strip():
        payload["id"] = surface_id.strip()
    functions = tool_surface.get("functions")
    if isinstance(functions, list | tuple):
        names: list[str] = []
        for function in functions:
            if not isinstance(function, Mapping):
                continue
            name = function.get("name")
            if isinstance(name, str) and name.strip():
                names.append(name.strip())
        payload["function_count"] = len(functions)
        if names:
            payload["function_names"] = names
    mirrored_schema_names = tool_surface.get("mirrored_schema_names")
    if isinstance(mirrored_schema_names, list | tuple):
        names = [
            name.strip()
            for name in mirrored_schema_names
            if isinstance(name, str) and name.strip()
        ]
        payload["mirrored_schema_count"] = len(mirrored_schema_names)
        if names:
            payload["mirrored_schema_names"] = names
    return {
        key: value
        for key, value in payload.items()
        if value not in (None, "", {}, [])
    }


__all__ = [
    "estimate_summary",
    "request_metadata_preview_payload",
    "request_render_snapshot_diagnostics",
    "request_render_snapshot_preview_payload",
]
