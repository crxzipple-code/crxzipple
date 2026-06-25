from __future__ import annotations

from dataclasses import dataclass

from crxzipple.modules.llm.domain import ToolSchema
from crxzipple.modules.orchestration.application.runtime_llm_request_draft import (
    RuntimeLlmRequestDraft,
)

from .request_render_snapshot_cost import (
    context_slice_builder_timings,
    request_render_cost as build_request_render_cost,
    transcript_budget_summary,
)
from .request_render_tool_schema_metadata import request_render_tool_schema_metadata
from .request_render_visible_input import visible_input_summary as build_visible_input_summary


@dataclass(frozen=True)
class RequestRenderSnapshotMetadataInput:
    draft: RuntimeLlmRequestDraft
    flow_context: dict[str, object]
    workspace_dir: str | None
    tree_revision: int
    control_slice: object | None
    context_slice: object | None
    control_selected_node_ids: tuple[str, ...]
    context_slice_node_ids: tuple[str, ...]
    context_slice_omitted_node_ids: tuple[str, ...]
    context_slice_report_refs: dict[str, tuple[dict[str, object], ...]]
    context_slice_loss: dict[str, object]
    projected_input_items: tuple[dict[str, object], ...]
    included_refs: tuple[dict[str, object], ...]
    protocol_required_refs: tuple[dict[str, object], ...]
    execution_required_refs: tuple[dict[str, object], ...]
    collapsed_refs: tuple[dict[str, object], ...]
    visible_tool_schemas: tuple[ToolSchema, ...]
    available_tool_schemas: tuple[ToolSchema, ...]
    render_metadata: dict[str, object]
    draft_input_budget: dict[str, object]


@dataclass(frozen=True)
class RequestRenderSnapshotMetadataBundle:
    metadata: dict[str, object]
    visible_input_summary: dict[str, object]
    render_report: dict[str, object]


