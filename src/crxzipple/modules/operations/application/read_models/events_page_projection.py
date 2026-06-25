from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from crxzipple.modules.operations.application.read_models.events_models import (
    EventsOperationsQuery,
)
from crxzipple.modules.operations.application.read_models.events_topic_state import (
    prioritized_topics,
)


@dataclass(frozen=True, slots=True)
class EventsTopicSelection:
    visible_topics: tuple[str, ...]
    recent_scan_topics: tuple[str, ...]
    snapshot_topics: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EventsHealthProjection:
    lagging_count: int
    stuck_count: int
    observer_lagging_count: int
    observer_stuck_count: int
    observer_runtime_lagging_count: int
    observer_runtime_stuck_count: int
    health: str


def safe_list(target: Any | None, method_name: str) -> tuple[Any, ...]:
    if target is None:
        return ()
    method = getattr(target, method_name, None)
    if not callable(method):
        return ()
    try:
        return tuple(method())
    except Exception:
        return ()


def source_topics_from(
    subscription_cursors: tuple[Any, ...],
    observer_subscriptions: tuple[Any, ...],
) -> set[str]:
    source_topics = {
        source_topic
        for state in subscription_cursors
        if (source_topic := text(getattr(state, "source_topic", None)))
    }
    source_topics.update(
        source_topic
        for subscription in observer_subscriptions
        if (source_topic := text(getattr(subscription, "source_topic", None)))
    )
    return source_topics


def topic_selection(
    *,
    live_topics: tuple[str, ...],
    source_topics: set[str],
    max_topic_rows: int,
    max_recent_topic_scan: int,
) -> EventsTopicSelection:
    visible_topics = prioritized_topics(
        live_topics=live_topics,
        source_topics=source_topics,
        limit=max_topic_rows,
    )
    recent_scan_topics = prioritized_topics(
        live_topics=live_topics,
        source_topics=source_topics,
        limit=max_recent_topic_scan,
    )
    return EventsTopicSelection(
        visible_topics=visible_topics,
        recent_scan_topics=recent_scan_topics,
        snapshot_topics=tuple(sorted({*visible_topics, *source_topics})),
    )


def recent_events_limit(query: EventsOperationsQuery) -> int:
    return max(query.limit + query.offset, query.limit)


def uncovered_events(events: tuple[dict[str, Any], ...]) -> tuple[dict[str, Any], ...]:
    return tuple(item for item in events if item["contract_status"] == "uncovered")


def state_flag_count(states: tuple[dict[str, Any], ...], key: str) -> int:
    return sum(1 for item in states if item[key])


def events_health_projection(
    *,
    events_service_available: bool,
    subscription_states: tuple[dict[str, Any], ...],
    observer_states: tuple[dict[str, Any], ...],
    observer_runtime_states: tuple[dict[str, Any], ...],
    dead_letter_count: int,
    uncovered_topic_count: int,
) -> EventsHealthProjection:
    lagging_count = state_flag_count(subscription_states, "lagging")
    stuck_count = state_flag_count(subscription_states, "stuck")
    observer_lagging_count = state_flag_count(observer_states, "lagging")
    observer_stuck_count = state_flag_count(observer_states, "stuck")
    observer_runtime_lagging_count = state_flag_count(
        observer_runtime_states,
        "lagging",
    )
    observer_runtime_stuck_count = state_flag_count(
        observer_runtime_states,
        "stuck",
    )
    return EventsHealthProjection(
        lagging_count=lagging_count,
        stuck_count=stuck_count,
        observer_lagging_count=observer_lagging_count,
        observer_stuck_count=observer_stuck_count,
        observer_runtime_lagging_count=observer_runtime_lagging_count,
        observer_runtime_stuck_count=observer_runtime_stuck_count,
        health=events_health(
            events_service_available=events_service_available,
            stuck_count=(
                stuck_count
                + observer_stuck_count
                + observer_runtime_stuck_count
            ),
            lagging_count=(
                lagging_count
                + observer_lagging_count
                + observer_runtime_lagging_count
            ),
            dead_letter_count=dead_letter_count,
            uncovered_topic_count=uncovered_topic_count,
        ),
    )


def events_health(
    *,
    events_service_available: bool,
    stuck_count: int,
    lagging_count: int,
    dead_letter_count: int,
    uncovered_topic_count: int,
) -> str:
    if not events_service_available or dead_letter_count:
        return "error"
    if stuck_count or lagging_count or uncovered_topic_count:
        return "warning"
    return "healthy"


def text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None
