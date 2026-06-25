from __future__ import annotations

import hashlib

from crxzipple.app.integration.context_workspace_session_blocks import (
    artifact_content_candidates,
)
from crxzipple.app.integration.context_workspace_session_content import (
    tool_call_id,
    tool_interaction_prompt_content,
    tool_name,
    tool_result_status,
)
from crxzipple.app.integration.context_workspace_session_content_values import (
    json_fragment,
    optional_text,
    text_estimate,
    truncate,
)
from crxzipple.app.integration.context_workspace_session_tool_interaction_summary import (
    tool_interaction_summary,
)
from crxzipple.app.integration.context_workspace_session_segment_values import (
    is_archived_transcript_entry,
    node_part,
)
from crxzipple.app.integration.context_workspace_session_tool_result_content import (
    tool_result_content,
    tool_result_envelope_metadata,
    tool_result_error_json,
)
from crxzipple.app.integration.context_workspace_session_tool_lifecycle import (
    is_failed_tool_status,
    tool_interaction_observed,
    tool_interaction_superseded,
    tool_interaction_superseded_by_tool_call_id,
)
from crxzipple.modules.context_workspace.domain import (
    ContextAction,
    ContextNodeSeed,
    ContextNodeState,
)
from crxzipple.modules.session.domain import SessionItem
from crxzipple.shared.time import format_datetime_utc


_BASIC_ACTIONS = (
    ContextAction.EXPAND,
    ContextAction.COLLAPSE,
    ContextAction.PIN,
    ContextAction.UNPIN,
    ContextAction.ESTIMATE,
)

_TOOL_INTERACTION_NODE_REVISION = "2026-06-09.tool_interaction_visible_result.v2"


