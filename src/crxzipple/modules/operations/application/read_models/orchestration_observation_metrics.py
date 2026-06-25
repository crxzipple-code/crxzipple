from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.models import (
    MetricCardModel,
)
from crxzipple.modules.operations.application.read_models.presenters import (
    display_value,
)


def observation_metric(observer_state: Any | None) -> MetricCardModel:
    if observer_state is None:
        return MetricCardModel(
            id="observed_facts",
            label="Observed Facts",
            value="0",
            delta="runtime facts unavailable",
            tone="warning",
        )
    event_count = _int_from_attr(observer_state, "event_count")
    recent_count = len(getattr(observer_state, "recent_events", ()) or ())
    last_event_name = _display(getattr(observer_state, "last_event_name", None))
    return MetricCardModel(
        id="observed_facts",
        label="Observed Facts",
        value=str(event_count),
        delta=f"{recent_count} recent / last {last_event_name}",
        tone="info",
    )


def _int_from_attr(value: Any, attr: str) -> int:
    raw = getattr(value, attr, 0)
    return raw if isinstance(raw, int) else 0


def _display(value: object | None) -> str:
    return display_value(value)
