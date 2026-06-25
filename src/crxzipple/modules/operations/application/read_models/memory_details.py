from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.observation_models import OperationsObservedEvent
from crxzipple.modules.operations.application.read_models.memory_common import (
    context_payload,
    kind_label,
    record_resolved,
)
from crxzipple.modules.operations.application.read_models.memory_file_helpers import (
    file_id,
    file_is_indexed,
    file_size,
)
from crxzipple.modules.operations.application.read_models.memory_values import (
    status_label,
    text,
)
from crxzipple.modules.operations.application.read_models.memory_events import (
    event_details,
    event_tone,
    short_event_name,
)
from crxzipple.modules.operations.application.read_models.memory_models import (
    MemoryContextRecord,
    MemoryFileDetailModel,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsKeyValueItemModel,
    OperationsTableColumnModel,
    OperationsTableRowModel,
    OperationsTableSectionModel,
)
from crxzipple.shared.time import coerce_utc_datetime, format_datetime_utc


def file_details(
    files: tuple[Any, ...],
    *,
    record: MemoryContextRecord | None,
    memory_query_service: Any | None,
    events: tuple[OperationsObservedEvent, ...],
) -> tuple[MemoryFileDetailModel, ...]:
    details: list[MemoryFileDetailModel] = []
    for item in files[:80]:
        item_file_id = file_id(record, item)
        path = text(getattr(item, "path", ""))
        excerpt = excerpt_text(memory_query_service, record=record, path=path)
        details.append(
            MemoryFileDetailModel(
                file_id=item_file_id,
                title=text(getattr(item, "title", "") or path),
                status="Indexed" if file_is_indexed(record, item) else "File Only",
                tone="success" if file_is_indexed(record, item) else "neutral",
                summary=(
                    OperationsKeyValueItemModel("File", path),
                    OperationsKeyValueItemModel("Title", text(getattr(item, "title", ""))),
                    OperationsKeyValueItemModel("Kind", kind_label(text(getattr(item, "kind", "")))),
                    OperationsKeyValueItemModel("Status", "Indexed" if file_is_indexed(record, item) else "File Only"),
                    OperationsKeyValueItemModel("Updated At", text(getattr(item, "updated_at", ""))),
                    OperationsKeyValueItemModel("Size", file_size(record, item)),
                    OperationsKeyValueItemModel("Agent", record.agent_id if record else "-"),
                    OperationsKeyValueItemModel("Space ID", record.scope_ref if record else "-"),
                ),
                excerpt=excerpt,
                related=events_for_file_table(events, path),
                raw_payload={
                    "file": {
                        "path": path,
                        "kind": text(getattr(item, "kind", "")),
                        "title": text(getattr(item, "title", "")),
                        "preview": text(getattr(item, "preview", "")),
                        "updated_at": text(getattr(item, "updated_at", "")),
                    },
                    "context": context_payload(record),
                },
            )
        )
    return tuple(details)


def events_for_file_table(
    events: tuple[OperationsObservedEvent, ...],
    path: str,
) -> OperationsTableSectionModel:
    filtered = tuple(
        event
        for event in events
        if event.entity_id == path or text(event.payload.get("path"), "") == path
    )
    rows = [
        OperationsTableRowModel(
            id=text(event.cursor or event.id, ""),
            cells={
                "time": format_datetime_utc(coerce_utc_datetime(event.occurred_at)),
                "event": short_event_name(event.event_name),
                "status": status_label(event.status),
                "details": event_details(event.payload),
            },
            status=event.status,
            tone=event_tone(event),
        )
        for event in filtered[:30]
    ]
    return OperationsTableSectionModel(
        id="related_events",
        title="Related Events",
        columns=(
            OperationsTableColumnModel("time", "Time"),
            OperationsTableColumnModel("event", "Event"),
            OperationsTableColumnModel("status", "Status"),
            OperationsTableColumnModel("details", "Details"),
        ),
        rows=tuple(rows),
        total=len(filtered),
        empty_state="No related events.",
    )


def excerpt_text(
    memory_query_service: Any | None,
    *,
    record: MemoryContextRecord | None,
    path: str,
) -> str:
    if record is None or not record_resolved(record) or not path:
        return ""
    get = getattr(memory_query_service, "get_agent_excerpt", None)
    if not callable(get):
        return ""
    try:
        excerpt = get(record.agent_id, path=path, start_line=1, line_count=60)
    except Exception:
        return ""
    return text(getattr(excerpt, "text", ""), "")
