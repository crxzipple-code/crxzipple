from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from crxzipple.modules.operations.application.read_models.channels_event_helpers import (
    dedupe_events,
    is_dead_letter_event,
)
from crxzipple.modules.operations.application.read_models.channels_events import (
    channel_types as _channel_types,
    dead_letter_events as _dead_letter_events,
    recent_channel_events as _recent_channel_events,
    recent_channel_events_from_observation as _recent_channel_events_from_observation,
)
from crxzipple.modules.operations.application.read_models.channels_health import (
    health as _health,
)
from crxzipple.modules.operations.application.read_models.channels_models import (
    ChannelsOperationsQuery,
)
from crxzipple.modules.operations.application.read_models.channels_page_filters import (
    filter_events,
    filter_interactions,
    filter_runtime_records,
    normalize_channels_query,
)
from crxzipple.modules.operations.application.read_models.channels_runtime_records import (
    runtime_records as _runtime_records,
)
from crxzipple.modules.operations.application.read_models.channels_safe_access import (
    safe_tuple,
)
from crxzipple.modules.operations.application.read_models.event_buckets import (
    recent_event_buckets,
)


@dataclass(frozen=True, slots=True)
class ChannelsPageData:
    query: ChannelsOperationsQuery
    now: datetime
    profiles: tuple[Any, ...]
    runtimes: tuple[Any, ...]
    account_bindings: tuple[Any, ...]
    connection_bindings: tuple[Any, ...]
    interactions: tuple[Any, ...]
    dead_letter_events: tuple[Any, ...]
    event_buckets: tuple[Any, ...]
    channel_events: tuple[Any, ...]
    runtime_records: tuple[Any, ...]
    filtered_runtime_records: tuple[Any, ...]
    filtered_interactions: tuple[Any, ...]
    visible_interactions: tuple[Any, ...]
    filtered_events: tuple[Any, ...]
    visible_events: tuple[Any, ...]
    filtered_dead_letters: tuple[Any, ...]
    health: str


def build_channels_page_data(
    *,
    channel_profile_service: Any | None,
    channel_runtime_manager: Any | None,
    channel_interaction_service: Any | None = None,
    events_service: Any | None = None,
    event_definition_registry: Any | None = None,
    operations_observation: Any | None = None,
    query: ChannelsOperationsQuery | None = None,
) -> ChannelsPageData:
    normalized_query = normalize_channels_query(query)
    now = datetime.now(timezone.utc)
    profiles = safe_tuple(channel_profile_service, "list_profiles")
    runtimes = safe_tuple(channel_runtime_manager, "list_runtimes", channel_type=None)
    account_bindings = safe_tuple(channel_runtime_manager, "list_account_bindings")
    connection_bindings = safe_tuple(
        channel_runtime_manager,
        "list_connection_bindings",
    )
    interactions = safe_tuple(channel_interaction_service, "list_interactions")
    channel_types = _channel_types(
        profiles=profiles,
        runtimes=runtimes,
        account_bindings=account_bindings,
        connection_bindings=connection_bindings,
        interactions=interactions,
        events_service=events_service,
    )
    observed_events = _recent_channel_events_from_observation(
        operations_observation,
        connection_bindings=connection_bindings,
    )
    if observed_events:
        dead_letter_events = tuple(
            event for event in observed_events if is_dead_letter_event(event)
        )
        recent_events = observed_events
    else:
        dead_letter_events = _dead_letter_events(
            events_service,
            channel_types=channel_types,
            runtimes=runtimes,
            definition_registry=event_definition_registry,
        )
        recent_events = _recent_channel_events(
            events_service,
            connection_bindings=connection_bindings,
            definition_registry=event_definition_registry,
        )
    event_buckets = recent_event_buckets(
        operations_observation,
        module="channels",
        hours=24,
        limit=1000,
    )
    channel_events = dedupe_events((*dead_letter_events, *recent_events))
    runtime_records = _runtime_records(
        runtimes=runtimes,
        account_bindings=account_bindings,
        connection_bindings=connection_bindings,
        events=channel_events,
        now=now,
    )
    filtered_runtime_records = filter_runtime_records(
        runtime_records,
        normalized_query,
    )
    filtered_interactions = filter_interactions(interactions, normalized_query)
    visible_interactions = filtered_interactions[
        normalized_query.offset : normalized_query.offset + normalized_query.limit
    ]
    filtered_events = filter_events(channel_events, normalized_query)
    visible_events = filtered_events[
        normalized_query.offset : normalized_query.offset + normalized_query.limit
    ]
    filtered_dead_letters = filter_events(dead_letter_events, normalized_query)
    health = _health(
        service_available=channel_runtime_manager is not None,
        runtimes=runtime_records,
        profiles=profiles,
        dead_letters=dead_letter_events,
        interactions=interactions,
        now=now,
    )
    return ChannelsPageData(
        query=normalized_query,
        now=now,
        profiles=profiles,
        runtimes=runtimes,
        account_bindings=account_bindings,
        connection_bindings=connection_bindings,
        interactions=interactions,
        dead_letter_events=dead_letter_events,
        event_buckets=event_buckets,
        channel_events=channel_events,
        runtime_records=runtime_records,
        filtered_runtime_records=filtered_runtime_records,
        filtered_interactions=filtered_interactions,
        visible_interactions=visible_interactions,
        filtered_events=filtered_events,
        visible_events=visible_events,
        filtered_dead_letters=filtered_dead_letters,
        health=health,
    )
