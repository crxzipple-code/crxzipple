from __future__ import annotations

from typing import Any

from crxzipple.shared.event_contracts import (
    TOOL_CLI_EVENT_NAMES,
    TOOL_FUNCTION_EVENT_NAMES,
    TOOL_SOURCE_EVENT_NAMES,
)

MAX_TOOL_EVENT_TOPICS = 200

TOOL_DIRECT_EVENT_TOPICS = (
    "events.named.tool.run.created",
    "events.named.tool.run.queued",
    "events.named.tool.run.dispatching",
    "events.named.tool.run.started",
    "events.named.tool.run.heartbeated",
    "events.named.tool.run.succeeded",
    "events.named.tool.run.failed",
    "events.named.tool.run.requeued",
    "events.named.tool.run.cancel_requested",
    "events.named.tool.run.cancelled",
    "events.named.tool.run.timed_out",
    "events.named.tool.assignment.created",
    "events.named.tool.assignment.started",
    "events.named.tool.assignment.heartbeated",
    "events.named.tool.assignment.succeeded",
    "events.named.tool.assignment.failed",
    "events.named.tool.assignment.cancelled",
    "events.named.tool.assignment.expired",
    "events.named.tool.worker.registered",
    "events.named.tool.worker.capabilities_updated",
    "events.named.tool.worker.recovered",
    "events.named.tool.worker.pruned",
    "events.named.tool.worker.stale",
    "events.named.tool.enabled",
    "events.named.tool.disabled",
    "events.named.tool.source.registered",
    "events.named.tool.source.updated",
    "events.named.tool.source.discovery_started",
    "events.named.tool.source.discovery_succeeded",
    "events.named.tool.source.discovery_failed",
    "events.named.tool.function.upserted",
    "events.named.tool.function.deprecated",
    "events.named.tool.function.deleted",
    *(f"events.named.{event_name}" for event_name in TOOL_SOURCE_EVENT_NAMES),
    *(f"events.named.{event_name}" for event_name in TOOL_FUNCTION_EVENT_NAMES),
    *(f"events.named.{event_name}" for event_name in TOOL_CLI_EVENT_NAMES),
    "tool.run.created",
    "tool.run.queued",
    "tool.run.dispatching",
    "tool.run.started",
    "tool.run.heartbeated",
    "tool.run.succeeded",
    "tool.run.failed",
    "tool.run.requeued",
    "tool.run.cancel_requested",
    "tool.run.cancelled",
    "tool.run.timed_out",
    "tool.assignment.created",
    "tool.assignment.started",
    "tool.assignment.heartbeated",
    "tool.assignment.succeeded",
    "tool.assignment.failed",
    "tool.assignment.cancelled",
    "tool.assignment.expired",
    "tool.worker.registered",
    "tool.worker.capabilities_updated",
    "tool.worker.recovered",
    "tool.worker.pruned",
    "tool.worker.stale",
    "tool.enabled",
    "tool.disabled",
    *TOOL_SOURCE_EVENT_NAMES,
    *TOOL_FUNCTION_EVENT_NAMES,
    *TOOL_CLI_EVENT_NAMES,
)


def safe_list_event_topics(events_service: Any) -> tuple[str, ...]:
    list_topics = getattr(events_service, "list_event_topics", None)
    if not callable(list_topics):
        return ()
    try:
        return tuple(str(topic) for topic in list_topics() or () if str(topic))
    except Exception:
        return ()


def is_tool_event_topic(topic: str) -> bool:
    normalized = topic.strip().lower()
    return normalized.startswith("tool.") or normalized.startswith("events.named.tool.")


def dedupe_topic_names(values: tuple[str, ...]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip()
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return tuple(result)
