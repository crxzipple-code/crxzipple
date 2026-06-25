from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.observation_models import (
    OperationsObservedEvent,
)
from crxzipple.modules.operations.application.read_models.llm_detail_payloads import (
    columns,
    enum_value,
    json_preview,
)
from crxzipple.modules.operations.application.read_models.llm_lifecycle_event_rows import (
    event_tone,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableRowModel,
    OperationsTableSectionModel,
)
from crxzipple.shared.time import format_datetime_utc


def response_events_table_for_invocation(
    invocation_id: str,
    response_events: tuple[Any, ...],
) -> OperationsTableSectionModel:
    rows = tuple(
        OperationsTableRowModel(
            id=str(getattr(event, "id", f"{invocation_id}:response_event:{index}")),
            cells={
                "sequence": str(getattr(event, "sequence_no", index)),
                "type": enum_value(getattr(event, "type", None)),
                "item_id": str(getattr(event, "item_id", None) or "-"),
                "provider_event": _provider_event_type(event),
                "delta": json_preview(getattr(event, "delta_payload", {}) or {}),
            },
            status=enum_value(getattr(event, "type", None)),
            tone=_response_event_tone(enum_value(getattr(event, "type", None))),
        )
        for index, event in enumerate(response_events[:80], start=1)
    )
    return OperationsTableSectionModel(
        id=f"{invocation_id}_response_events",
        title="Response Events",
        columns=columns(
            ("sequence", "Seq"),
            ("type", "Type"),
            ("item_id", "Item ID"),
            ("provider_event", "Provider Event"),
            ("delta", "Delta"),
        ),
        rows=rows,
        total=len(response_events),
        empty_state="No response events recorded.",
    )


def events_table_for_invocation(
    invocation_id: str,
    events: tuple[OperationsObservedEvent, ...],
) -> OperationsTableSectionModel:
    rows = tuple(
        OperationsTableRowModel(
            id=event.id,
            cells={
                "time": format_datetime_utc(event.occurred_at),
                "level": event.level,
                "event": event.event_name,
                "status": event.status,
                "details": json_preview(event.payload),
            },
            status=event.status,
            tone=event_tone(event),
        )
        for event in events[:30]
    )
    return OperationsTableSectionModel(
        id=f"{invocation_id}_events",
        title="Invocation Events",
        columns=columns(
            ("time", "Time"),
            ("level", "Level"),
            ("event", "Event"),
            ("status", "Status"),
            ("details", "Details"),
        ),
        rows=rows,
        total=len(events),
        empty_state="No observed events for this invocation.",
    )


def _response_event_tone(event_type: str) -> str:
    if event_type == "failed":
        return "danger"
    if event_type in {"tool_argument_delta", "item_started", "item_completed"}:
        return "info"
    if event_type == "completed":
        return "success"
    return "neutral"


def _provider_event_type(event: Any) -> str:
    provider_payload = getattr(event, "provider_payload", None)
    if isinstance(provider_payload, dict):
        event_type = provider_payload.get("type") or provider_payload.get(
            "provider_event_type",
        )
        if event_type is not None:
            return str(event_type)
    delta_payload = getattr(event, "delta_payload", None)
    if isinstance(delta_payload, dict):
        event_type = delta_payload.get("provider_event_type")
        if event_type is not None:
            return str(event_type)
    return "-"
