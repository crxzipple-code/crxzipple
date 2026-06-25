from __future__ import annotations

import hashlib
from typing import Any

from crxzipple.app.integration.context_workspace_session_blocks import (
    content_block_types,
)
from crxzipple.app.integration.context_workspace_session_content import (
    kind_label,
    message_estimate,
    message_preview,
    message_prompt_content,
)
from crxzipple.app.integration.context_workspace_session_segment_values import (
    is_archived_transcript_entry,
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


def message_node_seed(
    message: SessionItem,
    *,
    parent_id: str,
    current_run_id: str | None = None,
) -> ContextNodeSeed:
    archived = is_archived_transcript_entry(message)
    current_inbound = is_current_inbound_message(
        message,
        current_run_id=current_run_id,
    )
    preview = (
        "Delivered as provider user message for this turn."
        if current_inbound
        else message_preview(message)
    )
    content = "" if current_inbound else message_prompt_content(message)
    owner_ref: dict[str, object] = {
        "session_key": message.session_key,
        "session_id": message.session_id,
        "session_item_id": message.id,
        "sequence_no": message.sequence_no,
        "role": message.role,
        "kind": kind_label(message),
        "visibility": _visibility_label(message),
        "source_module": getattr(message, "source_module", "") or "",
        "source_kind": message.source_kind or "",
        "source_id": message.source_id or "",
    }
    for key in (
        "archived_reason",
        "archived_by_compaction_run_id",
        "compacted_segment_id",
        "archived_through_item_sequence_no",
        "summary_item_id",
    ):
        value = message.metadata.get(key)
        if value not in (None, "", {}, []):
            owner_ref[key] = value
    metadata: dict[str, object] = {
        "created_at": format_datetime_utc(message.created_at),
        "source_kind": message.source_kind,
        "source_id": message.source_id,
        "role": message.role,
        "kind": kind_label(message),
        "sequence_no": message.sequence_no,
        "visibility": _visibility_label(message),
        "current_inbound": current_inbound,
        "content_block_types": content_block_types(message),
        "content_digest": hashlib.sha256(content.encode("utf-8")).hexdigest(),
        "archived": archived,
    }
    for key in (
        "archived_reason",
        "archived_by_compaction_run_id",
        "compacted_segment_id",
        "archived_through_item_sequence_no",
        "summary_item_id",
    ):
        value = message.metadata.get(key)
        if value not in (None, "", {}, []):
            metadata[key] = value
    return ContextNodeSeed(
        node_id=f"session.item.{message.session_id}.{message.sequence_no}",
        parent_id=parent_id,
        owner="session",
        kind="session_item",
        title=f"{message.sequence_no}. {message.role}",
        summary=preview,
        content=content,
        state=ContextNodeState(
            collapsed=False,
            loaded=True,
            archived=archived,
            status="archived" if archived else "available",
            render_reason="archived_by_compaction" if archived else "",
        ),
        actions=_BASIC_ACTIONS,
        owner_ref=owner_ref,
        estimate=message_estimate(message, content),
        display_order=message.sequence_no,
        metadata=metadata,
    )


def current_inbound_sequence_no(
    messages: tuple[SessionItem, ...],
    *,
    current_run_id: str | None,
) -> int | None:
    if current_run_id is None:
        return None
    sequences = [
        message.sequence_no
        for message in messages
        if is_current_inbound_message(message, current_run_id=current_run_id)
    ]
    return min(sequences) if sequences else None


def is_current_inbound_message(
    message: SessionItem,
    *,
    current_run_id: str | None,
) -> bool:
    if current_run_id is None:
        return False
    return (
        message.role == "user"
        and message.source_kind == "orchestration_run"
        and message.source_id == current_run_id
    )


def _visibility_label(message: Any) -> str:
    if is_archived_transcript_entry(message):
        return "archived"
    return "default"