def tool_interaction_node_seed(
    *,
    call_message: SessionItem,
    result_message: SessionItem,
    parent_id: str,
    frontier: bool = False,
    consumed_through_sequence_no: int | None = None,
    current_run_id: str | None = None,
    current_inbound_sequence_no: int | None = None,
    lifecycle_facts: dict[str, object] | None = None,
) -> ContextNodeSeed:
    del current_run_id
    call_id = tool_call_id(call_message) or tool_call_id(result_message) or ""
    seed_tool_name = tool_name(call_message) or tool_name(result_message) or "tool"
    status = tool_result_status(result_message) or "unknown"
    arguments_json = json_fragment(call_message.content_payload.get("arguments") or {})
    result_content = tool_result_content(result_message)
    artifact_candidates = artifact_content_candidates(result_message)
    result_envelope = tool_result_envelope_metadata(result_message)
    error_json = tool_result_error_json(result_message)
    frontier = bool(frontier)
    current_turn = (
        current_inbound_sequence_no is not None
        and call_message.sequence_no >= current_inbound_sequence_no
    )
    archived = is_archived_transcript_entry(
        call_message,
    ) or is_archived_transcript_entry(result_message)
    consumed = not frontier
    opened_by_default = False
    collapsed_by_default = not frontier and not opened_by_default
    failed = is_failed_tool_status(status)
    observed = tool_interaction_observed(
        tool_name=seed_tool_name,
        status=status,
        result_message=result_message,
    )
    superseded = tool_interaction_superseded(
        result_message,
        lifecycle_facts=lifecycle_facts,
    )
    superseded_by_tool_call_id = tool_interaction_superseded_by_tool_call_id(
        result_message,
        lifecycle_facts=lifecycle_facts,
    )
    lifecycle_status = (
        "frontier_failed"
        if frontier and failed
        else "frontier"
        if frontier
        else "failed"
        if failed
        else "superseded"
        if superseded
        else "observed"
        if observed
        else "consumed"
    )
    content = tool_interaction_prompt_content(
        tool_name=seed_tool_name,
        tool_call_id=call_id,
        status=status,
        arguments_json=arguments_json,
        result_content=result_content,
        error_json=error_json,
    )
    summary = tool_interaction_summary(
        tool_name=seed_tool_name,
        status=status,
        frontier=frontier,
        current_turn=current_turn,
        arguments_json=arguments_json,
        result_content=result_content,
        error_json=error_json,
    )
    visibility_status = (
        "frontier_protocol_tail" if frontier else "folded_consumed_history"
    )
    return ContextNodeSeed(
        node_id=(
            f"session.tool_interaction.{call_message.session_id}."
            f"{node_part(call_id or str(call_message.sequence_no))}"
        ),
        parent_id=parent_id,
        owner="session",
        kind="tool_interaction",
        title=f"{call_message.sequence_no}-{result_message.sequence_no}. {seed_tool_name}",
        summary=truncate(summary, 320),
        content=content,
        state=ContextNodeState(
            collapsed=collapsed_by_default,
            loaded=True,
            opened=opened_by_default,
            consumed=consumed,
            archived=archived,
            status="archived" if archived else "available",
            render_reason="archived_by_compaction" if archived else "",
        ),
        actions=_BASIC_ACTIONS,
        owner_ref={
            "session_key": call_message.session_key,
            "session_id": call_message.session_id,
            "tool_call_id": call_id,
            "tool_name": seed_tool_name,
            "arguments_json": arguments_json,
            "result_content": result_content,
            "has_artifact_content_candidates": bool(artifact_candidates),
            "status": status,
            "lifecycle_status": lifecycle_status,
            "frontier": frontier,
            "current_turn": current_turn,
            "consumed": consumed,
            "failed": failed,
            "observed": observed,
            "superseded": superseded,
            "superseded_by_tool_call_id": superseded_by_tool_call_id or "",
            "call_session_item_id": call_message.id,
            "result_session_item_id": result_message.id,
            "call_sequence_no": call_message.sequence_no,
            "result_sequence_no": result_message.sequence_no,
            "consumed_through_sequence_no": consumed_through_sequence_no,
            "visibility": _visibility_label(result_message),
            "archived": archived,
        },
        estimate=text_estimate(content if not collapsed_by_default else summary),
        revision=_TOOL_INTERACTION_NODE_REVISION,
        display_order=call_message.sequence_no,
        metadata={
            "created_at": format_datetime_utc(call_message.created_at),
            "tool_call_id": call_id,
            "tool_name": seed_tool_name,
            "status": status,
            "arguments_json": arguments_json,
            "result_content": result_content,
            "artifact_content_candidates": artifact_candidates,
            "tool_result_envelope": result_envelope,
            "error_json": error_json,
            "call_source_kind": call_message.source_kind,
            "call_source_id": call_message.source_id,
            "result_source_kind": result_message.source_kind,
            "result_source_id": result_message.source_id,
            "call_sequence_no": call_message.sequence_no,
            "result_sequence_no": result_message.sequence_no,
            "archived": archived,
            "consumed_through_sequence_no": consumed_through_sequence_no,
            "snapshot_visibility_status": visibility_status,
            "lifecycle_status": lifecycle_status,
            "frontier": frontier,
            "current_turn": current_turn,
            "consumed": consumed,
            "failed": failed,
            "observed": observed,
            "superseded": superseded,
            "superseded_by_tool_call_id": superseded_by_tool_call_id or "",
            "collapsed_by_default": collapsed_by_default,
            "opened_by_default": opened_by_default,
            "content_digest": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        },
    )


def is_tool_interaction_frontier(
    *,
    call_message: SessionItem,
    result_message: SessionItem,
    current_inbound_sequence_no: int | None,
    consumed_through_sequence_no: int | None,
) -> bool:
    if current_inbound_sequence_no is None:
        return False
    if call_message.sequence_no < current_inbound_sequence_no:
        return False
    if consumed_through_sequence_no is None:
        return False
    return result_message.sequence_no > consumed_through_sequence_no


def tool_lifecycle_facts_for_result(
    result_message: SessionItem,
    facts_by_ref: dict[str, dict[str, object]],
) -> dict[str, object] | None:
    if not facts_by_ref:
        return None
    refs = (
        tool_call_id(result_message),
        result_message.id,
        optional_text(result_message.content_payload.get("tool_run_id")),
    )
    merged: dict[str, object] = {}
    for ref in refs:
        if ref is None:
            continue
        facts = facts_by_ref.get(ref)
        if facts:
            merged.update(facts)
    return merged or None

def _visibility_label(message: object) -> str:
    if is_archived_transcript_entry(message):
        return "archived"
    return "default"
