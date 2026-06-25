from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.events_overview_helpers import (
    health_delta,
    health_label,
    health_tone,
)
from crxzipple.modules.operations.application.read_models.models import (
    MetricCardModel,
)


def events_metric_cards(
    *,
    health: str,
    live_topics: tuple[str, ...],
    definitions: tuple[Any, ...],
    subscriptions: list[dict[str, Any]],
    recent_events: list[dict[str, Any]],
    dead_letters: list[dict[str, Any]],
    observer_states: list[dict[str, Any]],
    observer_runtime_states: list[dict[str, Any]],
) -> tuple[MetricCardModel, ...]:
    at_head = sum(1 for item in subscriptions if item["at_head"])
    lagging = sum(1 for item in subscriptions if item["lagging"])
    stuck = sum(1 for item in subscriptions if item["stuck"])
    observer_stuck = sum(1 for item in observer_states if item["stuck"])
    observer_lagging = sum(1 for item in observer_states if item["lagging"])
    observer_runtime_active = sum(
        1 for item in observer_runtime_states if item["active"]
    )
    observer_runtime_stuck = sum(
        1 for item in observer_runtime_states if item["stuck"]
    )
    observer_runtime_lagging = sum(
        1 for item in observer_runtime_states if item["lagging"]
    )
    return (
        MetricCardModel(
            id="health",
            label="Overall Health",
            value=health_label(health),
            delta=health_delta(health),
            tone=health_tone(health),
        ),
        MetricCardModel(
            id="topics",
            label="Live Topics",
            value=str(len(live_topics)),
            delta="event bus topics",
            tone="info" if live_topics else "neutral",
        ),
        MetricCardModel(
            id="recent_events",
            label="Recent Events",
            value=str(len(recent_events)),
            delta="retained bus records",
            tone="info" if recent_events else "neutral",
        ),
        MetricCardModel(
            id="definitions",
            label="Definitions",
            value=str(len(definitions)),
            delta="registered event definitions",
            tone="success" if definitions else "warning",
        ),
        MetricCardModel(
            id="subscriptions",
            label="Subscriptions",
            value=str(len(subscriptions)),
            delta=f"{at_head} at head",
            tone="info" if subscriptions else "neutral",
        ),
        MetricCardModel(
            id="lagging",
            label="Lagging",
            value=str(lagging),
            delta=f"{stuck} stuck",
            tone="danger" if stuck else "warning" if lagging else "success",
        ),
        MetricCardModel(
            id="dead_letters",
            label="Dead Letters",
            value=str(len(dead_letters)),
            delta="recent dead-letter records",
            tone="danger" if dead_letters else "success",
        ),
        MetricCardModel(
            id="observers",
            label="Observers",
            value=str(observer_runtime_active),
            delta=(
                f"{len(observer_runtime_states)} runtimes / "
                f"{len(observer_states)} subscriptions"
            ),
            tone=(
                "danger"
                if observer_stuck or observer_runtime_stuck
                else "warning"
                if observer_lagging
                or observer_runtime_lagging
                or not observer_runtime_states
                else "info"
                if observer_states or observer_runtime_states
                else "neutral"
            ),
        ),
    )
