from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.memory_common import (
    index_status,
    index_tone,
    index_updated_at,
    kind_label,
    progress,
    record_resolved,
    record_status,
    record_tone,
)
from crxzipple.modules.operations.application.read_models.memory_values import (
    format_bytes,
    percent,
    short,
)
from crxzipple.modules.operations.application.read_models.memory_models import (
    MemoryContextRecord,
)
from crxzipple.modules.operations.application.read_models.memory_records import (
    usage_rows,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableColumnModel,
    OperationsTableRowModel,
    OperationsTableSectionModel,
)


def memory_stores_table(
    records: tuple[MemoryContextRecord, ...],
) -> OperationsTableSectionModel:
    rows = [
        OperationsTableRowModel(
            id=record.agent_id,
            cells={
                "agent": record.agent_id,
                "space_id": record.scope_ref or "-",
                "backend": "file-backed",
                "status": record_status(record),
                "files": str(len(record.files)),
                "indexed_files": str(record.indexed_file_count),
                "retrieval_backend": record.retrieval_backend or "-",
                "watcher": "Watching" if record_resolved(record) else "-",
                "storage_root": short(record.storage_root or "-", 80),
            },
            status=record_status(record),
            tone=record_tone(record),
        )
        for record in records
    ]
    return OperationsTableSectionModel(
        id="memory_stores",
        title="Memory Stores",
        columns=(
            OperationsTableColumnModel("agent", "Agent"),
            OperationsTableColumnModel("space_id", "Space ID"),
            OperationsTableColumnModel("backend", "Backend"),
            OperationsTableColumnModel("status", "Status"),
            OperationsTableColumnModel("files", "Files"),
            OperationsTableColumnModel("indexed_files", "Indexed Files"),
            OperationsTableColumnModel("retrieval_backend", "Retrieval Backend"),
            OperationsTableColumnModel("watcher", "Watcher"),
            OperationsTableColumnModel("storage_root", "Storage Root"),
        ),
        rows=tuple(rows),
        total=len(rows),
        empty_state="No memory stores.",
    )


def index_jobs_table(
    records: tuple[MemoryContextRecord, ...],
) -> OperationsTableSectionModel:
    rows = []
    for record in records:
        source_count = len(record.files)
        status = index_status(record)
        rows.append(
            OperationsTableRowModel(
                id=f"index:{record.agent_id}",
                cells={
                    "job": f"memory-sync:{record.agent_id}",
                    "agent": record.agent_id,
                    "status": status,
                    "progress": progress(record.indexed_file_count, source_count),
                    "source_files": str(source_count),
                    "indexed_files": str(record.indexed_file_count),
                    "index_db": short(record.index_db_path, 72),
                    "updated_at": index_updated_at(record.index_db_path),
                },
                status=status,
                tone=index_tone(status),
            )
        )
    return OperationsTableSectionModel(
        id="index_jobs",
        title="Index Jobs",
        columns=(
            OperationsTableColumnModel("job", "Job"),
            OperationsTableColumnModel("agent", "Agent"),
            OperationsTableColumnModel("status", "Status"),
            OperationsTableColumnModel("progress", "Progress"),
            OperationsTableColumnModel("source_files", "Source Files"),
            OperationsTableColumnModel("indexed_files", "Indexed Files"),
            OperationsTableColumnModel("index_db", "Index DB"),
            OperationsTableColumnModel("updated_at", "Updated At"),
        ),
        rows=tuple(rows),
        total=len(rows),
        empty_state="No index state.",
    )


def memory_usage_table(
    files: tuple[Any, ...],
    record: MemoryContextRecord | None,
) -> OperationsTableSectionModel:
    rows = [
        OperationsTableRowModel(
            id=f"usage:{item['kind']}",
            cells={
                "kind": kind_label(item["kind"]),
                "files": str(item["files"]),
                "size": format_bytes(item["bytes"]),
                "latest_updated": item["latest_updated"],
                "percent": percent(
                    item["bytes"],
                    max(sum(row["bytes"] for row in usage_rows(files)), 1),
                ),
            },
            status="Ready",
            tone="info",
        )
        for item in usage_rows(files, record=record)
    ]
    return OperationsTableSectionModel(
        id="memory_usage",
        title="Memory Usage",
        columns=(
            OperationsTableColumnModel("kind", "Kind"),
            OperationsTableColumnModel("files", "Files"),
            OperationsTableColumnModel("size", "Size"),
            OperationsTableColumnModel("latest_updated", "Latest Updated"),
            OperationsTableColumnModel("percent", "Percent"),
        ),
        rows=tuple(rows),
        total=len(rows),
        empty_state="No memory usage.",
    )
