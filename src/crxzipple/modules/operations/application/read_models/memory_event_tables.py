from __future__ import annotations

from crxzipple.modules.operations.application.observation_models import (
    OperationsObservedEvent,
)
from crxzipple.modules.operations.application.read_models.memory_values import (
    duration_label_from_ms,
    status_label,
    text,
)
from crxzipple.modules.operations.application.read_models.memory_events import (
    event_details,
    event_tone,
    short_event_name,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableColumnModel,
    OperationsTableRowModel,
    OperationsTableSectionModel,
)
from crxzipple.shared.time import coerce_utc_datetime, format_datetime_utc


def index_sync_activity_table(
    events: tuple[OperationsObservedEvent, ...],
) -> OperationsTableSectionModel:
    filtered = tuple(
        event for event in events if event.event_name.startswith("memory.index.")
    )
    rows = [
        OperationsTableRowModel(
            id=text(event.cursor or event.id, ""),
            cells={
                "time": format_datetime_utc(coerce_utc_datetime(event.occurred_at)),
                "operation": short_event_name(event.event_name),
                "space_id": text(event.payload.get("space_id") or event.entity_id),
                "status": status_label(event.status),
                "changed": text(
                    event.payload.get("changed_path_count")
                    or event.payload.get("changed_paths")
                    or "-",
                ),
                "reindexed": text(event.payload.get("reindexed_files") or "-"),
                "chunks": text(event.payload.get("chunk_count") or "-"),
                "duration": duration_label_from_ms(event.payload.get("duration_ms")),
                "reason": event_details(event.payload),
            },
            status=event.status,
            tone=event_tone(event),
        )
        for event in filtered[:100]
    ]
    return OperationsTableSectionModel(
        id="index_sync_activity",
        title="Index Sync Activity",
        columns=(
            OperationsTableColumnModel("time", "Time"),
            OperationsTableColumnModel("operation", "Operation"),
            OperationsTableColumnModel("space_id", "Space ID"),
            OperationsTableColumnModel("status", "Status"),
            OperationsTableColumnModel("changed", "Changed"),
            OperationsTableColumnModel("reindexed", "Reindexed"),
            OperationsTableColumnModel("chunks", "Chunks"),
            OperationsTableColumnModel("duration", "Duration"),
            OperationsTableColumnModel("reason", "Reason"),
        ),
        rows=tuple(rows),
        total=len(filtered),
        empty_state="No memory index sync activity.",
    )


def write_flush_table(
    events: tuple[OperationsObservedEvent, ...],
) -> OperationsTableSectionModel:
    filtered = tuple(
        event
        for event in events
        if any(
            token in event.event_name.lower()
            for token in ("remember", "write", "flush", "memory.daily", "memory.long")
        )
    )
    rows = [
        OperationsTableRowModel(
            id=text(event.cursor or event.id, ""),
            cells={
                "time": format_datetime_utc(coerce_utc_datetime(event.occurred_at)),
                "operation": short_event_name(event.event_name),
                "file": text(event.payload.get("path") or event.entity_id),
                "status": status_label(event.status),
                "details": event_details(event.payload),
                "trace": text(event.trace_id),
            },
            status=event.status,
            tone=event_tone(event),
        )
        for event in filtered[:80]
    ]
    return OperationsTableSectionModel(
        id="write_flush",
        title="Write / Flush",
        columns=(
            OperationsTableColumnModel("time", "Time"),
            OperationsTableColumnModel("operation", "Operation"),
            OperationsTableColumnModel("file", "File"),
            OperationsTableColumnModel("status", "Status"),
            OperationsTableColumnModel("details", "Details"),
            OperationsTableColumnModel("trace", "Trace"),
        ),
        rows=tuple(rows),
        total=len(filtered),
        empty_state="No memory write or flush events.",
    )


def retrieval_logs_table(
    events: tuple[OperationsObservedEvent, ...],
) -> OperationsTableSectionModel:
    filtered = tuple(
        event
        for event in events
        if any(
            token in event.event_name.lower()
            for token in ("search", "retrieval", "recall", "memory")
        )
    )
    rows = [
        OperationsTableRowModel(
            id=text(event.cursor or event.id, ""),
            cells={
                "time": format_datetime_utc(coerce_utc_datetime(event.occurred_at)),
                "event": short_event_name(event.event_name),
                "entity": text(event.entity_id),
                "status": status_label(event.status),
                "details": event_details(event.payload),
                "trace": text(event.trace_id),
            },
            status=event.status,
            tone=event_tone(event),
        )
        for event in filtered[:120]
    ]
    return OperationsTableSectionModel(
        id="recent_retrieval_logs",
        title="Recent Retrieval Logs",
        columns=(
            OperationsTableColumnModel("time", "Time"),
            OperationsTableColumnModel("event", "Event"),
            OperationsTableColumnModel("entity", "Entity"),
            OperationsTableColumnModel("status", "Status"),
            OperationsTableColumnModel("details", "Details"),
            OperationsTableColumnModel("trace", "Trace"),
        ),
        rows=tuple(rows),
        total=len(filtered),
        empty_state="No memory retrieval events.",
    )
