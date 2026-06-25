from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.observation_event_projection import (
    observed_event_from_record,
)
from crxzipple.modules.operations.application.observation_models import (
    OperationsObservedEvent,
)
from crxzipple.modules.operations.application.read_models.tool_lifecycle_event_topics import (
    MAX_TOOL_EVENT_TOPICS,
    TOOL_DIRECT_EVENT_TOPICS,
    dedupe_topic_names,
    is_tool_event_topic,
    safe_list_event_topics,
)
from crxzipple.shared.time import coerce_utc_datetime

MAX_RECENT_TOOL_EVENTS = 240
RECENT_TOOL_TOPIC_LIMIT = 100


def recent_tool_events(
    *,
    operations_observation: Any | None,
    events_service: Any | None,
    definition_registry: Any | None,
    limit: int,
) -> tuple[OperationsObservedEvent, ...]:
    event_limit = max(int(limit), 1)
    return dedupe_tool_events(
        (
            *recent_tool_events_from_bus(
                events_service,
                definition_registry=definition_registry,
                limit=event_limit,
            ),
            *recent_tool_events_from_observation(
                operations_observation,
                limit=event_limit,
            ),
        ),
        limit=event_limit,
    )


def recent_tool_events_from_observation(
    observation: Any | None,
    *,
    limit: int,
) -> tuple[OperationsObservedEvent, ...]:
    if observation is None or not hasattr(observation, "get_module_observation"):
        return ()
    try:
        module_observation = observation.get_module_observation("tool")
    except Exception:
        return ()
    if module_observation is None:
        return ()
    recent_events = getattr(module_observation, "recent_events", ())
    return tuple(
        event
        for event in tuple(recent_events)[: max(int(limit), 1)]
        if isinstance(event, OperationsObservedEvent)
    )


def recent_tool_events_from_bus(
    events_service: Any | None,
    *,
    definition_registry: Any | None,
    limit: int,
) -> tuple[OperationsObservedEvent, ...]:
    if events_service is None:
        return ()
    topics = dedupe_topic_names(
        (
            *TOOL_DIRECT_EVENT_TOPICS,
            *(
                topic
                for topic in safe_list_event_topics(events_service)
                if is_tool_event_topic(topic)
            ),
        ),
    )[:MAX_TOOL_EVENT_TOPICS]
    read_recent = getattr(events_service, "read_recent_event_topic", None)
    if not callable(read_recent):
        return ()
    events: list[OperationsObservedEvent] = []
    topic_limit = min(
        max(RECENT_TOOL_TOPIC_LIMIT, int(limit)),
        MAX_RECENT_TOOL_EVENTS,
    )
    for topic in topics:
        try:
            records = tuple(read_recent(topic, limit=topic_limit) or ())
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
            if is_tool_observed_event(observed):
                events.append(observed)
    events.sort(key=lambda event: coerce_utc_datetime(event.occurred_at), reverse=True)
    return tuple(events[:MAX_RECENT_TOOL_EVENTS])


def is_tool_observed_event(event: OperationsObservedEvent) -> bool:
    owner = event.owner.strip().lower()
    module = event.module.strip().lower()
    event_name = event.event_name.strip().lower()
    return owner == "tool" or module == "tool" or event_name.startswith("tool.")


def dedupe_tool_events(
    events: tuple[OperationsObservedEvent, ...],
    *,
    limit: int,
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
    return tuple(result[: min(max(int(limit), 1), MAX_RECENT_TOOL_EVENTS)])

