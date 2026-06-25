"""Request-render snapshot metadata bundle assembly."""

from __future__ import annotations

from crxzipple.modules.llm.domain import ToolSchema
from crxzipple.modules.orchestration.application.flow_context import FlowContextPayload
from crxzipple.modules.orchestration.application.runtime_llm_request_draft import (
    RuntimeLlmRequestDraft,
)

from .request_render_input_selection import RequestRenderInputSelection
from .request_render_slice_projection import RequestRenderSliceProjection
from .request_render_snapshot_metadata import (
    RequestRenderSnapshotMetadataBuilder,
    RequestRenderSnapshotMetadataBundle,
    RequestRenderSnapshotMetadataInput,
)


def build_request_render_metadata_bundle(
    *,
    builder: RequestRenderSnapshotMetadataBuilder,
    draft: RuntimeLlmRequestDraft,
    flow_context: FlowContextPayload,
    tree_revision: int,
    control_slice: object | None,
    context_slice: object | None,
    slice_projection: RequestRenderSliceProjection,
    input_selection: RequestRenderInputSelection,
    visible_tool_schemas: tuple[ToolSchema, ...],
    render_metadata: dict[str, object],
) -> RequestRenderSnapshotMetadataBundle:
    return builder.build(
        RequestRenderSnapshotMetadataInput(
            draft=draft,
            flow_context=flow_context.to_payload(),
            workspace_dir=draft.workspace_dir,
            tree_revision=tree_revision,
            control_slice=control_slice,
            context_slice=context_slice,
            control_selected_node_ids=slice_projection.control_selected_node_ids,
            context_slice_node_ids=slice_projection.context_slice_node_ids,
            context_slice_omitted_node_ids=(
                slice_projection.context_slice_omitted_node_ids
            ),
            context_slice_report_refs=slice_projection.context_slice_report_refs,
            context_slice_loss=slice_projection.context_slice_loss,
            projected_input_items=slice_projection.projected_input_items,
            included_refs=slice_projection.included_refs,
            protocol_required_refs=input_selection.protocol_required_refs,
            execution_required_refs=input_selection.execution_required_refs,
            collapsed_refs=slice_projection.collapsed_refs,
            visible_tool_schemas=visible_tool_schemas,
            available_tool_schemas=draft.tool_schemas,
            render_metadata=render_metadata,
            draft_input_budget=input_selection.draft_input_budget,
        ),
    )
