from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.observation_event_projection import (
    observed_event_from_record,
)
from crxzipple.modules.operations.application.observation_models import (
    OperationsObservedEvent,
)
from crxzipple.modules.operations.application.read_models.daemon_event_filters import (
    daemon_event_topics,
    dedupe_daemon_events,
    is_daemon_observed_event,
)
from crxzipple.shared.time import coerce_utc_datetime

_MAX_DAEMON_EVENT_TOPICS = 160
_MAX_RECENT_DAEMON_EVENTS = 160
_RECENT_DAEMON_TOPIC_LIMIT = 80


def recent_daemon_events(
    *,
    operations_observation: Any | None,
    events_service: Any | None,
    definition_registry: Any | None,
) -> tuple[OperationsObservedEvent, ...]:
    return dedupe_daemon_events(
        (
            *_recent_daemon_events_from_bus(
                events_service,
                definition_registry=definition_registry,
            ),
            *_recent_daemon_events_from_observation(operations_observation),
        ),
        limit=_MAX_RECENT_DAEMON_EVENTS,
    )


def _recent_daemon_events_from_observation(
    operations_observation: Any | None,
) -> tuple[OperationsObservedEvent, ...]:
    get_module_observation = getattr(operations_observation, "get_module_observation", None)
    if not callable(get_module_observation):
        return ()
    try:
        observation = get_module_observation("daemon")
    except Exception:
        return ()
    recent_events = tuple(getattr(observation, "recent_events", ()) or ())
    return tuple(
        item
        for item in recent_events
        if isinstance(item, OperationsObservedEvent)
    )


def _recent_daemon_events_from_bus(
    events_service: Any | None,
    *,
    definition_registry: Any | None,
) -> tuple[OperationsObservedEvent, ...]:
    if events_service is None:
        return ()
    topics = daemon_event_topics(_safe_list_event_topics(events_service))[
        :_MAX_DAEMON_EVENT_TOPICS
    ]
    read_recent = getattr(events_service, "read_recent_event_topic", None)
    if not callable(read_recent):
        return ()
    events: list[OperationsObservedEvent] = []
    for topic in topics:
        try:
            records = tuple(read_recent(topic, limit=_RECENT_DAEMON_TOPIC_LIMIT) or ())
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
            if is_daemon_observed_event(observed):
                events.append(observed)
    events.sort(key=lambda event: coerce_utc_datetime(event.occurred_at), reverse=True)
    return tuple(events[:_MAX_RECENT_DAEMON_EVENTS])


def _safe_list_event_topics(events_service: Any) -> tuple[str, ...]:
    list_topics = getattr(events_service, "list_event_topics", None)
    if not callable(list_topics):
        return ()
    try:
        return tuple(str(topic) for topic in list_topics() or () if str(topic))
    except Exception:
        return ()

