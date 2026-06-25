from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from crxzipple.modules.operations.application.read_models.events_filters import (
    filter_events,
)
from crxzipple.modules.operations.application.read_models.events_models import (
    EventsOperationsQuery,
)
from crxzipple.modules.operations.application.read_models.events_page_projection import (
    recent_events_limit,
    uncovered_events,
)
from crxzipple.modules.operations.application.read_models.events_recent_state import (
    dead_letter_events,
    recent_event_summaries,
    recent_event_summaries_from_observation,
)


@dataclass(frozen=True, slots=True)
class EventsPageRecentFacts:
    all_recent_events: tuple[dict[str, Any], ...]
    filtered_events: tuple[dict[str, Any], ...]
    visible_events: tuple[dict[str, Any], ...]
    uncovered_events: tuple[dict[str, Any], ...]
    dead_letter_events: tuple[dict[str, Any], ...]


def collect_events_page_recent_facts(
    *,
    events_service: Any | None,
    event_definition_registry: Any | None,
    event_contract_registry: Any | None,
    operations_observation: Any | None,
    query: EventsOperationsQuery,
    recent_scan_topics: tuple[str, ...],
) -> EventsPageRecentFacts:
    limit = recent_events_limit(query)
    all_recent_events = tuple(
        recent_event_summaries_from_observation(
            operations_observation,
            definition_registry=event_definition_registry,
            contract_registry=event_contract_registry,
            limit=limit,
        ),
    )
    if not all_recent_events:
        all_recent_events = tuple(
            recent_event_summaries(
                events_service,
                topics=recent_scan_topics,
                definition_registry=event_definition_registry,
                contract_registry=event_contract_registry,
                limit=limit,
            ),
        )
    filtered_events = tuple(filter_events(all_recent_events, query))
    return EventsPageRecentFacts(
        all_recent_events=all_recent_events,
        filtered_events=filtered_events,
        visible_events=filtered_events[query.offset : query.offset + query.limit],
        uncovered_events=uncovered_events(all_recent_events),
        dead_letter_events=tuple(dead_letter_events(all_recent_events)),
    )
