from __future__ import annotations

from collections import Counter
from typing import Any

from crxzipple.modules.operations.application.read_models.models import (
    MetricCardModel,
    OperationsModuleOverview,
    RuntimeActionModel,
)
from crxzipple.modules.operations.application.read_models.modules_events_rows import (
    event_observer_definition_row,
    event_subscription_rows,
)
from crxzipple.modules.operations.application.read_models.modules_helpers import (
    as_list,
    int_value,
    now,
    overview,
    percent,
    s,
)
from crxzipple.shared.time import format_datetime_utc


def events_operations_overview(query: Any) -> OperationsModuleOverview:
    current_time = now()
    contract_payload = query.event_contract_registry.to_payload()
    definition_payload = query.event_definition_registry.to_payload()
    topics = as_list(contract_payload.get("topics"))
    definitions = as_list(definition_payload.get("definitions"))
    observer_definitions = as_list(definition_payload.get("observers"))
    surfaces = as_list(definition_payload.get("surfaces"))
    subscription_items = event_subscription_rows(query)
    operations_snapshot = (
        query.operations_observation_store.snapshot()
        if query.operations_observation_store is not None
        else None
    )
    observed_module_count = (
        len(getattr(operations_snapshot, "modules", ()))
        if operations_snapshot is not None
        else 0
    )
    lagging = sum(
        1 for item in subscription_items if item["status"] in {"Lagging", "Stuck"}
    )
    stuck = sum(1 for item in subscription_items if item["status"] == "Stuck")
    health = "error" if stuck else "warning" if lagging else "healthy"
    owner_counts = Counter(s(item.get("owner")) for item in topics + definitions)

    return overview(
        module="events",
        title="Events",
        subtitle="聚合事件合同、订阅游标、Topic 与观察者健康。",
        health=health,
        updated_at=format_datetime_utc(current_time),
        metrics=(
            MetricCardModel(
                "topics",
                "Topics",
                str(int_value(contract_payload.get("topic_count"), len(topics))),
                "contract registry",
                "info",
            ),
            MetricCardModel(
                "definitions",
                "Definitions",
                str(int_value(definition_payload.get("definition_count"), len(definitions))),
                "event definitions",
                "success",
            ),
            MetricCardModel(
                "subscriptions",
                "Subscriptions",
                str(len(subscription_items)),
                "runtime cursors",
                "info" if subscription_items else "neutral",
            ),
            MetricCardModel(
                "surfaces",
                "Surfaces",
                str(len(surfaces)),
                "registered UI/event surfaces",
                "neutral",
            ),
            MetricCardModel(
                "lagging",
                "Lagging",
                str(lagging),
                "subscriptions behind head",
                "warning" if lagging else "success",
            ),
            MetricCardModel(
                "stuck",
                "Stuck",
                str(stuck),
                "past stuck threshold",
                "danger" if stuck else "success",
            ),
            MetricCardModel(
                "observers",
                "Observers",
                str(len(observer_definitions)),
                "observer definitions",
                "info",
            ),
            MetricCardModel(
                "observed_modules",
                "Observed Modules",
                str(observed_module_count),
                "operations observer read model",
                "info" if observed_module_count else "neutral",
            ),
        ),
        queue=tuple(subscription_items[:80]),
        lane_locks=tuple(
            {
                "owner": owner,
                "events": str(count),
                "percent": percent(count, sum(owner_counts.values())),
                "trend": "registry",
            }
            for owner, count in sorted(owner_counts.items())
        ),
        executor=tuple(
            event_observer_definition_row(definition)
            for definition in observer_definitions
        ),
        actions=(
            RuntimeActionModel(
                id="open_event_stream", label="Open Event Stream", owner="events"
            ),
            RuntimeActionModel(
                id="inspect_subscription", label="Inspect Subscription", owner="events"
            ),
        ),
    )
