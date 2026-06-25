"""Snapshot metadata helpers for Context Workspace orchestration integration."""

from __future__ import annotations

from crxzipple.modules.context_workspace.application import (
    CONTEXT_INSTRUCTIONS_NODE_ID,
    CONTEXT_TREE_SCHEMA_VERSION,
    EXECUTION_CURRENT_NODE_ID,
    SESSION_CURRENT_NODE_ID,
)
from crxzipple.modules.orchestration.application.runtime_llm_request_draft import RuntimeLlmRequestDraft
from crxzipple.modules.orchestration.domain import OrchestrationRun
from crxzipple.shared.request_render_budget import request_render_budget_metadata

from ._metadata import (
    estimate_text_tokens,
    metadata_dict,
    metadata_int,
    metadata_text,
)
from .snapshot_artifact_metadata import build_snapshot_artifact_metadata
from .snapshot_draft_input_metadata import build_snapshot_draft_input_metadata
from .snapshot_metadata_values import (
    top_rendered_nodes as _top_rendered_nodes,
)
from .snapshot_node_refs import (
    current_inbound_node_id as _current_inbound_node_id,
    current_inbound_session_item_id as _current_inbound_session_item_id,
    evidence_node_refs as _evidence_node_refs,
    session_item_node_refs as _session_item_node_refs,
    tool_interaction_node_refs as _tool_interaction_node_refs,
)
from .snapshot_provider_attachments import (
    build_snapshot_provider_attachments,
    mirrored_schema_estimated_tokens,
    mirrored_tool_schemas,
)
from .snapshot_tool_schema_metadata import build_snapshot_tool_schema_metadata

__all__ = [
    "build_context_snapshot_metadata",
    "build_snapshot_provider_attachments",
    "mirrored_schema_estimated_tokens",
    "mirrored_tool_schemas",
]


