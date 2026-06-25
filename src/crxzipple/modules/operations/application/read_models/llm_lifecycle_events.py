from __future__ import annotations

from crxzipple.modules.operations.application.observation_models import (
    OperationsObservedEvent,
)
from crxzipple.modules.operations.application.read_models.llm_lifecycle_event_rows import (
    event_continuation_label,
    event_input_delta_label,
    event_payload_preview,
    event_tone,
    event_transport_label,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableColumnModel,
    OperationsTableRowModel,
    OperationsTableSectionModel,
)
from crxzipple.shared.time import format_datetime_utc


def llm_lifecycle_events_section(
    observed_events: tuple[OperationsObservedEvent, ...],
) -> OperationsTableSectionModel:
    rows = tuple(
        OperationsTableRowModel(
            id=event.id,
            cells={
                "time": format_datetime_utc(event.occurred_at),
                "level": event.level,
                "event": event.event_name,
                "entity": event.entity_id,
                "status": event.status,
                "trace": event.trace_id or "-",
                "transport": event_transport_label(event),
                "continuation": event_continuation_label(event),
                "input_delta": event_input_delta_label(event),
                "details": event_payload_preview(event.payload),
            },
            status=event.status,
            tone=event_tone(event),
        )
        for event in observed_events[:80]
    )
    return OperationsTableSectionModel(
        id="llm_lifecycle_events",
        title="LLM Lifecycle Events",
        columns=_columns(
            ("time", "Time"),
            ("level", "Level"),
            ("event", "Event"),
            ("entity", "Entity"),
            ("status", "Status"),
            ("trace", "Trace"),
            ("transport", "Transport"),
            ("continuation", "Continuation"),
            ("input_delta", "Input Delta"),
            ("details", "Details"),
        ),
        rows=rows,
        total=len(observed_events),
        empty_state="No LLM lifecycle events observed yet.",
    )


def _columns(*pairs: tuple[str, str]) -> tuple[OperationsTableColumnModel, ...]:
    return tuple(OperationsTableColumnModel(key=key, label=label) for key, label in pairs)
