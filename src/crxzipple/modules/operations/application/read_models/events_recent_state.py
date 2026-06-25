from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.observation_models import OperationsObservedEvent
from crxzipple.modules.operations.application.read_models.events_recent_projection import (
    event_summary_from_observed_event,
    event_summary_from_record,
)
from crxzipple.modules.operations.application.read_models.events_state_common import (
    display,
    safe_operations_observation_snapshot,
)


def recent_event_summaries(
    events_service: Any | None,
    *,
    topics: tuple[str, ...],
    definition_registry: Any | None,
    contract_registry: Any | None,
    limit: int,
) -> list[dict[str, Any]]:
    if events_service is None or limit <= 0:
        return []
    records = []
    per_topic_limit = min(max(limit, 20), 80)
    for topic in topics:
        try:
            topic_records = events_service.read_recent_event_topic(
                topic,
                limit=per_topic_limit,
            )
        except Exception:
            continue
        records.extend(topic_records)
    summaries = []
    for record in records:
        summary = event_summary_from_record(
            record,
            definition_registry=definition_registry,
            contract_registry=contract_registry,
        )
        if summary is not None:
            summaries.append(summary)
    summaries.sort(
        key=lambda item: (
            display(item.get("created_at")),
            display(item.get("topic")),
            display(item.get("event_id")),
        ),
        reverse=True,
    )
    return summaries[:limit]


def recent_event_summaries_from_observation(
    operations_observation: Any | None,
    *,
    definition_registry: Any | None,
    contract_registry: Any | None,
    limit: int,
) -> list[dict[str, Any]]:
    snapshot = safe_operations_observation_snapshot(operations_observation)
    if snapshot is None or limit <= 0:
        return []
    summaries: list[dict[str, Any]] = []
    for module in tuple(getattr(snapshot, "modules", ()) or ()):
        for observed in tuple(getattr(module, "recent_events", ()) or ()):
            if not isinstance(observed, OperationsObservedEvent):
                continue
            summary = event_summary_from_observed_event(
                observed,
                definition_registry=definition_registry,
                contract_registry=contract_registry,
            )
            if summary is not None:
                summaries.append(summary)
    summaries.sort(
        key=lambda item: (
            display(item.get("created_at")),
            display(item.get("topic")),
            display(item.get("event_id")),
        ),
        reverse=True,
    )
    return summaries[:limit]


def dead_letter_events(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        item
        for item in events
        if display(item.get("contract_status")) == "dead_letter"
        or "dead_letter" in display(item.get("topic")).lower()
        or "dead-letter" in display(item.get("topic")).lower()
    ]