def build_context_snapshot_metadata(
    *,
    run: OrchestrationRun,
    draft: RuntimeLlmRequestDraft,
    debug_body: str,
    provider_attachments: dict[str, object],
    provider_attachment_report: dict[str, object],
    included_node_ids: tuple[str, ...],
    flow_context: dict[str, object],
    artifact_content_blocks: tuple[dict[str, object], ...],
    estimate_breakdown: dict[str, object],
    runtime_contract: dict[str, object],
    tree_schema_version: str,
    root_node_ids: tuple[str, ...],
    mirrored_node_ids: tuple[str, ...],
    tool_schema_count: int,
) -> dict[str, object]:
    session_budget = metadata_dict(estimate_breakdown.get("session"))
    plan_budget = metadata_dict(estimate_breakdown.get("plan"))
    top_rendered_nodes = _top_rendered_nodes(estimate_breakdown)
    debug_body_estimate = metadata_dict(
        estimate_breakdown.get("debug_body"),
    ) or {
        "text_chars": len(debug_body or ""),
        "text_tokens": estimate_text_tokens(debug_body or ""),
    }
    node_estimate = metadata_dict(estimate_breakdown.get("node_visible"))
    contract_version = metadata_text(runtime_contract.get("contract_version"))
    contract_hash = metadata_text(runtime_contract.get("content_hash"))
    debug_body_chars = len(debug_body or "")
    debug_body_tokens = estimate_text_tokens(debug_body or "")
    draft_input_metadata = build_snapshot_draft_input_metadata(draft)
    draft_input_tokens = metadata_int(
        draft_input_metadata,
        "draft_input_estimated_tokens",
    )
    tree_tool_interaction_count = sum(
        1
        for node_id in included_node_ids
        if node_id.startswith("session.tool_interaction.")
    )
    tree_evidence_item_count = sum(
        1
        for node_id in included_node_ids
        if node_id.startswith("session.evidence.")
        and node_id != "session.evidence.current"
    )
    tool_schema_metadata = build_snapshot_tool_schema_metadata(
        provider_attachments=provider_attachments,
        provider_attachment_report=provider_attachment_report,
        tool_schema_count=tool_schema_count,
    )
    mirrored_schema_tokens = metadata_int(
        tool_schema_metadata,
        "mirrored_tool_schema_estimated_tokens",
    )
    artifact_metadata = build_snapshot_artifact_metadata(
        provider_attachments=provider_attachments,
        artifact_content_blocks=artifact_content_blocks,
    )
    artifact_content_tokens = metadata_int(
        artifact_metadata,
        "artifact_content_estimated_tokens",
    )
    duplicate_delivery_risk = (
        tree_tool_interaction_count > 0
        and any(message.role.value == "tool" for message in draft.messages)
    )
    payload: dict[str, object] = {
        "parallel_recording": True,
        "tree_schema_version": tree_schema_version or CONTEXT_TREE_SCHEMA_VERSION,
        "root_node_ids": list(root_node_ids),
        "context_instructions_node_id": CONTEXT_INSTRUCTIONS_NODE_ID,
        "execution_current_node_id": EXECUTION_CURRENT_NODE_ID,
        "session_current_node_id": SESSION_CURRENT_NODE_ID,
        "history_delivery": "context_tree",
        "runtime_contract": dict(runtime_contract),
        "runtime_contract_version": contract_version,
        "runtime_contract_hash": contract_hash,
        **tool_schema_metadata,
        "mirrored_node_count": len(mirrored_node_ids),
        "debug_body_estimate": dict(debug_body_estimate),
        "node_visible_estimate": dict(node_estimate),
        "node_estimate_breakdown": dict(estimate_breakdown),
        "top_rendered_nodes": top_rendered_nodes,
        "active_session_id": draft.active_session_id,
        "mode": draft.mode.value,
        "llm_id": draft.llm_id,
        "llm_capabilities": [
            capability.value for capability in draft.llm_capabilities
        ],
        "runtime_context_fact_count": len(draft.runtime_context),
        "has_agent_instruction": bool(draft.agent_instruction),
        "flow_context": flow_context,
        "workspace_dir": draft.workspace_dir,
        "runtime_request_report": (
            draft.report.to_payload()
            if draft.report is not None
            else None
        ),
        **draft_input_metadata,
        "debug_body_chars": debug_body_chars,
        "debug_body_estimated_tokens": debug_body_tokens,
        "estimated_provider_input_tokens": (
            debug_body_tokens
            + (draft_input_tokens or 0)
            + (mirrored_schema_tokens or 0)
            + (artifact_content_tokens or 0)
        ),
        **artifact_metadata,
        "duplicate_tool_delivery_risk": duplicate_delivery_risk,
        "tree_session_item_count": sum(
            1 for node_id in included_node_ids if node_id.startswith("session.item.")
        ),
        "session_item_node_refs": _session_item_node_refs(included_node_ids),
        "current_inbound_node_id": _current_inbound_node_id(
            run=run,
            draft=draft,
            included_node_ids=included_node_ids,
        ),
        "tree_tool_interaction_count": tree_tool_interaction_count,
        "tool_interaction_node_refs": _tool_interaction_node_refs(included_node_ids),
        "tree_evidence_item_count": tree_evidence_item_count,
        "evidence_node_refs": _evidence_node_refs(included_node_ids),
        "session_estimated_text_tokens": metadata_int(
            session_budget,
            "text_tokens",
        ),
        "session_estimated_text_chars": metadata_int(
            session_budget,
            "text_chars",
        ),
        "session_segment_node_count": metadata_int(
            session_budget,
            "segment_node_count",
        ),
        "session_item_range_node_count": metadata_int(
            session_budget,
            "range_node_count",
        ),
        "session_range_warning_count": metadata_int(
            session_budget,
            "range_warning_count",
        ),
        "session_range_blocked_count": metadata_int(
            session_budget,
            "range_blocked_count",
        ),
        "session_range_limited_count": metadata_int(
            session_budget,
            "range_limited_count",
        ),
        "session_budget_status": metadata_text(session_budget.get("status")) or "ok",
        "work_plan_status": metadata_text(plan_budget.get("status")),
        "work_plan_phase": metadata_text(plan_budget.get("plan_phase")),
        "work_plan_update_reason": metadata_text(plan_budget.get("update_reason")),
        "work_plan_phase_changed": bool(plan_budget.get("phase_changed")),
        "work_plan_update_count": metadata_int(plan_budget, "plan_update_count"),
        "folded_history_node_count": sum(
            1
            for node_id in included_node_ids
            if node_id.startswith("session.segment.compacted.")
            or node_id.startswith("session.segment.closed.")
            or node_id.startswith("session.segment.messages.")
        ),
        "current_inbound_session_item_id": _current_inbound_session_item_id(
            run=run,
            draft=draft,
        ),
    }
    payload.update(request_render_budget_metadata(payload))
    return payload