class RequestRenderSnapshotMetadataBuilder:
    def build(
        self,
        data: RequestRenderSnapshotMetadataInput,
    ) -> RequestRenderSnapshotMetadataBundle:
        visible_input_summary = build_visible_input_summary(
            included_refs=data.included_refs,
            protocol_required_refs=data.protocol_required_refs,
            collapsed_refs=data.collapsed_refs,
            visible_tool_schemas=data.visible_tool_schemas,
            control_slice=data.control_slice,
            context_slice=data.context_slice,
            control_selected_node_ids=data.control_selected_node_ids,
        )
        request_render_cost = build_request_render_cost(data)
        context_slice_builder_timings_value = context_slice_builder_timings(
            data.context_slice,
        )
        metadata: dict[str, object] = {
            "snapshot_kind": "request_render",
            "tree_schema_version": "request-render-snapshot",
            "history_delivery": "provider_native_request",
            "request_context_source": (
                "context_slice"
                if data.context_slice is not None
                else "missing_context_slice"
            ),
            "active_session_id": data.draft.active_session_id,
            "mode": data.draft.mode.value,
            "flow_context": dict(data.flow_context),
            "workspace_dir": data.workspace_dir,
            "tree_revision": data.tree_revision,
            "control_slice_id": (
                data.control_slice.slice_id if data.control_slice is not None else None
            ),
            "control_slice_selected_ref_count": (
                len(data.control_slice.selected_refs)
                if data.control_slice is not None
                else 0
            ),
            "control_slice_selected_node_count": len(
                data.control_selected_node_ids,
            ),
            "control_slice_active_tool_count": (
                len(data.control_slice.active_tools)
                if data.control_slice is not None
                else 0
            ),
            "context_slice_id": (
                data.context_slice.slice_id if data.context_slice is not None else None
            ),
            "context_slice_item_count": (
                len(data.context_slice.items) if data.context_slice is not None else 0
            ),
            "context_slice_included_node_count": len(data.context_slice_node_ids),
            "context_slice_omitted_node_count": len(
                data.context_slice_omitted_node_ids,
            ),
            "context_slice_active_tool_count": (
                len(data.context_slice.active_tools)
                if data.context_slice is not None
                else 0
            ),
            "context_slice_projected_input_item_count": len(
                data.projected_input_items,
            ),
            "context_slice_archived_ref_count": len(
                data.context_slice_report_refs["archived_refs"],
            ),
            "context_slice_redacted_ref_count": len(
                data.context_slice_report_refs["redacted_refs"],
            ),
            "context_slice_unresolved_ref_count": len(
                data.context_slice_report_refs["unresolved_refs"],
            ),
            "context_slice_loss": data.context_slice_loss,
            "context_slice_builder_timings": context_slice_builder_timings_value,
            "draft_input_message_count": len(data.draft.messages),
            "draft_input_roles": [
                message.role.value for message in data.draft.messages
            ],
            "draft_input_session_item_count": len(data.included_refs),
            "draft_input_session_item_frontier": dict(
                data.draft_input_budget.get("frontier")
                if isinstance(data.draft_input_budget.get("frontier"), dict)
                else {},
            ),
            "draft_input_budget_summary": transcript_budget_summary(
                data.draft_input_budget,
            ),
            "protocol_required_ref_count": len(data.protocol_required_refs),
            "execution_chain_protocol_required_ref_count": len(
                data.execution_required_refs,
            ),
            "collapsed_ref_count": len(data.collapsed_refs),
            **request_render_tool_schema_metadata(
                render_metadata=data.render_metadata,
                visible_tool_schemas=data.visible_tool_schemas,
                available_tool_schemas=data.available_tool_schemas,
            ),
            "visible_input_summary": visible_input_summary,
            "runtime_request_report": (
                data.draft.report.to_payload()
                if data.draft.report is not None
                else None
            ),
            "runtime_request_snapshot": {
                "llm_id": data.draft.llm_id,
                "llm_api_family": data.draft.llm_api_family,
                "llm_capabilities": [
                    capability.value for capability in data.draft.llm_capabilities
                ],
                "input_item_count": len(data.draft.input_items),
                "message_count": len(data.draft.messages),
                "tool_schema_count": len(data.visible_tool_schemas),
                "available_tool_schema_count": len(data.available_tool_schemas),
                "tree_revision": data.tree_revision,
            },
            "request_render_cost": dict(request_render_cost),
            "request_render_snapshot": {
                "kind": "request_render",
                "debug_body_included": False,
                "full_tree_rendered": False,
                "owner_children_refreshed": False,
                "visible_input_summary": visible_input_summary,
                "cost": dict(request_render_cost),
            },
        }
        render_report = {
            "kind": "request_render",
            "debug_body_included": False,
            "full_tree_rendered": False,
            "owner_children_refreshed": False,
            "tool_schema_count": len(data.visible_tool_schemas),
            "available_tool_schema_count": len(data.available_tool_schemas),
            "control_slice_id": (
                data.control_slice.slice_id if data.control_slice is not None else None
            ),
            "control_slice_selected_ref_count": (
                len(data.control_slice.selected_refs)
                if data.control_slice is not None
                else 0
            ),
            "control_slice_selected_node_count": len(
                data.control_selected_node_ids,
            ),
            "context_slice_id": (
                data.context_slice.slice_id if data.context_slice is not None else None
            ),
            "context_slice_item_count": (
                len(data.context_slice.items) if data.context_slice is not None else 0
            ),
            "context_slice_omitted_node_count": len(
                data.context_slice_omitted_node_ids,
            ),
            "context_slice_archived_ref_count": len(
                data.context_slice_report_refs["archived_refs"],
            ),
            "context_slice_redacted_ref_count": len(
                data.context_slice_report_refs["redacted_refs"],
            ),
            "context_slice_unresolved_ref_count": len(
                data.context_slice_report_refs["unresolved_refs"],
            ),
            "context_slice_loss": data.context_slice_loss,
            "context_slice_builder_timings": context_slice_builder_timings_value,
            "included_node_count": len(data.context_slice_node_ids),
            "input_item_ref_count": len(data.included_refs),
            "protocol_required_ref_count": len(data.protocol_required_refs),
            "visible_input_summary": visible_input_summary,
            "cost": dict(request_render_cost),
        }
        return RequestRenderSnapshotMetadataBundle(
            metadata=metadata,
            visible_input_summary=visible_input_summary,
            render_report=render_report,
        )
