from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.observation_models import (
    OperationsObservedEvent,
)
from crxzipple.modules.operations.application.read_models.channels_formatting import (
    text,
)
from crxzipple.modules.operations.application.read_models.channels_models import (
    ChannelEventRecord,
)
from crxzipple.modules.operations.application.read_models.channels_payload_formatting import (
    short_json,
)
from crxzipple.modules.operations.application.read_models.routes import (
    workbench_trace_route,
)

RECENT_TOPIC_LIMIT = 40
MAX_EVENT_TOPICS = 180
MAX_RECENT_EVENTS = 240


def events_for_interaction(
    interaction: Any,
    events: tuple[ChannelEventRecord, ...],
) -> tuple[ChannelEventRecord, ...]:
    run_id = text(getattr(interaction, "run_id", None), "")
    session_key = text(getattr(interaction, "session_key", None), "")
    external_conversation_id = text(
        getattr(interaction, "external_conversation_id", None),
        "",
    )
    channel_type = text(getattr(interaction, "channel_type", None), "")
    return tuple(
        event
        for event in events
        if (
            bool(run_id and event.run_id == run_id)
            or bool(session_key and event.conversation_id == session_key)
            or bool(
                external_conversation_id
                and event.conversation_id == external_conversation_id
            )
            or (
                bool(channel_type and event.channel_type == channel_type)
                and bool(run_id and text(event.payload.get("run_id"), "") == run_id)
            )
        )
    )


def event_direction(event: ChannelEventRecord) -> str:
    topic = event.topic
    name = event.event_name.lower()
    if "dead_letter" in topic or "dead_letter" in name or "failed" in name:
        return "Dead Letter"
    if topic.startswith("turn.live."):
        return "Live"
    if topic.startswith("turn.session."):
        return "Observe"
    if ".broadcast." in topic:
        return "Broadcast"
    if ".connection." in topic and topic.endswith(".control"):
        return "Control"
    return "Other"


def is_dead_letter_event(event: ChannelEventRecord) -> bool:
    name = event.event_name.lower()
    topic = event.topic.lower()
    return "dead_letter" in name or "dead-letter" in name or "dead_letter" in topic


def event_status(
    observed: OperationsObservedEvent,
    payload: dict[str, Any],
) -> str:
    for key in ("status", "state", "result"):
        value = text(payload.get(key), "")
        if value:
            return value
    return observed.status


def failure_reason(event: ChannelEventRecord) -> str:
    for key in ("reason", "error", "error_code", "status"):
        value = text(event.payload.get(key), "")
        if value:
            return value
    if "dead_letter" in event.topic:
        return "dead_letter"
    return "unknown"


def event_search_text(event: ChannelEventRecord) -> str:
    values = (
        event.id,
        event.cursor,
        event.topic,
        event.event_name,
        event.status,
        event.channel_type or "",
        event.runtime_id or "",
        event.channel_account_id or "",
        event.connection_id or "",
        event.conversation_id or "",
        event.run_id or "",
        event.trace_id or "",
        short_json(event.payload, size=400),
    )
    return " ".join(values).lower()


def trace_route(event: ChannelEventRecord) -> str:
    if event.trace_id:
        return workbench_trace_route(event.trace_id)
    if event.run_id:
        return f"/workbench/runs/{event.run_id}"
    return "-"


def dedupe_events(
    events: tuple[ChannelEventRecord, ...],
) -> tuple[ChannelEventRecord, ...]:
    by_id: dict[str, ChannelEventRecord] = {}
    for event in sorted(events, key=lambda item: item.occurred_at):
        by_id[event.id] = event
    return tuple(
        sorted(by_id.values(), key=lambda item: item.occurred_at, reverse=True)
    )
