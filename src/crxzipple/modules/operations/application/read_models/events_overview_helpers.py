from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableColumnModel,
)


def health_label(health: str) -> str:
    return {
        "healthy": "Healthy",
        "warning": "Warning",
        "error": "Error",
    }.get(health, "Unknown")


def health_delta(health: str) -> str:
    return {
        "healthy": "Event bus state is queryable",
        "warning": "Operator attention recommended",
        "error": "Operator action required",
    }.get(health, "Insufficient data")


def health_tone(health: str) -> str:
    return {
        "healthy": "success",
        "warning": "warning",
        "error": "danger",
    }.get(health, "neutral")


def kind_tone(kind: str) -> str:
    return {
        "command": "info",
        "fact": "success",
        "broadcast": "neutral",
        "observe": "warning",
        "live": "info",
    }.get(kind.lower(), "neutral")


def status_label(status: str) -> str:
    normalized = status.strip().replace("_", " ").replace("-", " ")
    return normalized.title() if normalized else "Observed"


def status_tone(status: str) -> str:
    return {
        "matched": "success",
        "uncovered": "warning",
        "definition_only": "neutral",
        "topic_contract_only": "warning",
        "dead_letter": "danger",
        "observed": "info",
    }.get(status, "neutral")


def tone_for_index(index: int) -> str:
    return ("info", "success", "warning", "neutral")[index % 4]


def owner_from_subscription(item: dict[str, Any]) -> str:
    owner = display(item.get("owner"))
    if owner != "-":
        return owner
    subscription_id = display(item.get("subscription_id"))
    if "." in subscription_id:
        return subscription_id.split(".", 1)[0]
    source_topic = display(item.get("source_topic"))
    if "." in source_topic:
        return source_topic.split(".", 1)[0]
    return "-"


def columns(*items: tuple[str, str]) -> tuple[OperationsTableColumnModel, ...]:
    return tuple(OperationsTableColumnModel(key=key, label=label) for key, label in items)


def display(value: Any, fallback: str = "-") -> str:
    if value is None:
        return fallback
    if isinstance(value, str):
        return value.strip() or fallback
    if isinstance(value, (tuple, list, set)):
        return join_values(tuple(display(item) for item in value))
    return str(value)


def int_value(value: Any) -> int:
    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return 0


def join_values(values: tuple[Any, ...] | list[Any]) -> str:
    rendered = [
        str(value).strip()
        for value in values
        if str(value).strip() and str(value).strip() != "-"
    ]
    return ", ".join(rendered) if rendered else "-"


def slug(value: str) -> str:
    normalized = "".join(ch.lower() if ch.isalnum() else "_" for ch in value)
    return "_".join(part for part in normalized.split("_") if part) or "unknown"
