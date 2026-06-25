from __future__ import annotations

from typing import Any

from crxzipple.modules.access.application.events import ACCESS_OPERATION_EVENT_NAMES
from crxzipple.modules.operations.application.observation_models import OperationsObservedEvent
from crxzipple.modules.operations.application.observation_event_projection import observed_event_from_record
from crxzipple.modules.operations.application.read_models.access_values import (
    short,
    text,
)
from crxzipple.shared.domain.events import named_event_topic
from crxzipple.shared.time import coerce_utc_datetime

MAX_RECENT_ACCESS_EVENTS = 240
RECENT_ACCESS_TOPIC_LIMIT = 80
ACCESS_EVENT_TOPICS = tuple(
    named_event_topic(event_name) for event_name in ACCESS_OPERATION_EVENT_NAMES
)


def recent_access_events(
    *,
    operations_observation: Any | None,
    events_service: Any | None,
    definition_registry: Any | None,
) -> tuple[OperationsObservedEvent, ...]:
    return dedupe_events(
        (
            *recent_access_events_from_bus(
                events_service,
                definition_registry=definition_registry,
            ),
            *recent_access_events_from_observation(operations_observation),
        )
    )


def recent_access_events_from_observation(
    operations_observation: Any | None,
) -> tuple[OperationsObservedEvent, ...]:
    get_module_observation = getattr(operations_observation, "get_module_observation", None)
    if not callable(get_module_observation):
        return ()
    try:
        observation = get_module_observation("access")
    except Exception:
        return ()
    return tuple(
        item
        for item in tuple(getattr(observation, "recent_events", ()) or ())
        if isinstance(item, OperationsObservedEvent)
    )


def recent_access_events_from_bus(
    events_service: Any | None,
    *,
    definition_registry: Any | None,
) -> tuple[OperationsObservedEvent, ...]:
    if events_service is None:
        return ()
    read_recent = getattr(events_service, "read_recent_event_topic", None)
    if not callable(read_recent):
        return ()
    events: list[OperationsObservedEvent] = []
    for topic in ACCESS_EVENT_TOPICS:
        try:
            records = tuple(
                read_recent(topic, limit=RECENT_ACCESS_TOPIC_LIMIT) or (),
            )
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
            if is_access_observed_event(observed):
                events.append(observed)
    events.sort(key=lambda event: coerce_utc_datetime(event.occurred_at), reverse=True)
    return tuple(events[:MAX_RECENT_ACCESS_EVENTS])


def is_access_observed_event(event: OperationsObservedEvent) -> bool:
    owner = event.owner.strip().lower()
    module = event.module.strip().lower()
    event_name = event.event_name.strip().lower()
    return (
        owner == "access"
        or module == "access"
        or event_name.startswith("access.")
    )


def dedupe_events(
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
    return tuple(result[:MAX_RECENT_ACCESS_EVENTS])


def event_details(payload: dict[str, Any]) -> str:
    for key in ("reason", "message", "summary", "error_message", "requirement", "status"):
        value = payload.get(key)
        if value is not None and text(value, ""):
            return short(value, 120)
    return "-"


def short_event_name(event_name: str) -> str:
    return event_name.removeprefix("access.")


def event_tone(event: OperationsObservedEvent) -> str:
    if event.level == "error" or event.status in {"failed", "error"}:
        return "danger"
    if event.level == "warning":
        return "warning"
    return "success" if event.status in {"ready", "success", "observed"} else "neutral"
