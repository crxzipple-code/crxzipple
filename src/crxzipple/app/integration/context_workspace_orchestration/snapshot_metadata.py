"""Snapshot metadata helpers for Context Workspace orchestration integration."""

from __future__ import annotations

from crxzipple.modules.context_workspace.application import (
    CONTEXT_INSTRUCTIONS_NODE_ID,
    CONTEXT_TREE_SCHEMA_VERSION,
    EXECUTION_CURRENT_NODE_ID,
    SESSION_CURRENT_NODE_ID,
)
from crxzipple.modules.llm.domain import ToolSchema
from crxzipple.modules.orchestration.application.runtime_llm_request_draft import RuntimeLlmRequestDraft
from crxzipple.modules.orchestration.domain import OrchestrationRun
from crxzipple.shared.request_render_budget import request_render_budget_metadata

from ._metadata import (
    estimate_text_tokens,
    estimate_text_tokens_from_chars,
    metadata_dict,
    metadata_int,
    metadata_text,
)
from .artifact_mirror import artifact_content_budget


def build_snapshot_provider_attachments(
    rendered_attachments: dict[str, object],
    *,
    draft: RuntimeLlmRequestDraft,
) -> dict[str, object]:
    return dict(rendered_attachments)


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
    draft_input_chars = _draft_input_chars(draft)
    draft_input_tokens = estimate_text_tokens_from_chars(draft_input_chars)
    draft_input_session_item_refs = _draft_input_session_item_refs(draft)
    draft_input_budget = _draft_transcript_budget(draft)
    protocol_required_refs = _merged_protocol_required_refs(
        draft_input_session_item_refs,
        draft_input_budget,
    )
    execution_chain_protocol_required_refs = _metadata_dict_list(
        draft_input_budget.get("execution_chain_protocol_required_refs"),
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
    tool_schema_budget = metadata_dict(
        provider_attachment_report.get("tool_schema_mirror_budget"),
    )
    mirrored_schema_tokens = mirrored_schema_estimated_tokens(provider_attachments)
    content_budget = artifact_content_budget(
        provider_attachments=provider_attachments,
        artifact_content_blocks=artifact_content_blocks,
    )
    artifact_content_tokens = metadata_int(
        content_budget,
        "estimated_tokens",
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
        "mirrored_tool_schema_count": tool_schema_count,
        "mirrored_tool_schema_estimated_tokens": mirrored_schema_tokens,
        "tool_schema_mirror_budget": dict(tool_schema_budget),
        "tool_schema_mirror_budget_status": (
            metadata_text(tool_schema_budget.get("status")) or "ok"
        ),
        "tool_schema_mirror_default_schema_source": metadata_text(
            tool_schema_budget.get("default_schema_source"),
        ),
        "tool_schema_mirror_available_count": metadata_int(
            tool_schema_budget,
            "available_count",
        ),
        "tool_schema_mirror_enabled_candidate_count": metadata_int(
            tool_schema_budget,
            "enabled_candidate_count",
        ),
        "tool_schema_mirror_default_requested_count": metadata_int(
            tool_schema_budget,
            "default_requested_count",
        ),
        "tool_schema_mirror_default_candidate_count": metadata_int(
            tool_schema_budget,
            "default_candidate_count",
        ),
        "tool_schema_mirror_default_mirrored_count": metadata_int(
            tool_schema_budget,
            "default_mirrored_count",
        ),
        "tool_schema_mirror_duplicate_count": metadata_int(
            tool_schema_budget,
            "duplicate_count",
        ),
        "tool_schema_mirror_groups": _metadata_dict_list(
            tool_schema_budget.get("groups"),
        ),
        "tool_schema_mirror_group_count": metadata_int(
            tool_schema_budget,
            "group_count",
        ),
        "tool_schema_mirror_visible_group_count": metadata_int(
            tool_schema_budget,
            "visible_group_count",
        ),
        "tool_schema_mirror_collapsed_group_count": metadata_int(
            tool_schema_budget,
            "collapsed_group_count",
        ),
        "tool_schema_mirror_default_group_count": metadata_int(
            tool_schema_budget,
            "default_group_count",
        ),
        "tool_schema_mirror_default_group_refs": _metadata_dict_list(
            tool_schema_budget.get("default_group_refs"),
        ),
        "tool_schema_mirror_default_group_ref_count": metadata_int(
            tool_schema_budget,
            "default_group_ref_count",
        ),
        "tool_schema_mirror_default_group_matches": _metadata_dict_list(
            tool_schema_budget.get("default_group_matches"),
        ),
        "tool_schema_mirror_default_group_match_count": metadata_int(
            tool_schema_budget,
            "default_group_match_count",
        ),
        "tool_schema_mirror_default_schema_priorities": metadata_dict(
            tool_schema_budget.get("default_schema_priorities"),
        ),
        "tool_schema_mirror_default_schema_reasons": metadata_dict(
            tool_schema_budget.get("default_schema_reasons"),
        ),
        "tool_schema_mirror_default_mirrored": _metadata_dict_list(
            tool_schema_budget.get("default_mirrored"),
        ),
        "tool_schema_mirror_skipped": _metadata_dict_list(
            tool_schema_budget.get("skipped"),
        ),
        "tool_schema_mirror_skipped_by_reason": metadata_dict(
            tool_schema_budget.get("skipped_by_reason"),
        ),
        "tool_schema_mirror_skipped_count": metadata_int(
            tool_schema_budget,
            "skipped_count",
        ),
        "tool_schema_mirror_max_count": metadata_int(
            tool_schema_budget,
            "max_count",
        ),
        "tool_schema_mirror_max_estimated_tokens": metadata_int(
            tool_schema_budget,
            "max_estimated_tokens",
        ),
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
        "draft_input_message_count": len(draft.messages),
        "draft_input_roles": [message.role.value for message in draft.messages],
        "draft_input_chars": draft_input_chars,
        "draft_input_estimated_tokens": draft_input_tokens,
        "draft_input_session_item_refs": draft_input_session_item_refs,
        "draft_input_session_item_count": len(draft_input_session_item_refs),
        "draft_input_session_item_frontier": _session_item_frontier(
            draft_input_session_item_refs,
        ),
        "draft_input_budget": draft_input_budget,
        "protocol_required_refs": protocol_required_refs,
        "protocol_required_ref_count": len(protocol_required_refs),
        "execution_chain_protocol_required_refs": (
            execution_chain_protocol_required_refs
        ),
        "execution_chain_protocol_required_ref_count": len(
            execution_chain_protocol_required_refs,
        ),
        "debug_body_chars": debug_body_chars,
        "debug_body_estimated_tokens": debug_body_tokens,
        "estimated_provider_input_tokens": (
            debug_body_tokens
            + draft_input_tokens
            + mirrored_schema_tokens
            + artifact_content_tokens
        ),
        "artifact_content_budget": dict(content_budget),
        "artifact_content_estimated_tokens": artifact_content_tokens,
        "artifact_content_candidate_count": metadata_int(
            content_budget,
            "candidate_count",
        ),
        "artifact_content_text_block_count": metadata_int(
            content_budget,
            "text_block_count",
        ),
        "artifact_content_image_count": metadata_int(
            content_budget,
            "image_count",
        ),
        "artifact_content_file_count": metadata_int(
            content_budget,
            "file_count",
        ),
        "artifact_content_omitted_count": metadata_int(
            content_budget,
            "omitted_count",
        ),
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
        "artifact_content_block_count": len(artifact_content_blocks),
        "current_inbound_session_item_id": _current_inbound_session_item_id(
            run=run,
            draft=draft,
        ),
    }
    payload.update(request_render_budget_metadata(payload))
    return payload


def mirrored_schema_estimated_tokens(provider_attachments: dict[str, object]) -> int:
    raw_schemas = provider_attachments.get("tool_schemas")
    if not isinstance(raw_schemas, list):
        return 0
    total_chars = 0
    for schema in raw_schemas:
        if not isinstance(schema, dict):
            continue
        total_chars += len(str(schema.get("name") or ""))
        total_chars += len(str(schema.get("description") or ""))
        total_chars += len(str(schema.get("input_schema") or ""))
    return estimate_text_tokens_from_chars(total_chars)


def _provider_tool_schema_names(
    provider_attachments: dict[str, object],
) -> tuple[str, ...]:
    raw_schemas = provider_attachments.get("tool_schemas")
    if not isinstance(raw_schemas, list):
        return ()
    names: list[str] = []
    for schema in raw_schemas:
        if not isinstance(schema, dict):
            continue
        name = metadata_text(schema.get("name"))
        if name is not None:
            names.append(name)
    return tuple(dict.fromkeys(names))


def _top_rendered_nodes(estimate_breakdown: dict[str, object]) -> list[dict[str, object]]:
    value = estimate_breakdown.get("top_rendered_nodes")
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def mirrored_tool_schemas(
    provider_attachments: dict[str, object],
    *,
    mirror_available: bool,
) -> tuple[ToolSchema, ...] | None:
    if not mirror_available:
        return None
    raw_schemas = provider_attachments.get("tool_schemas")
    if not isinstance(raw_schemas, list):
        return ()
    schemas: list[ToolSchema] = []
    for raw_schema in raw_schemas:
        if not isinstance(raw_schema, dict):
            continue
        name = raw_schema.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        input_schema = raw_schema.get("input_schema")
        schemas.append(
            ToolSchema(
                name=name,
                description=(
                    str(raw_schema.get("description"))
                    if raw_schema.get("description") is not None
                    else ""
                ),
                input_schema=(
                    dict(input_schema) if isinstance(input_schema, dict) else {}
                ),
            ),
        )
    return tuple(schemas)


def _session_item_node_refs(
    included_node_ids: tuple[str, ...],
) -> list[dict[str, object]]:
    refs: list[dict[str, object]] = []
    prefix = "session.item."
    for node_id in included_node_ids:
        if not node_id.startswith(prefix):
            continue
        tail = node_id[len(prefix):]
        session_id, separator, sequence_text = tail.rpartition(".")
        if not separator or not session_id or not sequence_text.isdigit():
            refs.append({"node_id": node_id})
            continue
        refs.append(
            {
                "node_id": node_id,
                "session_id": session_id,
                "sequence_no": int(sequence_text),
            },
        )
    return refs


def _tool_interaction_node_refs(
    included_node_ids: tuple[str, ...],
) -> list[dict[str, object]]:
    refs: list[dict[str, object]] = []
    prefix = "session.tool_interaction."
    for node_id in included_node_ids:
        if not node_id.startswith(prefix):
            continue
        refs.append({"node_id": node_id})
    return refs


def _evidence_node_refs(
    included_node_ids: tuple[str, ...],
) -> list[dict[str, object]]:
    refs: list[dict[str, object]] = []
    prefix = "session.evidence."
    for node_id in included_node_ids:
        if not node_id.startswith(prefix) or node_id == "session.evidence.current":
            continue
        refs.append({"node_id": node_id})
    return refs


def _current_inbound_node_id(
    *,
    run: OrchestrationRun,
    draft: RuntimeLlmRequestDraft,
    included_node_ids: tuple[str, ...],
) -> str | None:
    included = set(included_node_ids)
    for message in draft.messages:
        metadata = message.metadata
        if metadata.get("source_kind") != "orchestration_run":
            continue
        if metadata.get("source_id") != run.id:
            continue
        session_id = metadata.get("session_id")
        sequence_no = metadata.get("sequence_no")
        if not isinstance(session_id, str) or not session_id.strip():
            continue
        if isinstance(sequence_no, int):
            sequence_text = str(sequence_no)
        elif isinstance(sequence_no, str) and sequence_no.strip().isdigit():
            sequence_text = sequence_no.strip()
        else:
            continue
        node_id = f"session.item.{session_id.strip()}.{sequence_text}"
        if node_id in included:
            return node_id
    return None


def _current_inbound_session_item_id(
    *,
    run: OrchestrationRun,
    draft: RuntimeLlmRequestDraft,
) -> str | None:
    for message in draft.messages:
        metadata = message.metadata
        if metadata.get("source_kind") != "orchestration_run":
            continue
        if metadata.get("source_id") != run.id:
            continue
        session_item_id = metadata.get("session_item_id")
        if isinstance(session_item_id, str) and session_item_id.strip():
            return session_item_id.strip()
    return None


def _draft_input_chars(draft: RuntimeLlmRequestDraft) -> int:
    return sum(_llm_message_content_chars(message.content) for message in draft.messages)


def _draft_input_session_item_refs(draft: RuntimeLlmRequestDraft) -> list[dict[str, object]]:
    refs: list[dict[str, object]] = []
    for message in draft.messages:
        metadata = message.metadata
        item_id = metadata_text(metadata.get("session_item_id"))
        session_id = metadata_text(metadata.get("session_id"))
        sequence_no = _metadata_int_value(metadata.get("sequence_no"))
        if item_id is None or session_id is None or sequence_no is None:
            continue
        ref: dict[str, object] = {
            "owner_module": "session",
            "owner_kind": "session_item",
            "owner_id": item_id,
            "item_id": item_id,
            "session_id": session_id,
            "sequence_no": sequence_no,
            "role": message.role.value,
            "render_mode": "full",
            "render_scope": "provider_replay",
        }
        for key in (
            "kind",
            "phase",
            "source_module",
            "source_kind",
            "source_id",
            "provider_item_id",
            "provider_item_type",
            "tool_call_id",
            "tool_name",
            "tool_status",
        ):
            value = metadata_text(metadata.get(key))
            if value is not None:
                ref[key] = value
        refs.append(ref)
    return refs


def _protocol_required_refs(
    refs: list[dict[str, object]],
) -> list[dict[str, object]]:
    required: list[dict[str, object]] = []
    for ref in refs:
        kind = metadata_text(ref.get("kind"))
        if kind not in {"tool_call", "tool_result", "provider_external_item"}:
            continue
        payload = dict(ref)
        payload["protocol_required"] = True
        payload["budget_class"] = "protocol_required"
        required.append(payload)
    return required


def _merged_protocol_required_refs(
    draft_refs: list[dict[str, object]],
    transcript_budget: dict[str, object],
) -> list[dict[str, object]]:
    refs = [
        *_protocol_required_refs(draft_refs),
        *_metadata_dict_list(transcript_budget.get("protocol_required_refs")),
    ]
    deduped: list[dict[str, object]] = []
    seen: set[tuple[object, object, object, object, object]] = set()
    for ref in refs:
        identity = (
            ref.get("owner_module"),
            ref.get("owner_kind"),
            ref.get("owner_id"),
            ref.get("item_id"),
            ref.get("tool_call_id"),
        )
        if identity in seen:
            continue
        seen.add(identity)
        payload = dict(ref)
        payload["protocol_required"] = True
        payload["budget_class"] = "protocol_required"
        deduped.append(payload)
    return deduped


def _draft_transcript_budget(draft: RuntimeLlmRequestDraft) -> dict[str, object]:
    if draft.report is None:
        return _draft_input_session_item_budget(draft)
    report_payload = draft.report.to_payload()
    transcript = report_payload.get("transcript")
    if not isinstance(transcript, dict):
        return _draft_input_session_item_budget(draft)
    budget = transcript.get("budget")
    if not isinstance(budget, dict):
        return _draft_input_session_item_budget(draft)
    normalized = dict(budget)
    if normalized:
        return normalized
    return _draft_input_session_item_budget(draft)


def _draft_input_session_item_budget(draft: RuntimeLlmRequestDraft) -> dict[str, object]:
    draft_refs = _draft_input_session_item_refs(draft)
    if not draft_refs:
        return {}
    return {
        "source": "session_items",
        "budget_unit": "chars",
        "input_item_count": len(draft_refs),
        "included_item_count": len(draft_refs),
        "collapsed_item_count": 0,
        "truncated": False,
        "frontier": _session_item_frontier(draft_refs),
        "included_refs": draft_refs,
        "protocol_required_refs": _protocol_required_refs(draft_refs),
        "protocol_required_preserved": True,
    }


def _session_item_frontier(
    refs: list[dict[str, object]],
) -> dict[str, object]:
    sequence_numbers = [
        ref.get("sequence_no") for ref in refs if isinstance(ref.get("sequence_no"), int)
    ]
    if not sequence_numbers:
        return {}
    payload: dict[str, object] = {
        "from_sequence_no": min(sequence_numbers),
        "to_sequence_no": max(sequence_numbers),
        "item_count": len(sequence_numbers),
    }
    first_id = refs[0].get("item_id")
    last_id = refs[-1].get("item_id")
    if isinstance(first_id, str):
        payload["from_item_id"] = first_id
    if isinstance(last_id, str):
        payload["to_item_id"] = last_id
    return payload


def _metadata_int_value(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _metadata_dict_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, (list, tuple)):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _metadata_text_list(value: object) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    values = [metadata_text(item) for item in value]
    return list(dict.fromkeys(item for item in values if item is not None))


def _llm_message_content_chars(content: object) -> int:
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        return sum(_llm_content_block_chars(item) for item in content)
    if content is None:
        return 0
    return len(str(content))


def _llm_content_block_chars(value: object) -> int:
    if isinstance(value, dict):
        text = value.get("text")
        if isinstance(text, str):
            return len(text)
        data = value.get("data")
        if isinstance(data, str):
            return len(data)
        return len(str(value))
    if value is None:
        return 0
    return len(str(value))
