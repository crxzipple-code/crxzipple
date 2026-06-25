from __future__ import annotations

import hashlib
import json
from typing import Any

from crxzipple.modules.llm.application.runtime_request_preview import (
    request_render_snapshot_preview_payload,
)


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
        preview["request_render_snapshot_fingerprint"] = _stable_preview_fingerprint(
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
        preview["tool_surface_fingerprint"] = _stable_preview_fingerprint(tool_surface)
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


def _stable_preview_fingerprint(payload: object) -> str:
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
