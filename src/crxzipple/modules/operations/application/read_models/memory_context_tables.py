from __future__ import annotations

from crxzipple.modules.operations.application.observation_models import (
    OperationsObservedEvent,
)
from crxzipple.modules.operations.application.read_models.memory_common import (
    record_resolved,
)
from crxzipple.modules.operations.application.read_models.memory_events import (
    event_details,
    event_tone,
)
from crxzipple.modules.operations.application.read_models.memory_models import (
    MemoryContextRecord,
)
from crxzipple.modules.operations.application.read_models.memory_values import (
    short,
    status_label,
    text,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableColumnModel,
    OperationsTableRowModel,
    OperationsTableSectionModel,
)
from crxzipple.shared.time import coerce_utc_datetime, format_datetime_utc


def context_resolution_table(
    records: tuple[MemoryContextRecord, ...],
    events: tuple[OperationsObservedEvent, ...],
) -> OperationsTableSectionModel:
    context_events = tuple(
        event
        for event in events
        if event.event_name
        in {"memory.context.resolved", "memory.context.resolve_failed"}
    )
    rows: list[OperationsTableRowModel] = [
        OperationsTableRowModel(
            id=text(event.cursor or event.id, ""),
            cells={
                "time": format_datetime_utc(coerce_utc_datetime(event.occurred_at)),
                "agent": text(
                    event.payload.get("agent_id") or event.payload.get("space_ref")
                ),
                "space_id": text(event.payload.get("space_id") or event.entity_id),
                "backend": text(event.payload.get("retrieval_backend")),
                "status": status_label(event.status),
                "reason": event_details(event.payload),
                "storage_root": short(event.payload.get("storage_root"), 72),
                "trace": text(event.trace_id),
            },
            status=event.status,
            tone=event_tone(event),
        )
        for event in context_events[:80]
    ]
    if not rows:
        rows.extend(
            OperationsTableRowModel(
                id=f"context:{record.agent_id}",
                cells={
                    "time": "-",
                    "agent": record.agent_id,
                    "space_id": record.scope_ref or "-",
                    "backend": record.retrieval_backend or "-",
                    "status": "Resolved" if record_resolved(record) else "Resolve Failed",
                    "reason": record.error or "Current Context",
                    "storage_root": short(record.storage_root or "-", 72),
                    "trace": "-",
                },
                status="resolved" if record_resolved(record) else "failed",
                tone="success" if record_resolved(record) else "warning",
            )
            for record in records
        )
    return OperationsTableSectionModel(
        id="context_resolution",
        title="Context Resolution",
        columns=(
            OperationsTableColumnModel("time", "Time"),
            OperationsTableColumnModel("agent", "Agent"),
            OperationsTableColumnModel("space_id", "Space ID"),
            OperationsTableColumnModel("backend", "Retrieval Backend"),
            OperationsTableColumnModel("status", "Status"),
            OperationsTableColumnModel("reason", "Reason"),
            OperationsTableColumnModel("storage_root", "Storage Root"),
            OperationsTableColumnModel("trace", "Trace"),
        ),
        rows=tuple(rows),
        total=len(context_events) if context_events else len(rows),
        empty_state="No memory context resolution events.",
    )
