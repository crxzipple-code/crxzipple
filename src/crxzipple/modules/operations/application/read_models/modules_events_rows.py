from __future__ import annotations

from datetime import timezone
from typing import Any

from crxzipple.modules.operations.application.read_models.modules_helpers import (
    now,
    s,
)

_STUCK_SUBSCRIPTION_AFTER_SECONDS = 15.0


def event_subscription_rows(query: Any) -> list[dict[str, str]]:
    if query.events_service is None:
        return []
    states = query.events_service.list_subscription_cursors()
    latest_cursors = {
        state.source_topic: query.events_service.snapshot_event_topic(
            state.source_topic
        )
        for state in states
    }
    rows: list[dict[str, str]] = []
    for state in states:
        latest_cursor = latest_cursors.get(state.source_topic)
        at_head = _compare_event_cursors(state.cursor, latest_cursor) >= 0
        seconds_since_update = max(
            0.0,
            (now() - state.updated_at.astimezone(timezone.utc)).total_seconds(),
        )
        stuck = (
            not at_head
        ) and seconds_since_update >= _STUCK_SUBSCRIPTION_AFTER_SECONDS
        rows.append(
            {
                "subscription_id": state.subscription_id,
                "source_topic": state.source_topic,
                "cursor": state.cursor,
                "latest_cursor": s(latest_cursor),
                "updated_at": state.updated_at.isoformat(),
                "at_head": s(at_head),
                "lagging": s(not at_head),
                "stuck": s(stuck),
                "seconds_since_update": str(round(seconds_since_update, 3)),
                "status": "Stuck" if stuck else "Healthy" if at_head else "Lagging",
            }
        )
    rows.sort(
        key=lambda item: (
            item["status"] != "Stuck",
            item["status"] != "Lagging",
            item["subscription_id"],
        )
    )
    return rows


def event_observer_definition_row(definition: dict[str, Any]) -> dict[str, str]:
    return {
        "observer": s(definition.get("observer_id")),
        "owner": s(definition.get("owner")),
        "inputs": s(definition.get("source_event_names")),
        "outputs": s(definition.get("output_definition_ids")),
        "status": "Registered",
    }


def _compare_event_cursors(left: str | None, right: str | None) -> int:
    left_cursor = _parse_event_cursor(left)
    right_cursor = _parse_event_cursor(right)
    if left_cursor == right_cursor:
        return 0
    return 1 if left_cursor > right_cursor else -1


def _parse_event_cursor(cursor: str | None) -> tuple[int, int]:
    if not isinstance(cursor, str) or not cursor.strip():
        return (0, 0)
    if "-" not in cursor:
        try:
            return (int(cursor), 0)
        except ValueError:
            return (0, 0)
    left, right = cursor.split("-", 1)
    try:
        return (int(left), int(right))
    except ValueError:
        return (0, 0)
