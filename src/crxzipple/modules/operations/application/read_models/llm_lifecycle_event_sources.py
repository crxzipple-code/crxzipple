from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.observation_models import (
    OperationsObservedEvent,
)
from crxzipple.modules.operations.application.read_models.llm_lifecycle_event_bus import (
    MAX_RECENT_LLM_EVENTS,
    recent_llm_events_from_bus,
    recent_resolver_events_from_bus,
)
from crxzipple.modules.operations.application.read_models.ports_runtime import (
    OperationsObservationReadPort,
)
from crxzipple.shared.time import coerce_utc_datetime

def recent_llm_events(
    *,
    operations_observation: OperationsObservationReadPort | None,
    events_service: Any | None,
    definition_registry: Any | None,
    limit: int,
) -> tuple[OperationsObservedEvent, ...]:
    event_limit = max(int(limit), 1)
    return _dedupe_llm_events(
        (
            *recent_llm_events_from_bus(
                events_service,
                definition_registry=definition_registry,
                limit=event_limit,
            ),
            *_recent_llm_events_from_observation(
                operations_observation,
                limit=event_limit,
            ),
        ),
        limit=event_limit,
    )


def recent_resolver_events(
    *,
    operations_observation: OperationsObservationReadPort | None,
    events_service: Any | None,
    definition_registry: Any | None,
    limit: int,
) -> tuple[OperationsObservedEvent, ...]:
    event_limit = max(int(limit), 1)
    return _dedupe_llm_events(
        (
            *recent_resolver_events_from_bus(
                events_service,
                definition_registry=definition_registry,
                limit=event_limit,
            ),
            *_recent_resolver_events_from_observation(
                operations_observation,
                limit=event_limit,
            ),
        ),
        limit=event_limit,
    )


def _recent_llm_events_from_observation(
    operations_observation: OperationsObservationReadPort | None,
    *,
    limit: int,
) -> tuple[OperationsObservedEvent, ...]:
    if operations_observation is None:
        return ()
    try:
        observation = operations_observation.get_module_observation("llm")
    except Exception:
        return ()
    if observation is None:
        return ()
    recent_events = getattr(observation, "recent_events", ())
    return tuple(
        event for event in recent_events if isinstance(event, OperationsObservedEvent)
    )[:limit]


def _recent_resolver_events_from_observation(
    operations_observation: OperationsObservationReadPort | None,
    *,
    limit: int,
) -> tuple[OperationsObservedEvent, ...]:
    if operations_observation is None:
        return ()
    events: list[OperationsObservedEvent] = []
    for module in ("orchestration", "llm"):
        try:
            observation = operations_observation.get_module_observation(module)
        except Exception:
            continue
        if observation is None:
            continue
        events.extend(
            event
            for event in getattr(observation, "recent_events", ())
            if isinstance(event, OperationsObservedEvent)
            and event.event_name == "orchestration.llm_resolved"
        )
    return tuple(sorted(events, key=lambda event: event.occurred_at, reverse=True))[
        :limit
    ]


def _dedupe_llm_events(
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
    return tuple(result[: min(max(int(limit), 1), MAX_RECENT_LLM_EVENTS)])
