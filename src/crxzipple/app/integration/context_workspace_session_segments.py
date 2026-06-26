from __future__ import annotations

from crxzipple.app.integration.context_workspace_session_content_values import (
    text_estimate,
    truncate,
)
from crxzipple.app.integration.context_workspace_session_segment_values import (
    historical_segment_kind,
    is_archived_transcript_entry,
    node_part,
    segment_summary_text,
)
from crxzipple.modules.context_workspace.domain import (
    ContextAction,
    ContextNodeSeed,
    ContextNodeState,
)
from crxzipple.modules.session.domain import SessionInstance, SessionItem
from crxzipple.shared.time import format_datetime_utc


_BASIC_ACTIONS = (
    ContextAction.EXPAND,
    ContextAction.COLLAPSE,
    ContextAction.PIN,
    ContextAction.UNPIN,
    ContextAction.ESTIMATE,
)


def session_instance_seed(
    *,
    instance: SessionInstance,
    item_count: int | None,
    parent_id: str,
    active: bool,
    display_order: int,
) -> ContextNodeSeed:
    if active:
        summary = (
            f"Active {instance.kind.value} instance #{instance.sequence_no} has "
            f"{item_count or 0} visible items."
        )
        node_id = "session.instance.active"
        title = "Active Instance"
    else:
        summary = f"Closed {instance.kind.value} instance #{instance.sequence_no}."
        node_id = f"session.instance.closed.{node_part(instance.id)}"
        title = f"Closed Instance #{instance.sequence_no}"
    return ContextNodeSeed(
        node_id=node_id,
        parent_id=parent_id,
        owner="session",
        kind="session_instance",
        title=title,
        summary=summary,
        state=ContextNodeState(collapsed=False, loaded=True),
        actions=_BASIC_ACTIONS,
        owner_ref={
            "session_key": instance.session_key,
            "session_id": instance.id,
            "sequence_no": instance.sequence_no,
            "status": instance.status,
            "active": active,
            "item_count": item_count or 0,
        },
        estimate=text_estimate(summary),
        display_order=display_order,
        metadata={
            "opened_at": format_datetime_utc(instance.opened_at),
            "closed_at": (
                format_datetime_utc(instance.closed_at)
                if instance.closed_at is not None
                else None
            ),
            "item_count": item_count,
        },
    )


def session_segments_root_seed(
    *,
    instance: SessionInstance,
    parent_id: str,
    active: bool,
) -> ContextNodeSeed:
    summary = f"Segments for session instance #{instance.sequence_no}."
    return ContextNodeSeed(
        node_id=(
            "session.segments.active"
            if active
            else f"session.segments.closed.{node_part(instance.id)}"
        ),
        parent_id=parent_id,
        owner="session",
        kind="session_segments_root",
        title="Segments",
        summary=summary,
        state=ContextNodeState(collapsed=False, loaded=True),
        actions=_BASIC_ACTIONS,
        owner_ref={
            "session_key": instance.session_key,
            "session_id": instance.id,
            "active": active,
        },
        estimate=text_estimate(summary),
        display_order=10,
    )


def session_segment_seed(
    *,
    instance: SessionInstance,
    item_count: int,
    parent_id: str,
    active: bool,
    display_order: int,
) -> ContextNodeSeed:
    segment_kind = "active" if active else historical_segment_kind(instance)
    summary = (
        f"{segment_kind.title()} segment for instance #{instance.sequence_no} has "
        f"{item_count} visible items."
    )
    return ContextNodeSeed(
        node_id=(
            "session.segment.active"
            if active
            else f"session.segment.{segment_kind}.{node_part(instance.id)}"
        ),
        parent_id=parent_id,
        owner="session",
        kind="session_segment",
        title=f"{segment_kind.title()} Segment",
        summary=summary,
        state=ContextNodeState(collapsed=False, loaded=True),
        actions=_BASIC_ACTIONS,
        owner_ref={
            "session_key": instance.session_key,
            "session_id": instance.id,
            "sequence_no": instance.sequence_no,
            "status": instance.status,
            "segment_kind": segment_kind,
            "item_count": item_count,
        },
        estimate=text_estimate(summary),
        display_order=display_order,
        metadata={
            "opened_at": format_datetime_utc(instance.opened_at),
            "closed_at": (
                format_datetime_utc(instance.closed_at)
                if instance.closed_at is not None
                else None
            ),
            "item_count": item_count,
        },
    )


def current_turn_seed(
    *,
    run_id: str,
    session_key: str,
    session_id: str | None,
    parent_id: str,
    display_order: int,
) -> ContextNodeSeed:
    summary = f"Current turn runtime facts are owned by orchestration run {run_id}."
    return ContextNodeSeed(
        node_id="session.turn.current",
        parent_id=parent_id,
        owner="session",
        kind="session_turn",
        title="Current Turn",
        summary=summary,
        state=ContextNodeState(collapsed=False, loaded=True),
        actions=_BASIC_ACTIONS,
        owner_ref={
            "session_key": session_key,
            "session_id": session_id or "",
            "run_id": run_id,
            "turn_id": run_id,
        },
        estimate=text_estimate(summary),
        display_order=display_order,
        metadata={"run_id": run_id},
    )


def historical_segment_seed(
    *,
    instance: SessionInstance,
    messages: tuple[SessionItem, ...] | None,
    parent_id: str,
    segment_kind: str,
    message_scope: str,
    fallback_summary: str | None,
    display_order: int,
) -> ContextNodeSeed:
    summary_text = segment_summary_text(instance.metadata) or fallback_summary
    item_count = len(messages) if messages is not None else None
    archived_count = sum(
        1
        for message in messages or ()
        if is_archived_transcript_entry(message)
    )
    fallback = f"{segment_kind.title()} segment #{instance.sequence_no} is available."
    if item_count is not None:
        fallback = (
            f"{segment_kind.title()} segment #{instance.sequence_no} has "
            f"{item_count} messages."
        )
    if archived_count > 0:
        fallback = (
            f"{segment_kind.title()} segment #{instance.sequence_no} has "
            f"{archived_count} archived messages."
        )
    summary = truncate(summary_text or fallback, 320)
    owner_ref: dict[str, object] = {
        "session_key": instance.session_key,
        "session_id": instance.id,
        "sequence_no": instance.sequence_no,
        "status": instance.status,
        "segment_kind": segment_kind,
        "message_scope": message_scope,
        "archived_count": archived_count,
        "has_summary": bool(summary_text),
    }
    metadata: dict[str, object] = {
        "opened_at": format_datetime_utc(instance.opened_at),
        "closed_at": (
            format_datetime_utc(instance.closed_at)
            if instance.closed_at is not None
            else ""
        ),
        "reset_reason": instance.reset_reason or "",
        "archived_count": archived_count,
        "message_scope": message_scope,
        "has_summary": bool(summary_text),
    }
    if item_count is not None:
        owner_ref["item_count"] = item_count
        metadata["item_count"] = item_count
    return ContextNodeSeed(
        node_id=f"session.segment.{segment_kind}.{node_part(instance.id)}",
        parent_id=parent_id,
        owner="session",
        kind="session_segment",
        title=f"{segment_kind.title()} Segment #{instance.sequence_no}",
        summary=summary,
        content=summary_text or "",
        state=ContextNodeState(collapsed=True, loaded=False),
        actions=_BASIC_ACTIONS,
        owner_ref=owner_ref,
        estimate=text_estimate(summary),
        display_order=display_order,
        metadata=metadata,
    )
