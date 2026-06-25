from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.channels_formatting import (
    text,
)
from crxzipple.modules.operations.application.read_models.channels_models import (
    ChannelEventRecord,
)
from crxzipple.modules.orchestration.application import (
    turn_session_live_topic,
    turn_session_topic,
)


def connection_event_topics(bindings: tuple[Any, ...]) -> tuple[str, ...]:
    topics: set[str] = set()
    for binding in bindings:
        conversation_id = text(getattr(binding, "conversation_id", None), "")
        if not conversation_id:
            continue
        topics.add(turn_session_topic(conversation_id))
        topics.add(turn_session_live_topic(conversation_id))
    return tuple(sorted(topics))


def connection_binding_by_conversation(bindings: tuple[Any, ...]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for binding in bindings:
        conversation_id = text(getattr(binding, "conversation_id", None), "")
        if conversation_id:
            result[conversation_id] = binding
    return result


def event_matches_runtime(
    event: ChannelEventRecord,
    runtime_id: str,
    connection_bindings: tuple[Any, ...],
) -> bool:
    if event.runtime_id == runtime_id:
        return True
    connection_ids = {
        text(getattr(binding, "connection_id", None), "")
        for binding in connection_bindings
    }
    conversation_ids = {
        text(getattr(binding, "conversation_id", None), "")
        for binding in connection_bindings
    }
    return (
        bool(event.connection_id and event.connection_id in connection_ids)
        or bool(event.conversation_id and event.conversation_id in conversation_ids)
    )
