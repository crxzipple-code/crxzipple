from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.memory_common import (
    kind_label,
    record_status,
    record_tone,
    watcher_label,
)
from crxzipple.modules.operations.application.read_models.memory_file_helpers import (
    file_id,
    file_is_indexed,
    file_size,
    latest_file_update,
)
from crxzipple.modules.operations.application.read_models.memory_values import (
    short,
    text,
)
from crxzipple.modules.operations.application.read_models.memory_models import (
    MemoryContextRecord,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableColumnModel,
    OperationsTableRowModel,
    OperationsTableSectionModel,
)


def source_files_table(
    *,
    files: tuple[Any, ...],
    total: int,
    record: MemoryContextRecord | None,
) -> OperationsTableSectionModel:
    rows = [
        OperationsTableRowModel(
            id=file_id(record, item),
            cells={
                "file": text(getattr(item, "path", "")),
                "title": text(getattr(item, "title", "")),
                "kind": kind_label(text(getattr(item, "kind", ""))),
                "status": "Indexed" if file_is_indexed(record, item) else "File Only",
                "size": file_size(record, item),
                "updated_at": text(getattr(item, "updated_at", "")),
                "preview": short(getattr(item, "preview", ""), 120),
                "action": "Open",
            },
            status="Indexed" if file_is_indexed(record, item) else "File Only",
            tone="success" if file_is_indexed(record, item) else "neutral",
        )
        for item in files
    ]
    return OperationsTableSectionModel(
        id="source_files",
        title="Source Files",
        columns=(
            OperationsTableColumnModel("file", "File"),
            OperationsTableColumnModel("title", "Title"),
            OperationsTableColumnModel("kind", "Kind"),
            OperationsTableColumnModel("status", "Status"),
            OperationsTableColumnModel("size", "Size"),
            OperationsTableColumnModel("updated_at", "Updated At"),
            OperationsTableColumnModel("preview", "Preview"),
            OperationsTableColumnModel("action", "Action"),
        ),
        rows=tuple(rows),
        total=total,
        empty_state="No memory files.",
    )


def retrieval_trace_table(
    *,
    search_hits: tuple[Any, ...],
    query: str,
) -> OperationsTableSectionModel:
    rows = [
        OperationsTableRowModel(
            id=f"hit:{index}:{text(getattr(hit, 'path', ''))}",
            cells={
                "rank": str(index + 1),
                "result": text(
                    getattr(getattr(hit, "item", None), "title", None)
                    or getattr(hit, "path", "")
                ),
                "score": f"{float(getattr(hit, 'score', 0.0)):.3f}",
                "kind": kind_label(text(getattr(hit, "kind", ""))),
                "file": text(getattr(hit, "path", "")),
                "lines": (
                    f"{text(getattr(hit, 'start_line', ''))}-"
                    f"{text(getattr(hit, 'end_line', ''))}"
                ),
                "snippet": short(getattr(hit, "snippet", ""), 140),
            },
            status="Hit",
            tone="success",
        )
        for index, hit in enumerate(search_hits)
    ]
    return OperationsTableSectionModel(
        id="retrieval_trace",
        title="Retrieval Trace",
        columns=(
            OperationsTableColumnModel("rank", "Rank"),
            OperationsTableColumnModel("result", "Result"),
            OperationsTableColumnModel("score", "Score"),
            OperationsTableColumnModel("kind", "Kind"),
            OperationsTableColumnModel("file", "File"),
            OperationsTableColumnModel("lines", "Lines"),
            OperationsTableColumnModel("snippet", "Snippet"),
        ),
        rows=tuple(rows),
        total=len(rows),
        empty_state=(
            "Set a search query to run retrieval trace."
            if not query
            else "No retrieval hits."
        ),
    )


def source_scan_table(
    records: tuple[MemoryContextRecord, ...],
    watch_metrics: Any | None,
) -> OperationsTableSectionModel:
    rows = [
        OperationsTableRowModel(
            id=f"scan:{record.agent_id}",
            cells={
                "source": short(record.storage_root or "-", 80),
                "agent": record.agent_id,
                "type": "directory",
                "status": record_status(record),
                "files": str(len(record.files)),
                "watcher": watcher_label(record, watch_metrics),
                "last": latest_file_update(record.files),
                "next": "-",
            },
            status=record_status(record),
            tone=record_tone(record),
        )
        for record in records
    ]
    return OperationsTableSectionModel(
        id="source_scan_status",
        title="Source Scan Status",
        columns=(
            OperationsTableColumnModel("source", "Source"),
            OperationsTableColumnModel("agent", "Agent"),
            OperationsTableColumnModel("type", "Type"),
            OperationsTableColumnModel("status", "Status"),
            OperationsTableColumnModel("files", "Files"),
            OperationsTableColumnModel("watcher", "Watcher"),
            OperationsTableColumnModel("last", "Last Scanned"),
            OperationsTableColumnModel("next", "Next Scan"),
        ),
        rows=tuple(rows),
        total=len(rows),
        empty_state="No source scan state.",
    )
