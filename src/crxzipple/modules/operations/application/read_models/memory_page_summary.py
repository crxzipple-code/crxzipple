from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.observation_models import OperationsObservedEvent
from crxzipple.modules.operations.application.read_models.memory_common import (
    health_delta,
    health_label,
    health_tone,
    index_status,
    record_resolved,
    watch_failures,
)
from crxzipple.modules.operations.application.read_models.memory_events import (
    credential_readiness_blocked,
)
from crxzipple.modules.operations.application.read_models.memory_models import (
    MemoryContextRecord,
)
from crxzipple.modules.operations.application.read_models.models import (
    MetricCardModel,
    OperationsTabModel,
    RuntimeActionModel,
)


def metrics(
    *,
    health: str,
    records: tuple[MemoryContextRecord, ...],
    selected_record: MemoryContextRecord | None,
    filtered_files: tuple[Any, ...],
    search_hits: tuple[Any, ...],
    watch_metrics: Any | None,
    events: tuple[OperationsObservedEvent, ...],
) -> tuple[MetricCardModel, ...]:
    resolved = sum(1 for item in records if record_resolved(item))
    indexed = selected_record.indexed_file_count if selected_record else 0
    total_files = len(filtered_files)
    failures = watch_failures(watch_metrics)
    event_errors = sum(
        1
        for event in events
        if event.level == "error" or event.status in {"failed", "error"}
    )
    stale_indexes = sum(
        1 for record in records if index_status(record) in {"Dirty", "Missing Index"}
    )
    rebuilds = sum(
        1
        for event in events
        if event.event_name == "memory.index.sync_succeeded"
        and bool(event.payload.get("force"))
    )
    credential_blocked = credential_readiness_blocked(events)
    return (
        MetricCardModel(
            "health",
            "Overall Health",
            health_label(health),
            health_delta(health),
            health_tone(health),
        ),
        MetricCardModel(
            "memory_stores",
            "Memory Stores",
            str(resolved),
            f"{len(records)} agents",
            "info" if resolved else "warning",
        ),
        MetricCardModel(
            "source_documents",
            "Source Documents",
            str(total_files),
            "selected memory files",
            "info" if total_files else "neutral",
        ),
        MetricCardModel(
            "indexed_files",
            "Indexed Files",
            str(indexed),
            "files present in index store",
            "success" if indexed >= total_files and total_files else "neutral",
        ),
        MetricCardModel(
            "retrieval_hits",
            "Retrieval Hits",
            str(len(search_hits)),
            "current retrieval trace query",
            "info" if search_hits else "neutral",
        ),
        MetricCardModel(
            "stale_indexes",
            "Stale Indexes",
            str(stale_indexes),
            "dirty or missing indexes",
            "warning" if stale_indexes else "success",
        ),
        MetricCardModel(
            "rebuilds",
            "Rebuilds",
            str(rebuilds),
            "forced index sync events",
            "info" if rebuilds else "neutral",
        ),
        MetricCardModel(
            "credential_readiness",
            "Credential Readiness",
            "Blocked" if credential_blocked else "Ready",
            "memory engine credential checks",
            "danger" if credential_blocked else "success",
        ),
        MetricCardModel(
            "watch_failures",
            "Watch Failures",
            str(failures + event_errors),
            "watcher and observed memory errors",
            "danger" if failures + event_errors else "success",
        ),
    )


def tabs(
    *,
    stores: int,
    context: int,
    files: int,
    index: int,
    sync: int,
    retrieval: int,
    writes: int,
    usage: int,
    scans: int,
    events: int,
) -> tuple[OperationsTabModel, ...]:
    return (
        OperationsTabModel("files", "Source Files", files),
        OperationsTabModel("stores", "Memory Stores", stores),
        OperationsTabModel("context", "Context Resolution", context),
        OperationsTabModel("index", "Index Jobs", index),
        OperationsTabModel("sync", "Index Sync Activity", sync),
        OperationsTabModel("retrieval", "Retrieval Trace", retrieval),
        OperationsTabModel("writes", "Write / Flush", writes),
        OperationsTabModel("usage", "Memory Usage", usage),
        OperationsTabModel("scan", "Source Scan Status", scans),
        OperationsTabModel("events", "Retrieval Logs", events),
    )


def actions(agent_id: str) -> tuple[RuntimeActionModel, ...]:
    suffix = f"?agent_id={agent_id}" if agent_id else ""
    return (
        RuntimeActionModel(
            id="open_memory_overview",
            label="Open Memory Overview",
            owner="memory",
            kind="navigation",
            method="GET",
            endpoint=f"/operations/memory{suffix}",
        ),
        RuntimeActionModel(
            id="search_memory",
            label="Search Memory",
            owner="memory",
            kind="navigation",
            method="GET",
            endpoint=(
                f"/operations/memory{suffix}&search={{query}}"
                if suffix
                else "/operations/memory?search={query}"
            ),
        ),
        RuntimeActionModel(
            id="write_long_term_memory",
            label="Write Long Term Memory",
            owner="memory",
            risk="controlled",
            audit_event="memory.long_term.write",
            method="POST",
            endpoint="/operations/memory/long-term",
        ),
    )
