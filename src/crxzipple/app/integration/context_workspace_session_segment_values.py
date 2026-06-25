from __future__ import annotations

from crxzipple.app.integration.context_workspace_session_content_values import (
    optional_text,
)
from crxzipple.modules.session.domain import SessionInstance, SessionItem


def segment_messages(
    messages: tuple[SessionItem, ...],
    *,
    session_id: str,
    message_scope: str,
) -> tuple[SessionItem, ...]:
    return tuple(
        message
        for message in messages
        if message.session_id == session_id
        and matches_message_scope(
            message,
            message_scope=message_scope,
        )
    )


def matches_message_scope(
    message: object,
    *,
    message_scope: str,
) -> bool:
    if message_scope == "archived":
        return is_archived_transcript_entry(message)
    return True


def is_archived_transcript_entry(message: object) -> bool:
    metadata = getattr(message, "metadata", None)
    if not isinstance(metadata, dict):
        return False
    return (
        metadata.get("archived_reason") is not None
        or metadata.get("compacted_segment_id") is not None
    )


def is_session_instance_node_id(node_id: str) -> bool:
    return node_id == "session.instance.active" or node_id.startswith(
        "session.instance.closed.",
    )


def is_session_segments_root_node_id(node_id: str) -> bool:
    return node_id == "session.segments.active" or node_id.startswith(
        "session.segments.closed.",
    )


def is_session_segment_node_id(node_id: str) -> bool:
    return node_id == "session.segment.active" or node_id.startswith(
        "session.segment.compacted.",
    ) or node_id.startswith("session.segment.closed.")


def is_historical_segment_node_id(node_id: str) -> bool:
    return node_id.startswith("session.segment.compacted.") or node_id.startswith(
        "session.segment.closed.",
    )


def session_segments_root_id(instance: SessionInstance, *, active: bool) -> str:
    if active:
        return "session.segments.active"
    return f"session.segments.closed.{node_part(instance.id)}"


def historical_segment_kind(instance: SessionInstance) -> str:
    if segment_summary_text(instance.metadata) is not None:
        return "compacted"
    segment = instance.metadata.get("segment")
    if isinstance(segment, dict):
        kind = optional_text(segment.get("kind")) or optional_text(segment.get("status"))
        if kind == "compacted":
            return "compacted"
    return "closed"


def segment_summary_text(metadata: dict[str, object]) -> str | None:
    segment = metadata.get("segment")
    if not isinstance(segment, dict):
        return None
    return optional_text(segment.get("summary_text"))


def chunks(
    messages: tuple[SessionItem, ...],
    size: int,
) -> tuple[tuple[SessionItem, ...], ...]:
    chunk_size = max(int(size), 1)
    return tuple(
        messages[index : index + chunk_size]
        for index in range(0, len(messages), chunk_size)
    )


def node_part(value: str) -> str:
    return "".join(
        char if char.isalnum() or char in {"-", "_"} else "_"
        for char in value
    )
