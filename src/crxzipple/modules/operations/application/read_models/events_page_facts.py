from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from crxzipple.modules.operations.application.read_models.event_buckets import (
    recent_event_buckets,
)
from crxzipple.modules.operations.application.read_models.events_topic_rows import (
    topic_rows as _topic_rows,
    uncovered_topics as _uncovered_topics,
)
from crxzipple.modules.operations.application.read_models.events_filters import (
    normalize_events_query as _normalize_query,
)
from crxzipple.modules.operations.application.read_models.events_models import (
    EventsOperationsQuery,
)
from crxzipple.modules.operations.application.read_models.events_page_recent_facts import (
    collect_events_page_recent_facts,
)
from crxzipple.modules.operations.application.read_models.events_page_runtime_facts import (
    collect_events_page_runtime_facts,
)
from crxzipple.modules.operations.application.read_models.events_page_sources import (
    collect_events_page_sources,
)
from crxzipple.modules.operations.application.read_models.events_page_projection import (
    events_health_projection,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableRowModel,
)


@dataclass(frozen=True, slots=True)
class EventsPageFacts:
    now: datetime
    query: EventsOperationsQuery
    topic_contracts: tuple[Any, ...]
    route_contracts: tuple[Any, ...]
    definitions: tuple[Any, ...]
    surfaces: tuple[Any, ...]
    observer_definitions: tuple[Any, ...]
    live_topics: tuple[str, ...]
    subscription_states: tuple[dict[str, Any], ...]
    observer_states: tuple[dict[str, Any], ...]
    observer_runtime_states: tuple[dict[str, Any], ...]
    event_buckets: tuple[dict[str, Any], ...]
    all_recent_events: tuple[dict[str, Any], ...]
    filtered_events: tuple[dict[str, Any], ...]
    visible_events: tuple[dict[str, Any], ...]
    live_topic_rows: tuple[OperationsTableRowModel, ...]
    uncovered_topics: tuple[str, ...]
    uncovered_events: tuple[dict[str, Any], ...]
    dead_letter_events: tuple[dict[str, Any], ...]
    lagging_count: int
    stuck_count: int
    observer_lagging_count: int
    observer_stuck_count: int
    observer_runtime_lagging_count: int
    observer_runtime_stuck_count: int
    health: str


def collect_events_page_facts(
    *,
    events_service: Any | None,
    event_contract_registry: Any | None,
    event_definition_registry: Any | None,
    operations_observation: Any | None,
    operations_observer_runtime: Any | None,
    query: EventsOperationsQuery | None,
) -> EventsPageFacts:
    normalized_query = _normalize_query(query)
    now = datetime.now(timezone.utc)
    sources = collect_events_page_sources(
        events_service=events_service,
        event_contract_registry=event_contract_registry,
        event_definition_registry=event_definition_registry,
        operations_observer_runtime=operations_observer_runtime,
        topic_prefix=normalized_query.topic_prefix,
    )
    runtime_facts = collect_events_page_runtime_facts(
        events_service=events_service,
        event_contract_registry=event_contract_registry,
        operations_observation=operations_observation,
        operations_observer_runtime=operations_observer_runtime,
        sources=sources,
        now=now,
    )
    event_buckets = recent_event_buckets(
        operations_observation,
        hours=24,
        limit=2000,
    )
    recent_facts = collect_events_page_recent_facts(
        events_service=events_service,
        event_definition_registry=event_definition_registry,
        event_contract_registry=event_contract_registry,
        operations_observation=operations_observation,
        query=normalized_query,
        recent_scan_topics=runtime_facts.selected_topics.recent_scan_topics,
    )
    live_topic_rows = _topic_rows(
        runtime_facts.selected_topics.visible_topics,
        latest_cursors=runtime_facts.latest_cursors,
        subscription_states=runtime_facts.subscription_states,
        recent_events=recent_facts.all_recent_events,
        registry=event_contract_registry,
    )
    uncovered_topics = _uncovered_topics(
        sources.live_topics,
        registry=event_contract_registry,
    )
    health_projection = events_health_projection(
        events_service_available=events_service is not None,
        subscription_states=runtime_facts.subscription_states,
        observer_states=runtime_facts.observer_states,
        observer_runtime_states=runtime_facts.observer_runtime_states,
        dead_letter_count=len(recent_facts.dead_letter_events),
        uncovered_topic_count=len(uncovered_topics),
    )

    return EventsPageFacts(
        now=now,
        query=normalized_query,
        topic_contracts=sources.topic_contracts,
        route_contracts=sources.route_contracts,
        definitions=sources.definitions,
        surfaces=sources.surfaces,
        observer_definitions=sources.observer_definitions,
        live_topics=sources.live_topics,
        subscription_states=runtime_facts.subscription_states,
        observer_states=runtime_facts.observer_states,
        observer_runtime_states=runtime_facts.observer_runtime_states,
        event_buckets=event_buckets,
        all_recent_events=recent_facts.all_recent_events,
        filtered_events=recent_facts.filtered_events,
        visible_events=recent_facts.visible_events,
        live_topic_rows=live_topic_rows,
        uncovered_topics=uncovered_topics,
        uncovered_events=recent_facts.uncovered_events,
        dead_letter_events=recent_facts.dead_letter_events,
        lagging_count=health_projection.lagging_count,
        stuck_count=health_projection.stuck_count,
        observer_lagging_count=health_projection.observer_lagging_count,
        observer_stuck_count=health_projection.observer_stuck_count,
        observer_runtime_lagging_count=(
            health_projection.observer_runtime_lagging_count
        ),
        observer_runtime_stuck_count=health_projection.observer_runtime_stuck_count,
        health=health_projection.health,
    )
