from __future__ import annotations

from crxzipple.app.integration.context_workspace_session_content import (
    items_estimate,
)
from crxzipple.app.integration.context_workspace_session_content_values import (
    text_estimate,
)
from crxzipple.app.integration.context_workspace_session_item_nodes import (
    message_node_seeds,
)
from crxzipple.app.integration.context_workspace_session_segment_values import (
    chunks,
    is_archived_transcript_entry,
    matches_message_scope,
    node_part,
    segment_messages,
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


def historical_segment_range_seeds(
    *,
    parent_id: str,
    session_key: str,
    session_id: str,
    messages: tuple[SessionItem, ...],
    segment_kind: object,
    message_scope: str,
    recent_limit: int,
    historical_range_limit: int,
    range_token_soft_limit: int,
) -> tuple[ContextNodeSeed, ...]:
    scoped_messages = segment_messages(
        messages,
        session_id=session_id,
        message_scope=message_scope,
    )
    ranges: list[ContextNodeSeed] = []
    display_order = 10
    message_chunks = chunks(scoped_messages, recent_limit)
    visible_chunks = message_chunks[:historical_range_limit]
    for chunk in visible_chunks:
        ranges.append(
            segment_message_range_seed(
                parent_id=parent_id,
                session_key=session_key,
                session_id=session_id,
                messages=chunk,
                segment_kind=segment_kind,
                message_scope=message_scope,
                range_token_soft_limit=range_token_soft_limit,
                display_order=display_order,
            )
        )
        display_order += 10
    omitted_chunks = message_chunks[historical_range_limit:]
    if omitted_chunks:
        omitted_item_count = sum(len(chunk) for chunk in omitted_chunks)
        ranges.append(
            range_notice_seed(
                node_id=f"session.segment.ranges.more.{node_part(session_id)}",
                parent_id=parent_id,
                title="More Message Ranges",
                summary=(
                    f"{len(omitted_chunks)} more range pages with "
                    f"{omitted_item_count} messages are hidden by the "
                    "session range page limit."
                ),
                display_order=display_order,
                metadata={
                    "notice_kind": "range_limit",
                    "range_reason_code": "range_page_limit",
                    "segment_kind": segment_kind,
                    "message_scope": message_scope,
                    "omitted_range_count": len(omitted_chunks),
                    "omitted_item_count": omitted_item_count,
                    "range_page_limit": historical_range_limit,
                },
            ),
        )
    return tuple(ranges)


def segment_range_item_seeds(
    *,
    parent_id: str,
    session_key: str,
    session_id: str,
    messages: tuple[SessionItem, ...],
    segment_kind: object,
    message_scope: str,
    from_sequence_no: int,
    to_sequence_no: int,
    current_run_id: str | None,
    range_token_soft_limit: int,
) -> tuple[ContextNodeSeed, ...]:
    range_messages = tuple(
        message
        for message in messages
        if message.session_id == session_id
        and matches_message_scope(
            message,
            message_scope=message_scope,
        )
    )
    range_estimate = items_estimate(
        range_messages,
        current_run_id=current_run_id,
    )
    if range_estimate.text_tokens > range_token_soft_limit:
        if len(range_messages) > 1:
            return split_segment_message_range_seeds(
                parent_id=parent_id,
                session_key=session_key,
                session_id=session_id,
                messages=range_messages,
                segment_kind=segment_kind,
                message_scope=message_scope,
                range_token_soft_limit=range_token_soft_limit,
            )
        return (
            range_notice_seed(
                node_id=(
                    "session.segment.range.blocked."
                    f"{node_part(session_id)}.{from_sequence_no}.{to_sequence_no}"
                ),
                parent_id=parent_id,
                title="Range Over Budget",
                summary=(
                    "This message range exceeds the session prompt budget. "
                    "Keep the segment summary visible or use session owner tools "
                    "such as sessions_history with a narrower limit."
                ),
                display_order=10,
                metadata={
                    "notice_kind": "range_budget",
                    "range_budget_status": "blocked",
                    "range_reason_code": "over_budget",
                    "range_budget_soft_limit": range_token_soft_limit,
                    "estimated_expanded_text_tokens": range_estimate.text_tokens,
                    "estimated_expanded_text_chars": range_estimate.text_chars,
                    "item_count": len(range_messages),
                    "segment_kind": segment_kind,
                    "message_scope": message_scope,
                },
            ),
        )
    return message_node_seeds(
        range_messages,
        parent_id=parent_id,
        current_run_id=current_run_id,
        consumed_through_sequence_no=None,
        tool_lifecycle_facts={},
    )


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
