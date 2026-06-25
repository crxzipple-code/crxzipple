from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableColumnModel,
    OperationsTableRowModel,
    OperationsTableSectionModel,
)


def dead_letters_table(
    events: list[dict[str, Any]],
) -> OperationsTableSectionModel:
    rows = tuple(
        OperationsTableRowModel(
            id=_event_row_id(item),
            cells={
                "time": _display(item.get("created_at")),
                "event": _display(item.get("event_name")),
                "topic": _display(item.get("topic")),
                "cursor": _display(item.get("cursor")),
                "owner": _display(item.get("owner")),
                "reason": _display(item.get("status")),
                "trace": _display(item.get("trace_id")),
            },
            status="dead_letter",
            tone="danger",
        )
        for item in events[:80]
    )
    return OperationsTableSectionModel(
        id="dead_letters",
        title="Dead Letters",
        columns=_columns(
            ("time", "Time"),
            ("event", "Event"),
            ("topic", "Topic"),
            ("cursor", "Cursor"),
            ("owner", "Owner"),
            ("reason", "Reason"),
            ("trace", "Trace"),
        ),
        rows=rows,
        total=len(events),
        view_all_route="/operations/events?tab=dead_letters",
        empty_state="No dead-letter events observed.",
    )


def _event_row_id(item: dict[str, Any]) -> str:
    event_id = _display(item.get("event_id"))
    if event_id != "-":
        return event_id
    return f"{_display(item.get('topic'))}:{_display(item.get('cursor'))}"


def _columns(*items: tuple[str, str]) -> tuple[OperationsTableColumnModel, ...]:
    return tuple(OperationsTableColumnModel(key=key, label=label) for key, label in items)


def _display(value: Any, fallback: str = "-") -> str:
    if value is None:
        return fallback
    if isinstance(value, str):
        return value.strip() or fallback
    if isinstance(value, (tuple, list, set)):
        return _join(tuple(_display(item) for item in value))
    return str(value)


def _join(values: tuple[Any, ...] | list[Any]) -> str:
    rendered = [
        str(value).strip()
        for value in values
        if str(value).strip() and str(value).strip() != "-"
    ]
    return ", ".join(rendered) if rendered else "-"
