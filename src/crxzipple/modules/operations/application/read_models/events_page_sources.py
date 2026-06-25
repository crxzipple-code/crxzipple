from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from crxzipple.modules.operations.application.read_models.events_page_projection import (
    safe_list,
)
from crxzipple.modules.operations.application.read_models.events_subscription_state import (
    safe_observer_subscriptions,
    safe_subscription_cursors,
)
from crxzipple.modules.operations.application.read_models.events_topic_state import (
    list_live_topics,
)


@dataclass(frozen=True, slots=True)
class EventsPageSources:
    topic_contracts: tuple[Any, ...]
    route_contracts: tuple[Any, ...]
    definitions: tuple[Any, ...]
    surfaces: tuple[Any, ...]
    observer_definitions: tuple[Any, ...]
    observer_subscriptions: tuple[Any, ...]
    live_topics: tuple[str, ...]
    subscription_cursors: tuple[Any, ...]


def collect_events_page_sources(
    *,
    events_service: Any | None,
    event_contract_registry: Any | None,
    event_definition_registry: Any | None,
    operations_observer_runtime: Any | None,
    topic_prefix: str,
) -> EventsPageSources:
    return EventsPageSources(
        topic_contracts=safe_list(
            event_contract_registry,
            "list_topic_contracts",
        ),
        route_contracts=safe_list(
            event_contract_registry,
            "list_route_contracts",
        ),
        definitions=safe_list(
            event_definition_registry,
            "list_definitions",
        ),
        surfaces=safe_list(event_definition_registry, "list_surfaces"),
        observer_definitions=safe_list(
            event_definition_registry,
            "list_observers",
        ),
        observer_subscriptions=safe_observer_subscriptions(
            operations_observer_runtime,
        ),
        live_topics=list_live_topics(
            events_service,
            topic_prefix=topic_prefix,
        ),
        subscription_cursors=safe_subscription_cursors(events_service),
    )
