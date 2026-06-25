from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.events_models import (
    EventsOperationsQuery,
)
from crxzipple.modules.operations.application.read_models.events_observer_common import (
    columns,
    display,
    subscription_sort_key,
    subscription_tone,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableRowModel,
    OperationsTableSectionModel,
)


def consumer_health_table(
    subscription_states: list[dict[str, Any]],
) -> OperationsTableSectionModel:
    rows = tuple(
        OperationsTableRowModel(
            id=display(item.get("subscription_id")),
            cells={
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
        for item in sorted(subscription_states, key=subscription_sort_key)
    )
    return OperationsTableSectionModel(
        id="consumer_health",
        title="Consumer Health",
        columns=columns(
            ("subscription", "Subscription"),
            ("source_topic", "Source Topic"),
            ("status", "Status"),
            ("lag", "Lag"),
            ("cursor", "Cursor"),
            ("latest_cursor", "Latest Cursor"),
            ("updated_at", "Updated At"),
            ("contract", "Contract"),
        ),
        rows=rows,
        total=len(subscription_states),
        view_all_route="/operations/events?tab=subscriptions",
        empty_state="No subscription cursors observed.",
    )


def subscriptions_table(
    subscription_states: list[dict[str, Any]],
    *,
    query: EventsOperationsQuery,
) -> OperationsTableSectionModel:
    states = subscription_states
    if query.status in {"at_head", "lagging", "stuck"}:
        states = [item for item in states if item[query.status]]
    rows = tuple(
        OperationsTableRowModel(
            id=f"{item['subscription_id']}:{item['source_topic']}",
            cells={
                "subscription": display(item.get("subscription_id")),
                "source_topic": display(item.get("source_topic")),
                "cursor": display(item.get("cursor")),
                "latest_cursor": display(item.get("latest_cursor")),
                "lag": str(item.get("lag") or 0),
                "status": display(item.get("status")),
                "updated_at": display(item.get("updated_at")),
                "seconds_since_update": str(item.get("seconds_since_update") or 0),
                "contracts": display(item.get("contract_label")),
                "routes": display(item.get("route_label")),
            },
            status=display(item.get("status")).lower().replace(" ", "_"),
            tone=subscription_tone(item),
        )
        for item in sorted(states, key=subscription_sort_key)
    )
    return OperationsTableSectionModel(
        id="subscriptions",
        title="Subscriptions",
        columns=columns(
            ("subscription", "Subscription"),
            ("source_topic", "Source Topic"),
            ("cursor", "Cursor"),
            ("latest_cursor", "Latest Cursor"),
            ("lag", "Lag"),
            ("status", "Status"),
            ("updated_at", "Updated At"),
            ("seconds_since_update", "Seconds Since Update"),
            ("contracts", "Contracts"),
            ("routes", "Routes"),
        ),
        rows=rows,
        total=len(states),
        view_all_route="/operations/events?tab=subscriptions",
        empty_state="No subscription cursors observed.",
    )
