from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from crxzipple.modules.operations.application.read_models.events_observer_runtime_state import (
    observer_runtime_states,
)
from crxzipple.modules.operations.application.read_models.events_page_projection import (
    EventsTopicSelection,
    source_topics_from,
    topic_selection,
)
from crxzipple.modules.operations.application.read_models.events_page_sources import (
    EventsPageSources,
)
from crxzipple.modules.operations.application.read_models.events_subscription_state import (
    observer_subscription_states,
    subscription_states,
)
from crxzipple.modules.operations.application.read_models.events_topic_state import (
    safe_snapshot,
)

_MAX_TOPIC_ROWS = 300
_MAX_RECENT_TOPIC_SCAN = 300


@dataclass(frozen=True, slots=True)
class EventsPageRuntimeFacts:
    selected_topics: EventsTopicSelection
    latest_cursors: dict[str, str | None]
    subscription_states: tuple[dict[str, Any], ...]
    observer_states: tuple[dict[str, Any], ...]
    observer_runtime_states: tuple[dict[str, Any], ...]


def collect_events_page_runtime_facts(
    *,
    events_service: Any | None,
    event_contract_registry: Any | None,
    operations_observation: Any | None,
    operations_observer_runtime: Any | None,
    sources: EventsPageSources,
    now: datetime,
) -> EventsPageRuntimeFacts:
    selected_topics = topic_selection(
        live_topics=sources.live_topics,
        source_topics=source_topics_from(
            sources.subscription_cursors,
            sources.observer_subscriptions,
        ),
        max_topic_rows=_MAX_TOPIC_ROWS,
        max_recent_topic_scan=_MAX_RECENT_TOPIC_SCAN,
    )
    latest_cursors = {
        topic: safe_snapshot(events_service, topic)
        for topic in selected_topics.snapshot_topics
    }
    subscription_state_rows = subscription_states(
        sources.subscription_cursors,
        latest_cursors=latest_cursors,
        now=now,
        registry=event_contract_registry,
    )
    observer_state_rows = observer_subscription_states(
        sources.observer_subscriptions,
        subscription_cursors=sources.subscription_cursors,
        latest_cursors=latest_cursors,
        now=now,
        registry=event_contract_registry,
    )
    return EventsPageRuntimeFacts(
        selected_topics=selected_topics,
        latest_cursors=latest_cursors,
        subscription_states=subscription_state_rows,
        observer_states=observer_state_rows,
        observer_runtime_states=observer_runtime_states(
            operations_observation,
            runtime=operations_observer_runtime,
            now=now,
        ),
    )
