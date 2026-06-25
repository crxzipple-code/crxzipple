from __future__ import annotations

from collections import Counter
from typing import Any

from crxzipple.modules.operations.application.read_models.events_overview_helpers import (
    columns,
    display,
    int_value,
    owner_from_subscription,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableRowModel,
    OperationsTableSectionModel,
)


def owners_by_volume(
    events: list[dict[str, Any]],
    *,
    definitions: tuple[Any, ...],
    surfaces: tuple[Any, ...],
    subscriptions: list[dict[str, Any]],
    event_buckets: tuple[dict[str, Any], ...] = (),
) -> OperationsTableSectionModel:
    event_counts = Counter(display(item.get("owner")) for item in events)
    if event_buckets:
        event_counts = Counter()
        for bucket in event_buckets:
            owner = display(bucket.get("owner") or bucket.get("module"))
            if owner != "-":
                event_counts[owner] += int_value(bucket.get("count"))
    definition_counts = Counter(display(getattr(item, "owner", None)) for item in definitions)
    surface_counts = Counter(display(getattr(item, "owner", None)) for item in surfaces)
    subscription_counts = Counter(
        owner_from_subscription(item) for item in subscriptions
    )
    owners = sorted(
        {
            owner
            for owner in (
                set(event_counts)
                | set(definition_counts)
                | set(surface_counts)
                | set(subscription_counts)
            )
            if owner != "-"
        },
        key=lambda owner: (
            -event_counts[owner],
            -definition_counts[owner],
            owner,
        ),
    )
    rows = tuple(
        OperationsTableRowModel(
            id=owner,
            cells={
                "owner": owner,
                "events": str(event_counts[owner]),
                "definitions": str(definition_counts[owner]),
                "surfaces": str(surface_counts[owner]),
                "subscriptions": str(subscription_counts[owner]),
            },
            status="active" if event_counts[owner] else "registered",
            tone="info" if event_counts[owner] else "neutral",
        )
        for owner in owners[:40]
    )
    return OperationsTableSectionModel(
        id="owners_by_volume",
        title="Owners by Volume",
        columns=columns(
            ("owner", "Owner"),
            ("events", "Events"),
            ("definitions", "Definitions"),
            ("surfaces", "Surfaces"),
            ("subscriptions", "Subscriptions"),
        ),
        rows=rows,
        total=len(owners),
        view_all_route="/operations/events?tab=owners",
        empty_state="No event owners observed.",
    )
