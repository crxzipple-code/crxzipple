from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.events_models import (
    EventsOperationsQuery,
)

_EVENT_FILTER_STATUSES = frozenset(
    {
        "all",
        "matched",
        "uncovered",
        "definition_only",
        "topic_contract_only",
        "dead_letter",
        "at_head",
        "lagging",
        "stuck",
    },
)
_CONTRACT_FILTER_STATUSES = frozenset(
    {
        "matched",
        "uncovered",
        "definition_only",
        "topic_contract_only",
        "dead_letter",
    },
)


def normalize_events_query(
    query: EventsOperationsQuery | None,
) -> EventsOperationsQuery:
    if query is None:
        return EventsOperationsQuery()
    status = (query.status or "all").strip().lower() or "all"
    if status not in _EVENT_FILTER_STATUSES:
        status = "all"
    owner = (query.owner or "all").strip().lower() or "all"
    return EventsOperationsQuery(
        status=status,
        topic_prefix=(query.topic_prefix or "").strip(),
        search=(query.search or "").strip(),
        owner=owner,
        limit=max(1, min(int(query.limit or 80), 200)),
        offset=max(0, int(query.offset or 0)),
    )


def filter_events(
    events: list[dict[str, Any]],
    query: EventsOperationsQuery,
) -> list[dict[str, Any]]:
    filtered = events
    if query.status in _CONTRACT_FILTER_STATUSES:
        filtered = [
            item
            for item in filtered
            if _display(item.get("contract_status")) == query.status
        ]
    if query.owner != "all":
        filtered = [
            item
            for item in filtered
            if _display(item.get("owner")).lower() == query.owner
        ]
    if query.topic_prefix:
        filtered = [
            item
            for item in filtered
            if _display(item.get("topic")).startswith(query.topic_prefix)
        ]
    if query.search:
        needle = query.search.lower()
        filtered = [
            item
            for item in filtered
            if needle
            in " ".join(
                (
                    _display(item.get("event_name")),
                    _display(item.get("topic")),
                    _display(item.get("event_id")),
                    _display(item.get("trace_id")),
                    _display(item.get("run_id")),
                    _display(item.get("owner")),
                )
            ).lower()
        ]
    return filtered


def recent_empty_state(query: EventsOperationsQuery) -> str:
    if query.search or query.status != "all" or query.owner != "all" or query.topic_prefix:
        return "No events match the current filters."
    return "No event bus records observed."


def _display(value: Any, fallback: str = "-") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    return text or fallback
