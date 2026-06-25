"""Request-render snapshot record DTO assembly."""

from __future__ import annotations

from crxzipple.modules.llm.domain import ToolSchema
from crxzipple.modules.orchestration.application.ports import (
    RequestRenderSnapshotRecord,
)

from .request_render_input_selection import RequestRenderInputSelection
from .request_render_slice_projection import RequestRenderSliceProjection


def build_request_render_snapshot_record(
    *,
    snapshot_id: str,
    estimate_payload: dict[str, object],
    slice_projection: RequestRenderSliceProjection,
    input_selection: RequestRenderInputSelection,
    metadata: dict[str, object],
    visible_tool_schemas: tuple[ToolSchema, ...],
    visible_tool_schema_refs: tuple[dict[str, object], ...],
    artifact_content_blocks: tuple[dict[str, object], ...],
) -> RequestRenderSnapshotRecord:
    return RequestRenderSnapshotRecord(
        snapshot_id=snapshot_id,
        estimate=estimate_payload,
        included_node_ids=slice_projection.included_node_ids,
        mirrored_node_ids=(),
        included_refs=slice_projection.included_refs,
        collapsed_refs=slice_projection.collapsed_refs,
        protocol_required_refs=input_selection.protocol_required_refs,
        input_item_refs=slice_projection.included_refs,
        projected_input_items=slice_projection.projected_input_items,
        metadata=metadata,
        tool_schemas=visible_tool_schemas,
        tool_schema_refs=visible_tool_schema_refs,
        tool_schema_mirror_available=bool(visible_tool_schemas),
        artifact_content_blocks=artifact_content_blocks,
        parent_snapshot_id=None,
        parent_tree_revision=None,
    )
