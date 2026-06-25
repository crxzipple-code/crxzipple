from __future__ import annotations

from collections import defaultdict
from typing import Any

from crxzipple.modules.operations.application.read_models.events_contract_matching import (
    contract_ids,
    match_route_contracts,
    match_topic_contracts,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableRowModel,
)


def topic_rows(
    topics: tuple[str, ...],
    *,
    latest_cursors: dict[str, str | None],
    subscription_states: list[dict[str, Any]],
    recent_events: list[dict[str, Any]],
    registry: Any | None,
) -> list[OperationsTableRowModel]:
    subscriptions_by_topic: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in subscription_states:
        subscriptions_by_topic[_display(item.get("source_topic"))].append(item)
    events_by_topic: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in recent_events:
        events_by_topic[_display(item.get("topic"))].append(item)
    rows = []
    for topic in topics:
        topic_events = events_by_topic.get(topic, [])
        latest_event = topic_events[0] if topic_events else {}
        contract_matches = match_topic_contracts(registry, topic)
        route_matches = match_route_contracts(registry, topic)
        kinds = sorted(
            {_display(item.get("kind")) for item in topic_events if item.get("kind")}
        )
        rows.append(
            OperationsTableRowModel(
                id=topic,
                cells={
                    "topic": topic,
                    "latest_cursor": _display(latest_cursors.get(topic)),
                    "recent_events": str(len(topic_events)),
                    "subscriptions": str(len(subscriptions_by_topic.get(topic, []))),
                    "contract": _join(contract_ids(contract_matches)),
                    "routes": _join(contract_ids(route_matches)),
                    "latest_event": _display(latest_event.get("event_name")),
                    "kinds": _join(kinds),
                },
                status="covered" if contract_matches else "uncovered",
                tone="success" if contract_matches else "warning",
            )
        )
    return rows


def uncovered_topics(
    topics: tuple[str, ...],
    *,
    registry: Any | None,
) -> tuple[str, ...]:
    return tuple(
        topic
        for topic in topics
        if not match_topic_contracts(registry, topic)
    )


def _display(value: Any, fallback: str = "-") -> str:
    if value is None:
        return fallback
    if isinstance(value, str):
        return value.strip() or fallback
    if isinstance(value, (tuple, list, set)):
        return _join(tuple(_display(item) for item in value))
    return str(value)


def _join(values: tuple[Any, ...] | list[Any]) -> str:
    rendered = [
        str(value).strip()
        for value in values
        if str(value).strip() and str(value).strip() != "-"
    ]
    return ", ".join(rendered) if rendered else "-"
