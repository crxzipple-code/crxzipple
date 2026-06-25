from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableColumnModel,
)


def observer_event_name(item: dict[str, Any]) -> str:
    subscription_id = display(item.get("subscription_id"))
    observer_prefix = "operations.observer."
    if subscription_id.startswith(observer_prefix):
        return subscription_id.removeprefix(observer_prefix)
    topic = display(item.get("source_topic"))
    named_prefix = "events.named."
    if topic.startswith(named_prefix):
        return topic.removeprefix(named_prefix)
    return topic


def event_row_id(item: dict[str, Any]) -> str:
    event_id = display(item.get("event_id"))
    if event_id != "-":
        return event_id
    return f"{display(item.get('topic'))}:{display(item.get('cursor'))}"


def subscription_tone(item: dict[str, Any]) -> str:
    if item.get("stuck"):
        return "danger"
    if item.get("lagging"):
        return "warning"
    return "success"


def subscription_sort_key(item: dict[str, Any]) -> tuple[bool, bool, int, str, str]:
    return (
        not bool(item.get("stuck")),
        not bool(item.get("lagging")),
        -int(item.get("lag") or 0),
        display(item.get("source_topic")),
        display(item.get("subscription_id")),
    )


def observer_runtime_sort_key(item: dict[str, Any]) -> tuple[bool, bool, str, str]:
    return (
        not bool(item.get("stuck")),
        not bool(item.get("lagging")),
        display(item.get("runtime_name")),
        display(item.get("worker_id")),
    )


def columns(*items: tuple[str, str]) -> tuple[OperationsTableColumnModel, ...]:
    return tuple(OperationsTableColumnModel(key=key, label=label) for key, label in items)


def display(value: Any, fallback: str = "-") -> str:
    if value is None:
        return fallback
    if isinstance(value, str):
        return value.strip() or fallback
    if isinstance(value, (tuple, list, set)):
        return join(tuple(display(item) for item in value))
    return str(value)


def join(values: tuple[Any, ...] | list[Any]) -> str:
    rendered = [
        str(value).strip()
        for value in values
        if str(value).strip() and str(value).strip() != "-"
    ]
    return ", ".join(rendered) if rendered else "-"
