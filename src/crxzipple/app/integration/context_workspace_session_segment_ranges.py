from __future__ import annotations

from crxzipple.app.integration.context_workspace_session_content import (
    items_estimate,
)
from crxzipple.app.integration.context_workspace_session_content_values import (
    text_estimate,
)
from crxzipple.app.integration.context_workspace_session_segment_values import (
    is_archived_transcript_entry,
    node_part,
)
from crxzipple.modules.context_workspace.domain import (
    ContextAction,
    ContextEstimate,
    ContextNodeSeed,
    ContextNodeState,
)
from crxzipple.modules.session.domain import SessionItem


_BASIC_ACTIONS = (
    ContextAction.EXPAND,
    ContextAction.COLLAPSE,
    ContextAction.PIN,
    ContextAction.UNPIN,
    ContextAction.ESTIMATE,
)


def segment_message_range_seed(
    *,
    parent_id: str,
    session_key: str,
    session_id: str,
    messages: tuple[SessionItem, ...],
    segment_kind: object,
    message_scope: str,
    range_token_soft_limit: int,
    display_order: int,
) -> ContextNodeSeed:
    first_sequence_no = messages[0].sequence_no
    last_sequence_no = messages[-1].sequence_no
    estimate = items_estimate(messages, current_run_id=None)
    archived = all(is_archived_transcript_entry(message) for message in messages)
    budget_status = range_budget_status(
        estimate=estimate,
        item_count=len(messages),
        soft_limit=range_token_soft_limit,
    )
    summary = (
        f"{len(messages)} messages in this segment, sequences "
        f"{first_sequence_no}-{last_sequence_no}."
    )
    if budget_status == "split_required":
        summary = f"{summary} Expanding this range will reveal smaller ranges first."
    elif budget_status == "blocked":
        summary = f"{summary} Expanding this range is blocked by the session budget."
    return ContextNodeSeed(
        node_id=(
            f"session.segment.items.{node_part(session_id)}."
            f"{first_sequence_no}.{last_sequence_no}"
        ),
        parent_id=parent_id,
        owner="session",
        kind="session_item_range",
        title=f"Messages {first_sequence_no}-{last_sequence_no}",
        summary=summary,
        state=ContextNodeState(
            collapsed=True,
            loaded=False,
            archived=archived,
            status="archived" if archived else "available",
            render_reason="archived_by_compaction" if archived else "",
        ),
        actions=_BASIC_ACTIONS,
        owner_ref={
            "session_key": session_key,
            "session_id": session_id,
            "from_sequence_no": first_sequence_no,
            "to_sequence_no": last_sequence_no,
            "item_count": len(messages),
            "segment_kind": segment_kind,
            "message_scope": message_scope,
            "archived": archived,
        },
        estimate=ContextEstimate(text_chars=80, text_tokens=20),
        display_order=display_order,
        metadata={
            "item_count": len(messages),
            "segment_kind": segment_kind,
            "message_scope": message_scope,
            "archived": archived,
            "archived_count": sum(
                1
                for message in messages
                if is_archived_transcript_entry(message)
            ),
            "range_budget_status": budget_status,
            "range_reason_code": range_reason_code(budget_status),
            "range_budget_soft_limit": range_token_soft_limit,
            "estimated_expanded_text_tokens": estimate.text_tokens,
            "estimated_expanded_text_chars": estimate.text_chars,
        },
    )


def split_segment_message_range_seeds(
    *,
    parent_id: str,
    session_key: str,
    session_id: str,
    messages: tuple[SessionItem, ...],
    segment_kind: object,
    message_scope: str,
    range_token_soft_limit: int,
) -> tuple[ContextNodeSeed, ...]:
    midpoint = max(len(messages) // 2, 1)
    split_chunks = tuple(
        chunk for chunk in (messages[:midpoint], messages[midpoint:]) if chunk
    )
    seeds: list[ContextNodeSeed] = []
    display_order = 10
    for chunk in split_chunks:
        seeds.append(
            segment_message_range_seed(
                parent_id=parent_id,
                session_key=session_key,
                session_id=session_id,
                messages=chunk,
                segment_kind=segment_kind,
                message_scope=message_scope,
                range_token_soft_limit=range_token_soft_limit,
                display_order=display_order,
            ),
        )
        display_order += 10
    return tuple(seeds)


def range_notice_seed(
    *,
    node_id: str,
    parent_id: str,
    title: str,
    summary: str,
    display_order: int,
    metadata: dict[str, object],
) -> ContextNodeSeed:
    return ContextNodeSeed(
        node_id=node_id,
        parent_id=parent_id,
        owner="session",
        kind="session_range_notice",
        title=title,
        summary=summary,
        state=ContextNodeState(collapsed=False, loaded=True),
        actions=_BASIC_ACTIONS,
        estimate=text_estimate(summary),
        display_order=display_order,
        metadata=metadata,
    )


def range_budget_status(
    *,
    estimate: ContextEstimate,
    item_count: int,
    soft_limit: int,
) -> str:
    if estimate.text_tokens <= soft_limit:
        return "ok"
    if item_count > 1:
        return "split_required"
    return "blocked"


def range_reason_code(budget_status: str) -> str:
    if budget_status == "split_required":
        return "split_required"
    if budget_status == "blocked":
        return "over_budget"
    return "within_budget"
