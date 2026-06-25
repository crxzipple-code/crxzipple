from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.observation_event_projection import (
    observed_event_from_record,
)
from crxzipple.modules.operations.application.observation_models import (
    OperationsObservedEvent,
)
from crxzipple.modules.operations.application.read_models.skills_common import text
from crxzipple.modules.skills.application.events import SKILL_OPERATION_EVENT_NAMES
from crxzipple.shared.time import coerce_utc_datetime

_MAX_RECENT_SKILL_EVENTS = 240
_RECENT_SKILL_TOPIC_LIMIT = 80
_SKILL_EVENT_TOPICS = tuple(
    f"events.named.{event_name}" for event_name in SKILL_OPERATION_EVENT_NAMES
)


def recent_skill_events(
    *,
    operations_observation: Any | None,
    events_service: Any | None,
    definition_registry: Any | None,
) -> tuple[OperationsObservedEvent, ...]:
    return dedupe_skill_events(
        (
            *recent_skill_events_from_bus(
                events_service,
                definition_registry=definition_registry,
            ),
            *recent_skill_events_from_observation(operations_observation),
        ),
    )


def recent_skill_events_from_observation(
    operations_observation: Any | None,
) -> tuple[OperationsObservedEvent, ...]:
    get_module_observation = getattr(operations_observation, "get_module_observation", None)
    if not callable(get_module_observation):
        return ()
    try:
        observation = get_module_observation("skills")
    except Exception:
        return ()
    return tuple(
        item
        for item in tuple(getattr(observation, "recent_events", ()) or ())
        if isinstance(item, OperationsObservedEvent)
    )


def recent_skill_events_from_bus(
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
    for topic in _SKILL_EVENT_TOPICS:
        try:
            records = tuple(read_recent(topic, limit=_RECENT_SKILL_TOPIC_LIMIT) or ())
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
            if is_skill_observed_event(observed):
                events.append(observed)
    events.sort(key=lambda event: coerce_utc_datetime(event.occurred_at), reverse=True)
    return tuple(events[:_MAX_RECENT_SKILL_EVENTS])


def is_skill_observed_event(event: OperationsObservedEvent) -> bool:
    owner = event.owner.strip().lower()
    module = event.module.strip().lower()
    event_name = event.event_name.strip().lower()
    return (
        owner in {"skills", "skill"}
        or module in {"skills", "skill"}
        or event_name.startswith("skills.")
        or event_name.startswith("skill.")
    )


def dedupe_skill_events(
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
    return tuple(result[:_MAX_RECENT_SKILL_EVENTS])


def latest_readiness_events_by_skill(
    events: tuple[OperationsObservedEvent, ...],
) -> dict[str, OperationsObservedEvent]:
    latest: dict[str, OperationsObservedEvent] = {}
    for event in sorted(
        events,
        key=lambda item: coerce_utc_datetime(item.occurred_at),
        reverse=True,
    ):
        if event.event_name != "skills.readiness.changed":
            continue
        skill = text(
            event.payload.get("skill")
            or event.payload.get("skill_name")
            or event.entity_id,
            "",
        )
        if not skill or skill in latest:
            continue
        latest[skill] = event
    return latest
