from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.events_observer_common import (
    columns,
    display,
    event_row_id,
    observer_event_name,
    observer_runtime_sort_key,
    subscription_sort_key,
    subscription_tone,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableRowModel,
    OperationsTableSectionModel,
)


def observer_health_table(
    observer_states: list[dict[str, Any]],
    *,
    runtime_states: list[dict[str, Any]],
    definitions: tuple[Any, ...],
) -> OperationsTableSectionModel:
    definitions_by_event_name = {
        display(getattr(definition, "event_name", None)): definition
        for definition in definitions
    }
    rows = []
    for item in sorted(runtime_states, key=observer_runtime_sort_key):
        rows.append(
            OperationsTableRowModel(
                id=f"runtime:{item['runtime_name']}:{item['worker_id']}",
                cells={
                    "runtime_key": display(item.get("runtime_name")),
                    "worker_id": display(item.get("worker_id")),
                    "event": "Observer Runtime",
                    "module": "operations",
                    "owner": "operations",
                    "status": display(item.get("status")),
                    "lag": "-",
                    "updated_at": display(item.get("last_seen_at")),
                    "subscriptions": str(item.get("subscription_count") or 0),
                },
                status=display(item.get("status")).lower().replace(" ", "_"),
                tone=display(item.get("tone"), "neutral"),
            )
        )
    for item in sorted(observer_states, key=subscription_sort_key):
        event_name = observer_event_name(item)
        definition = definitions_by_event_name.get(event_name)
        rows.append(
            OperationsTableRowModel(
                id=f"{item['subscription_id']}:{item['source_topic']}",
                cells={
                    "runtime_key": "-",
                    "worker_id": "-",
                    "event": event_name,
                    "module": display(getattr(definition, "module", None)),
                    "owner": display(getattr(definition, "owner", None)),
                    "subscription": display(item.get("subscription_id")),
                    "source_topic": display(item.get("source_topic")),
                    "status": display(item.get("status")),
                    "lag": str(item.get("lag") or 0),
                    "cursor": display(item.get("cursor")),
                    "latest_cursor": display(item.get("latest_cursor")),
                    "updated_at": display(item.get("updated_at")),
                    "contract": display(item.get("contract_label")),
                },
                status=display(item.get("status")).lower().replace(" ", "_"),
                tone=subscription_tone(item),
            )
        )
    return OperationsTableSectionModel(
        id="observer_health",
        title="Observer Health",
        columns=columns(
            ("runtime_key", "Runtime Key"),
            ("event", "Event"),
            ("owner", "Owner"),
            ("status", "Status"),
            ("lag", "Lag"),
            ("updated_at", "Last Seen"),
        ),
        rows=tuple(rows),
        total=len(rows),
        view_all_route="/operations/events?tab=observer",
        empty_state="No operations observer subscriptions registered.",
    )


def observer_lag_table(
    subscription_states: list[dict[str, Any]],
    events: list[dict[str, Any]],
) -> OperationsTableSectionModel:
    rows: list[OperationsTableRowModel] = []
    for item in sorted(subscription_states, key=subscription_sort_key):
        if not item["lagging"] and not item["stuck"]:
            continue
        rows.append(
            OperationsTableRowModel(
                id=f"subscription:{item['subscription_id']}:{item['source_topic']}",
                cells={
                    "source": display(item.get("source_topic")),
                    "target": display(item.get("subscription_id")),
                    "reason": "stuck_subscription" if item["stuck"] else "lagging_subscription",
                    "count": str(item.get("lag") or 0),
                    "last": display(item.get("updated_at")),
                },
                status="stuck" if item["stuck"] else "lagging",
                tone="danger" if item["stuck"] else "warning",
            )
        )
    for item in events:
        if not _looks_like_mapping_failure(item):
            continue
        rows.append(
            OperationsTableRowModel(
                id=f"event:{event_row_id(item)}",
                cells={
                    "source": display(item.get("topic")),
                    "target": display(item.get("event_name")),
                    "reason": display(item.get("status")),
                    "count": "1",
                    "last": display(item.get("created_at")),
                },
                status="failed",
                tone="danger",
            )
        )
    return OperationsTableSectionModel(
        id="observer_lag",
        title="Observer Lag",
        columns=columns(
            ("source", "Source"),
            ("target", "Target"),
            ("reason", "Reason"),
            ("count", "Count"),
            ("last", "Last Seen"),
        ),
        rows=tuple(rows[:80]),
        total=len(rows),
        view_all_route="/operations/events?tab=observer_lag",
        empty_state="No observer lag or failed observer records observed.",
    )


def _looks_like_mapping_failure(item: dict[str, Any]) -> bool:
    text = " ".join(
        (
            display(item.get("event_name")),
            display(item.get("status")),
            display(item.get("topic")),
            display(item.get("level")),
        )
    ).lower()
    return any(
        token in text
        for token in (
            "observation",
            "observer",
            "mapping",
            "dead_letter",
            "failed",
            "error",
        )
    )
