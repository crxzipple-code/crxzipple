from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.observation_models import OperationsObservedEvent
from crxzipple.modules.operations.application.observation_event_projection import observed_event_from_record
from crxzipple.modules.operations.application.read_models.memory_values import (
    short,
    text,
)
from crxzipple.shared.time import coerce_utc_datetime

MAX_MEMORY_EVENT_TOPICS = 160
MAX_RECENT_MEMORY_EVENTS = 240
RECENT_MEMORY_TOPIC_LIMIT = 80


def recent_memory_events(
    *,
    operations_observation: Any | None,
    events_service: Any | None,
    definition_registry: Any | None,
) -> tuple[OperationsObservedEvent, ...]:
    return dedupe_memory_events(
        (
            *recent_memory_events_from_bus(
                events_service,
                definition_registry=definition_registry,
            ),
            *recent_memory_events_from_observation(operations_observation),
        )
    )


def recent_memory_events_from_observation(
    operations_observation: Any | None,
) -> tuple[OperationsObservedEvent, ...]:
    get_module_observation = getattr(operations_observation, "get_module_observation", None)
    if not callable(get_module_observation):
        return ()
    try:
        observation = get_module_observation("memory")
    except Exception:
        return ()
    return tuple(
        item
        for item in tuple(getattr(observation, "recent_events", ()) or ())
        if isinstance(item, OperationsObservedEvent)
    )


def recent_memory_events_from_bus(
    events_service: Any | None,
    *,
    definition_registry: Any | None,
) -> tuple[OperationsObservedEvent, ...]:
    if events_service is None:
        return ()
    topics = tuple(
        topic
        for topic in safe_list_event_topics(events_service)
        if is_memory_event_topic(topic)
    )[:MAX_MEMORY_EVENT_TOPICS]
    read_recent = getattr(events_service, "read_recent_event_topic", None)
    if not callable(read_recent):
        return ()
    events: list[OperationsObservedEvent] = []
    for topic in topics:
        try:
            records = tuple(read_recent(topic, limit=RECENT_MEMORY_TOPIC_LIMIT) or ())
        except Exception:
            continue
        for record in records:
            try:
                observed = observed_event_from_record(
                    record,
                    definition_registry=definition_registry,
                )
            except Exception:
                continue
            if is_memory_observed_event(observed):
                events.append(observed)
    events.sort(key=lambda event: coerce_utc_datetime(event.occurred_at), reverse=True)
    return tuple(events[:MAX_RECENT_MEMORY_EVENTS])


def safe_list_event_topics(events_service: Any) -> tuple[str, ...]:
    list_topics = getattr(events_service, "list_event_topics", None)
    if not callable(list_topics):
        return ()
    try:
        return tuple(str(topic) for topic in list_topics() or () if str(topic))
    except Exception:
        return ()


def is_memory_event_topic(topic: str) -> bool:
    normalized = topic.strip().lower()
    return (
        normalized.startswith("memory.")
        or normalized.startswith("events.named.memory.")
    )


def is_memory_observed_event(event: OperationsObservedEvent) -> bool:
    owner = event.owner.strip().lower()
    module = event.module.strip().lower()
    event_name = event.event_name.strip().lower()
    return owner == "memory" or module == "memory" or event_name.startswith("memory.")


def dedupe_memory_events(
    events: tuple[OperationsObservedEvent, ...],
) -> tuple[OperationsObservedEvent, ...]:
    result: list[OperationsObservedEvent] = []
    seen: set[tuple[str, str]] = set()
    for event in sorted(
        events,
        key=lambda item: coerce_utc_datetime(item.occurred_at),
        reverse=True,
    ):
        key = (event.topic, event.cursor or event.id)
        if key in seen:
            continue
        seen.add(key)
        result.append(event)
    return tuple(result[:MAX_RECENT_MEMORY_EVENTS])


def credential_readiness_blocked(
    events: tuple[OperationsObservedEvent, ...],
) -> bool:
    readiness_events = tuple(
        event
        for event in events
        if event.event_name.startswith("memory.engine.readiness_")
    )
    if not readiness_events:
        return False
    latest = max(readiness_events, key=lambda event: coerce_utc_datetime(event.occurred_at))
    status = text(
        latest.payload.get("readiness_status")
        or latest.status,
        "",
    ).lower()
    requires_credentials = bool(latest.payload.get("requires_credentials"))
    if latest.event_name == "memory.engine.readiness_failed":
        return True
    return requires_credentials and status not in {"ready", "succeeded", "observed"}


def event_details(payload: dict[str, Any]) -> str:
    for key in ("reason", "message", "summary", "error_message", "query", "path", "status"):
        value = payload.get(key)
        if value is not None and text(value, ""):
            return short(value, 120)
    return "-"


def short_event_name(event_name: str) -> str:
    return event_name.removeprefix("memory.")


def event_tone(event: OperationsObservedEvent) -> str:
    if event.level == "error" or event.status in {"failed", "error"}:
        return "danger"
    if event.level == "warning":
        return "warning"
    return "success" if event.status in {"ready", "success", "observed"} else "neutral"
