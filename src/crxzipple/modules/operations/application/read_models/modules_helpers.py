from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Any

from crxzipple.modules.operations.application.read_models.models import (
    MetricCardModel,
    OperationsModuleOverview,
    RuntimeActionModel,
)


def overview(
    *,
    module: str,
    title: str,
    subtitle: str,
    health: str,
    updated_at: str,
    metrics: tuple[MetricCardModel, ...],
    queue: tuple[dict[str, str], ...],
    lane_locks: tuple[dict[str, str], ...],
    executor: tuple[dict[str, str], ...],
    actions: tuple[RuntimeActionModel, ...],
) -> OperationsModuleOverview:
    return OperationsModuleOverview(
        module=module,
        title=title,
        subtitle=subtitle,
        health=health,
        updated_at=updated_at,
        metrics=metrics,
        queue=queue,
        lane_locks=lane_locks,
        executor=executor,
        actions=actions,
    )


def health_metric(health: str, delta: str) -> MetricCardModel:
    return MetricCardModel(
        id="health",
        label="Overall Health",
        value={"healthy": "Healthy", "warning": "Warning", "error": "Error"}.get(
            health, "Unknown"
        ),
        delta=delta,
        tone={"healthy": "success", "warning": "warning", "error": "danger"}.get(
            health, "neutral"
        ),
    )


def now() -> datetime:
    return datetime.now(timezone.utc)


def s(value: Any, default: str = "-") -> str:
    if value is None or value == "":
        return default
    if isinstance(value, (list, tuple, set)):
        items = [s(item) for item in value]
        return ", ".join(item for item in items if item != "-") or default
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def int_value(value: Any, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip():
        try:
            return int(float(value))
        except ValueError:
            return default
    return default


def as_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def as_list(value: Any) -> list[dict[str, Any]]:
    return [dict(item) for item in value] if isinstance(value, list) else []


def percent(part: int, total: int) -> str:
    if total <= 0:
        return "0%"
    return f"{round((part / total) * 100, 1)}%"


def short(value: Any, size: int = 28) -> str:
    text = s(value)
    if len(text) <= size:
        return text
    return f"{text[: max(8, size - 8)]}...{text[-5:]}"
