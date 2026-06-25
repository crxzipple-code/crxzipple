from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.models import (
    OperationsKeyValueItemModel,
    OperationsKeyValueSectionModel,
)


def contract_compatibility(
    *,
    live_topics: tuple[str, ...],
    topic_contracts: tuple[Any, ...],
    route_contracts: tuple[Any, ...],
    definitions: tuple[Any, ...],
    surfaces: tuple[Any, ...],
    observer_definitions: tuple[Any, ...],
    subscriptions: list[dict[str, Any]],
    uncovered_topics: tuple[str, ...],
    uncovered_events: list[dict[str, Any]],
) -> OperationsKeyValueSectionModel:
    lagging = sum(1 for item in subscriptions if item["lagging"])
    stuck = sum(1 for item in subscriptions if item["stuck"])
    return OperationsKeyValueSectionModel(
        id="contract_compatibility",
        title="Contract Compatibility",
        items=(
            OperationsKeyValueItemModel("Live Topics", str(len(live_topics)), "info"),
            OperationsKeyValueItemModel(
                "Topic Contracts",
                str(len(topic_contracts)),
                "success" if topic_contracts else "warning",
            ),
            OperationsKeyValueItemModel(
                "Route Contracts",
                str(len(route_contracts)),
                "success" if route_contracts else "neutral",
            ),
            OperationsKeyValueItemModel(
                "Definitions",
                str(len(definitions)),
                "success" if definitions else "warning",
            ),
            OperationsKeyValueItemModel("Surfaces", str(len(surfaces)), "info"),
            OperationsKeyValueItemModel(
                "Observer Definitions",
                str(len(observer_definitions)),
                "info",
            ),
            OperationsKeyValueItemModel(
                "Uncovered Topics",
                str(len(uncovered_topics)),
                "warning" if uncovered_topics else "success",
            ),
            OperationsKeyValueItemModel(
                "Uncovered Events",
                str(len(uncovered_events)),
                "warning" if uncovered_events else "success",
            ),
            OperationsKeyValueItemModel(
                "Lagging Subscriptions",
                str(lagging),
                "warning" if lagging else "success",
            ),
            OperationsKeyValueItemModel(
                "Stuck Subscriptions",
                str(stuck),
                "danger" if stuck else "success",
            ),
        ),
    )
