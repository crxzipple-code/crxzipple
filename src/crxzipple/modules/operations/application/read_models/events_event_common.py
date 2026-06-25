from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableColumnModel,
)


def columns(*items: tuple[str, str]) -> tuple[OperationsTableColumnModel, ...]:
    return tuple(OperationsTableColumnModel(key=key, label=label) for key, label in items)


def contract_status_label(status: str) -> str:
    return {
        "matched": "Matched",
        "uncovered": "Uncovered",
        "definition_only": "Definition Only",
        "topic_contract_only": "Topic Contract Only",
        "dead_letter": "Dead Letter",
    }.get(status, status or "-")


def event_tone(item: dict[str, Any]) -> str:
    status = display(item.get("contract_status"))
    if status == "matched":
        return "success"
    if status == "dead_letter":
        return "danger"
    if status in {"uncovered", "topic_contract_only"}:
        return "warning"
    return "neutral"


def subscription_tone(item: dict[str, Any]) -> str:
    if item.get("stuck"):
        return "danger"
    if item.get("lagging"):
        return "warning"
    if item.get("at_head"):
        return "success"
    return "neutral"


def display(value: Any, fallback: str = "-") -> str:
    if value is None:
        return fallback
    if isinstance(value, str):
        return value.strip() or fallback
    if isinstance(value, (tuple, list, set)):
        return _join(tuple(display(item) for item in value))
    return str(value)


def as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_tuple(value: Any) -> tuple[Any, ...]:
    if isinstance(value, tuple):
        return value
    if isinstance(value, list):
        return tuple(value)
    return ()


def _join(values: tuple[Any, ...] | list[Any]) -> str:
    rendered = [
        str(value).strip()
        for value in values
        if str(value).strip() and str(value).strip() != "-"
    ]
    return ", ".join(rendered) if rendered else "-"
