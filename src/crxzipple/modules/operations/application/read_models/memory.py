from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from crxzipple.modules.operations.application.observation import (
    OperationsObservedEvent,
    observed_event_from_record,
)
from crxzipple.modules.operations.application.read_models.models import (
    MetricCardModel,
    OperationsChartSectionModel,
    OperationsChartSegmentModel,
    OperationsKeyValueItemModel,
    OperationsModuleOverview,
    OperationsModuleRoleModel,
    OperationsTabModel,
    OperationsTableColumnModel,
    OperationsTableRowModel,
    OperationsTableSectionModel,
    RuntimeActionModel,
)
from crxzipple.shared.time import coerce_utc_datetime, format_datetime_utc

_MAX_MEMORY_EVENT_TOPICS = 160
_MAX_RECENT_MEMORY_EVENTS = 240
_RECENT_MEMORY_TOPIC_LIMIT = 80


@dataclass(frozen=True, slots=True)
class MemoryOperationsQuery:
    agent_id: str = ""
    kind: str = "all"
    search: str = ""
    limit: int = 80
    offset: int = 0


@dataclass(frozen=True, slots=True)
class MemoryFileDetailModel:
    file_id: str
    title: str
    status: str
    tone: str
    summary: tuple[OperationsKeyValueItemModel, ...]
    excerpt: str
    related: OperationsTableSectionModel
    raw_payload: dict[str, Any]


def defer_memory_file_details_payload(payload: dict[str, Any]) -> None:
    payload["file_details"] = []


@dataclass(frozen=True, slots=True)
class MemoryOperationsPage:
    module: str
    title: str
    subtitle: str
    health: str
    updated_at: str
    auto_refresh: bool
    role: OperationsModuleRoleModel
    metrics: tuple[MetricCardModel, ...]
    tabs: tuple[OperationsTabModel, ...]
    active_tab: str
    actions: tuple[RuntimeActionModel, ...]
    memory_stores: OperationsTableSectionModel
    context_resolution: OperationsTableSectionModel
    index_health: OperationsChartSectionModel
    index_jobs: OperationsTableSectionModel
    index_sync_activity: OperationsTableSectionModel
    retrieval_performance: OperationsChartSectionModel
    retrieval_trace: OperationsTableSectionModel
    write_flush: OperationsTableSectionModel
    memory_usage: OperationsTableSectionModel
    recent_retrieval_logs: OperationsTableSectionModel
    source_scan_status: OperationsTableSectionModel
    source_files: OperationsTableSectionModel
    file_details: tuple[MemoryFileDetailModel, ...]


@dataclass(frozen=True, slots=True)
class _MemoryContextRecord:
    agent_id: str
    agent_name: str
    enabled: bool
    scope_ref: str
    storage_root: str
    retrieval_backend: str
    files: tuple[Any, ...]
    indexed_file_count: int
    index_db_path: str
    index_db_exists: bool
    dirty: bool
    error: str = ""


@dataclass(slots=True)
class MemoryOperationsReadModelProvider:
    agent_service: Any | None
    memory_query_service: Any | None
    memory_watch_registry: Any | None = None
    events_service: Any | None = None
    event_definition_registry: Any | None = None
    operations_observation: Any | None = None

    def overview(self) -> OperationsModuleOverview:
        page = self.page(MemoryOperationsQuery(limit=40))
        return OperationsModuleOverview(
            module=page.module,
            title=page.title,
            subtitle=page.subtitle,
            health=page.health,
            updated_at=page.updated_at,
            metrics=page.metrics,
            queue=_overview_rows(page.source_files),
            lane_locks=_overview_rows(page.memory_stores),
            executor=_overview_rows(page.index_jobs),
            actions=page.actions,
        )

    def page(
        self,
        query: MemoryOperationsQuery | None = None,
    ) -> MemoryOperationsPage:
        query = _normalize_query(query)
        now = datetime.now(timezone.utc)
        profiles = _safe_tuple(self.agent_service, "list_profiles")
        selected_profile = _select_profile(profiles, query.agent_id)
        selected_agent_id = _text(getattr(selected_profile, "id", "") or query.agent_id, "")
        records = _context_records(
            profiles=profiles,
            provider=self,
            selected_agent_id=selected_agent_id,
        )
        selected_record = _record_for_agent(records, selected_agent_id)
        selected_files = selected_record.files if selected_record else ()
        filtered_files = _filter_files(selected_files, query)
        visible_files = filtered_files[query.offset : query.offset + query.limit]
        events = _recent_memory_events(
            operations_observation=self.operations_observation,
            events_service=self.events_service,
            definition_registry=self.event_definition_registry,
        )
        search_hits = _search_hits(
            self.memory_query_service,
            agent_id=selected_record.agent_id if selected_record else "",
            query=query.search,
            limit=min(query.limit, 50),
        )
        watch_metrics = _watch_metrics(self.memory_watch_registry)
        health = _health(
            service_available=self.memory_query_service is not None,
            selected_record=selected_record,
            records=records,
            watch_metrics=watch_metrics,
            events=events,
        )
        memory_stores = _memory_stores_table(records)
        source_files = _source_files_table(
            files=visible_files,
            total=len(filtered_files),
            record=selected_record,
        )
        index_jobs = _index_jobs_table(records)
        context_resolution = _context_resolution_table(records, events)
        index_sync_activity = _index_sync_activity_table(events)
        retrieval_trace = _retrieval_trace_table(
            search_hits=search_hits,
            query=query.search,
        )
        write_flush = _write_flush_table(events)
        retrieval_logs = _retrieval_logs_table(events)

        return MemoryOperationsPage(
            module="memory",
            title="Memory",
            subtitle="观察文件存储记忆空间、记忆文件、索引同步、检索与写入事件的运维视图。",
            health=health,
            updated_at=format_datetime_utc(now),
            auto_refresh=True,
            role=OperationsModuleRoleModel(
                label="Memory operator",
                can_operate=True,
                scope="memory",
            ),
            metrics=_metrics(
                health=health,
                records=records,
                selected_record=selected_record,
                filtered_files=filtered_files,
                search_hits=search_hits,
                watch_metrics=watch_metrics,
                events=events,
            ),
            tabs=_tabs(
                stores=memory_stores.total,
                context=context_resolution.total,
                files=len(filtered_files),
                index=index_jobs.total,
                sync=index_sync_activity.total,
                retrieval=retrieval_trace.total,
                writes=write_flush.total,
                usage=len(_usage_rows(selected_files)),
                scans=len(records),
                events=len(events),
            ),
            active_tab="files",
            actions=_actions(selected_agent_id),
            memory_stores=memory_stores,
            context_resolution=context_resolution,
            index_health=_index_health(records, watch_metrics),
            index_jobs=index_jobs,
            index_sync_activity=index_sync_activity,
            retrieval_performance=_retrieval_performance(records, search_hits, query.search),
            retrieval_trace=retrieval_trace,
            write_flush=write_flush,
            memory_usage=_memory_usage_table(selected_files, selected_record),
            recent_retrieval_logs=retrieval_logs,
            source_scan_status=_source_scan_table(records, watch_metrics),
            source_files=source_files,
            file_details=_file_details(
                visible_files,
                record=selected_record,
                memory_query_service=self.memory_query_service,
                events=events,
            ),
        )


def _normalize_query(
    query: MemoryOperationsQuery | None,
) -> MemoryOperationsQuery:
    if query is None:
        return MemoryOperationsQuery()
    return MemoryOperationsQuery(
        agent_id=query.agent_id.strip() if isinstance(query.agent_id, str) else "",
        kind=_normalized_filter(query.kind),
        search=query.search.strip() if isinstance(query.search, str) else "",
        limit=max(1, min(int(query.limit), 200)),
        offset=max(0, int(query.offset)),
    )


def _context_records(
    *,
    profiles: tuple[Any, ...],
    provider: MemoryOperationsReadModelProvider,
    selected_agent_id: str,
) -> tuple[_MemoryContextRecord, ...]:
    records: list[_MemoryContextRecord] = []
    profile_ids = {_text(getattr(profile, "id", ""), "") for profile in profiles}
    if selected_agent_id and selected_agent_id not in profile_ids:
        profiles = (
            *profiles,
            _AdHocProfile(selected_agent_id),
        )
    for profile in profiles:
        agent_id = _text(getattr(profile, "id", ""), "")
        if not agent_id:
            continue
        agent_name = _text(getattr(profile, "name", None) or agent_id)
        enabled = bool(getattr(profile, "enabled", True))
        inventory = _agent_scope_inventory(provider.memory_query_service, agent_id)
        if inventory is None or _text(getattr(inventory, "error", ""), ""):
            records.append(
                _MemoryContextRecord(
                    agent_id=agent_id,
                    agent_name=agent_name,
                    enabled=enabled,
                    scope_ref=_text(getattr(inventory, "scope_ref", ""), ""),
                    storage_root=_text(getattr(inventory, "storage_root", ""), ""),
                    retrieval_backend=_text(getattr(inventory, "retrieval_backend", ""), ""),
                    files=(),
                    indexed_file_count=0,
                    index_db_path=_text(getattr(inventory, "index_db_path", "-"), "-"),
                    index_db_exists=False,
                    dirty=bool(getattr(inventory, "dirty", False)),
                    error=_text(
                        getattr(inventory, "error", ""),
                        "memory context is not resolved",
                    ),
                )
            )
            continue
        records.append(
            _MemoryContextRecord(
                agent_id=agent_id,
                agent_name=agent_name,
                enabled=enabled,
                scope_ref=_text(getattr(inventory, "scope_ref", ""), ""),
                storage_root=_text(getattr(inventory, "storage_root", ""), ""),
                retrieval_backend=_text(getattr(inventory, "retrieval_backend", ""), ""),
                files=tuple(getattr(inventory, "files", ()) or ()),
                indexed_file_count=int(getattr(inventory, "indexed_file_count", 0) or 0),
                index_db_path=_text(getattr(inventory, "index_db_path", "-"), "-"),
                index_db_exists=bool(getattr(inventory, "index_db_exists", False)),
                dirty=bool(getattr(inventory, "dirty", False)),
            )
        )
    return tuple(records)


def _agent_scope_inventory(memory_query_service: Any | None, agent_id: str) -> Any | None:
    inventory = getattr(memory_query_service, "agent_scope_inventory", None)
    if not callable(inventory):
        return None
    try:
        return inventory(agent_id, file_limit=240)
    except Exception:
        return None


def _search_hits(
    memory_query_service: Any | None,
    *,
    agent_id: str,
    query: str,
    limit: int,
) -> tuple[Any, ...]:
    if not agent_id or not query:
        return ()
    search = getattr(memory_query_service, "search_agent", None)
    if not callable(search):
        return ()
    try:
        return tuple(search(agent_id, query=query, limit=limit))
    except Exception:
        return ()


def _watch_metrics(registry: Any | None) -> Any | None:
    snapshot_metrics = getattr(registry, "snapshot_metrics", None)
    if not callable(snapshot_metrics):
        return None
    try:
        return snapshot_metrics()
    except Exception:
        return None


def _safe_tuple(service: Any | None, method_name: str) -> tuple[Any, ...]:
    method = getattr(service, method_name, None)
    if not callable(method):
        return ()
    try:
        return tuple(method() or ())
    except Exception:
        return ()


def _recent_memory_events(
    *,
    operations_observation: Any | None,
    events_service: Any | None,
    definition_registry: Any | None,
) -> tuple[OperationsObservedEvent, ...]:
    return _dedupe_memory_events(
        (
            *_recent_memory_events_from_bus(
                events_service,
                definition_registry=definition_registry,
            ),
            *_recent_memory_events_from_observation(operations_observation),
        )
    )


def _recent_memory_events_from_observation(
    operations_observation: Any | None,
) -> tuple[OperationsObservedEvent, ...]:
    get_module_observation = getattr(operations_observation, "get_module_observation", None)
    if not callable(get_module_observation):
        return ()
    try:
        observation = get_module_observation("memory")
    except Exception:
        return ()
    return tuple(
        item
        for item in tuple(getattr(observation, "recent_events", ()) or ())
        if isinstance(item, OperationsObservedEvent)
    )


def _recent_memory_events_from_bus(
    events_service: Any | None,
    *,
    definition_registry: Any | None,
) -> tuple[OperationsObservedEvent, ...]:
    if events_service is None:
        return ()
    topics = tuple(
        topic
        for topic in _safe_list_event_topics(events_service)
        if _is_memory_event_topic(topic)
    )[:_MAX_MEMORY_EVENT_TOPICS]
    read_recent = getattr(events_service, "read_recent_event_topic", None)
    if not callable(read_recent):
        return ()
    events: list[OperationsObservedEvent] = []
    for topic in topics:
        try:
            records = tuple(read_recent(topic, limit=_RECENT_MEMORY_TOPIC_LIMIT) or ())
        except Exception:
            continue
        for record in records:
            try:
                observed = observed_event_from_record(
                    record,
                    definition_registry=definition_registry,
                )
            except Exception:
                continue
            if _is_memory_observed_event(observed):
                events.append(observed)
    events.sort(key=lambda event: coerce_utc_datetime(event.occurred_at), reverse=True)
    return tuple(events[:_MAX_RECENT_MEMORY_EVENTS])


def _safe_list_event_topics(events_service: Any) -> tuple[str, ...]:
    list_topics = getattr(events_service, "list_event_topics", None)
    if not callable(list_topics):
        return ()
    try:
        return tuple(str(topic) for topic in list_topics() or () if str(topic))
    except Exception:
        return ()


def _is_memory_event_topic(topic: str) -> bool:
    normalized = topic.strip().lower()
    return (
        normalized.startswith("memory.")
        or normalized.startswith("events.named.memory.")
    )


def _is_memory_observed_event(event: OperationsObservedEvent) -> bool:
    owner = event.owner.strip().lower()
    module = event.module.strip().lower()
    event_name = event.event_name.strip().lower()
    return owner == "memory" or module == "memory" or event_name.startswith("memory.")


def _dedupe_memory_events(
    events: tuple[OperationsObservedEvent, ...],
) -> tuple[OperationsObservedEvent, ...]:
    result: list[OperationsObservedEvent] = []
    seen: set[tuple[str, str]] = set()
    for event in sorted(
        events,
        key=lambda item: coerce_utc_datetime(item.occurred_at),
        reverse=True,
    ):
        key = (event.topic, event.cursor or event.id)
        if key in seen:
            continue
        seen.add(key)
        result.append(event)
    return tuple(result[:_MAX_RECENT_MEMORY_EVENTS])


def _health(
    *,
    service_available: bool,
    selected_record: _MemoryContextRecord | None,
    records: tuple[_MemoryContextRecord, ...],
    watch_metrics: Any | None,
    events: tuple[OperationsObservedEvent, ...],
) -> str:
    if not service_available:
        return "error"
    if selected_record is None or not _record_resolved(selected_record):
        return "warning"
    if any(item.error for item in records):
        return "warning"
    if _watch_failures(watch_metrics) > 0:
        return "warning"
    if any(event.level == "error" or event.status in {"failed", "error"} for event in events):
        return "warning"
    return "healthy"


def _metrics(
    *,
    health: str,
    records: tuple[_MemoryContextRecord, ...],
    selected_record: _MemoryContextRecord | None,
    filtered_files: tuple[Any, ...],
    search_hits: tuple[Any, ...],
    watch_metrics: Any | None,
    events: tuple[OperationsObservedEvent, ...],
) -> tuple[MetricCardModel, ...]:
    resolved = sum(1 for item in records if _record_resolved(item))
    indexed = selected_record.indexed_file_count if selected_record else 0
    total_files = len(filtered_files)
    failures = _watch_failures(watch_metrics)
    event_errors = sum(1 for event in events if event.level == "error" or event.status in {"failed", "error"})
    stale_indexes = sum(
        1 for record in records if _index_status(record) in {"Dirty", "Missing Index"}
    )
    rebuilds = sum(
        1
        for event in events
        if event.event_name == "memory.index.sync_succeeded"
        and bool(event.payload.get("force"))
    )
    credential_blocked = _credential_readiness_blocked(events)
    return (
        MetricCardModel("health", "Overall Health", _health_label(health), _health_delta(health), _health_tone(health)),
        MetricCardModel("memory_stores", "Memory Stores", str(resolved), f"{len(records)} agents", "info" if resolved else "warning"),
        MetricCardModel("source_documents", "Source Documents", str(total_files), "selected memory files", "info" if total_files else "neutral"),
        MetricCardModel("indexed_files", "Indexed Files", str(indexed), "files present in index store", "success" if indexed >= total_files and total_files else "neutral"),
        MetricCardModel("retrieval_hits", "Retrieval Hits", str(len(search_hits)), "current retrieval trace query", "info" if search_hits else "neutral"),
        MetricCardModel("stale_indexes", "Stale Indexes", str(stale_indexes), "dirty or missing indexes", "warning" if stale_indexes else "success"),
        MetricCardModel("rebuilds", "Rebuilds", str(rebuilds), "forced index sync events", "info" if rebuilds else "neutral"),
        MetricCardModel("credential_readiness", "Credential Readiness", "Blocked" if credential_blocked else "Ready", "memory engine credential checks", "danger" if credential_blocked else "success"),
        MetricCardModel("watch_failures", "Watch Failures", str(failures + event_errors), "watcher and observed memory errors", "danger" if failures + event_errors else "success"),
    )


def _tabs(
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


def _credential_readiness_blocked(
    events: tuple[OperationsObservedEvent, ...],
) -> bool:
    readiness_events = tuple(
        event
        for event in events
        if event.event_name.startswith("memory.engine.readiness_")
    )
    if not readiness_events:
        return False
    latest = max(readiness_events, key=lambda event: coerce_utc_datetime(event.occurred_at))
    status = _text(
        latest.payload.get("readiness_status")
        or latest.status,
        "",
    ).lower()
    requires_credentials = bool(latest.payload.get("requires_credentials"))
    if latest.event_name == "memory.engine.readiness_failed":
        return True
    return requires_credentials and status not in {"ready", "succeeded", "observed"}


def _actions(agent_id: str) -> tuple[RuntimeActionModel, ...]:
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
            endpoint=f"/operations/memory{suffix}&search={{query}}" if suffix else "/operations/memory?search={query}",
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


def _memory_stores_table(
    records: tuple[_MemoryContextRecord, ...],
) -> OperationsTableSectionModel:
    rows = [
        OperationsTableRowModel(
            id=record.agent_id,
            cells={
                "agent": record.agent_id,
                "space_id": record.scope_ref or "-",
                "backend": "file-backed",
                "status": _record_status(record),
                "files": str(len(record.files)),
                "indexed_files": str(record.indexed_file_count),
                "retrieval_backend": record.retrieval_backend or "-",
                "watcher": "Watching" if _record_resolved(record) else "-",
                "storage_root": _short(record.storage_root or "-", 80),
            },
            status=_record_status(record),
            tone=_record_tone(record),
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


def _context_resolution_table(
    records: tuple[_MemoryContextRecord, ...],
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
            id=_text(event.cursor or event.id, ""),
            cells={
                "time": format_datetime_utc(coerce_utc_datetime(event.occurred_at)),
                "agent": _text(event.payload.get("agent_id") or event.payload.get("space_ref")),
                "space_id": _text(event.payload.get("space_id") or event.entity_id),
                "backend": _text(event.payload.get("retrieval_backend")),
                "status": _status_label(event.status),
                "reason": _event_details(event.payload),
                "storage_root": _short(event.payload.get("storage_root"), 72),
                "trace": _text(event.trace_id),
            },
            status=event.status,
            tone=_event_tone(event),
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
                    "status": "Resolved" if _record_resolved(record) else "Resolve Failed",
                    "reason": record.error or "Current Context",
                    "storage_root": _short(record.storage_root or "-", 72),
                    "trace": "-",
                },
                status="resolved" if _record_resolved(record) else "failed",
                tone="success" if _record_resolved(record) else "warning",
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


def _source_files_table(
    *,
    files: tuple[Any, ...],
    total: int,
    record: _MemoryContextRecord | None,
) -> OperationsTableSectionModel:
    rows = [
        OperationsTableRowModel(
            id=_file_id(record, item),
            cells={
                "file": _text(getattr(item, "path", "")),
                "title": _text(getattr(item, "title", "")),
                "kind": _kind_label(_text(getattr(item, "kind", ""))),
                "status": "Indexed" if _file_is_indexed(record, item) else "File Only",
                "size": _file_size(record, item),
                "updated_at": _text(getattr(item, "updated_at", "")),
                "preview": _short(getattr(item, "preview", ""), 120),
                "action": "Open",
            },
            status="Indexed" if _file_is_indexed(record, item) else "File Only",
            tone="success" if _file_is_indexed(record, item) else "neutral",
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


def _index_jobs_table(
    records: tuple[_MemoryContextRecord, ...],
) -> OperationsTableSectionModel:
    rows = []
    for record in records:
        source_count = len(record.files)
        status = _index_status(record)
        rows.append(
            OperationsTableRowModel(
                id=f"index:{record.agent_id}",
                cells={
                    "job": f"memory-sync:{record.agent_id}",
                    "agent": record.agent_id,
                    "status": status,
                    "progress": _progress(record.indexed_file_count, source_count),
                    "source_files": str(source_count),
                    "indexed_files": str(record.indexed_file_count),
                    "index_db": _short(record.index_db_path, 72),
                    "updated_at": _index_updated_at(record.index_db_path),
                },
                status=status,
                tone=_index_tone(status),
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


def _index_sync_activity_table(
    events: tuple[OperationsObservedEvent, ...],
) -> OperationsTableSectionModel:
    filtered = tuple(
        event
        for event in events
        if event.event_name.startswith("memory.index.")
    )
    rows = [
        OperationsTableRowModel(
            id=_text(event.cursor or event.id, ""),
            cells={
                "time": format_datetime_utc(coerce_utc_datetime(event.occurred_at)),
                "operation": _short_event_name(event.event_name),
                "space_id": _text(event.payload.get("space_id") or event.entity_id),
                "status": _status_label(event.status),
                "changed": _text(event.payload.get("changed_path_count") or event.payload.get("changed_paths") or "-"),
                "reindexed": _text(event.payload.get("reindexed_files") or "-"),
                "chunks": _text(event.payload.get("chunk_count") or "-"),
                "duration": _duration_label_from_ms(event.payload.get("duration_ms")),
                "reason": _event_details(event.payload),
            },
            status=event.status,
            tone=_event_tone(event),
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


def _retrieval_trace_table(
    *,
    search_hits: tuple[Any, ...],
    query: str,
) -> OperationsTableSectionModel:
    rows = [
        OperationsTableRowModel(
            id=f"hit:{index}:{_text(getattr(hit, 'path', ''))}",
            cells={
                "rank": str(index + 1),
                "result": _text(getattr(getattr(hit, "item", None), "title", None) or getattr(hit, "path", "")),
                "score": f"{float(getattr(hit, 'score', 0.0)):.3f}",
                "kind": _kind_label(_text(getattr(hit, "kind", ""))),
                "file": _text(getattr(hit, "path", "")),
                "lines": f"{_text(getattr(hit, 'start_line', ''))}-{_text(getattr(hit, 'end_line', ''))}",
                "snippet": _short(getattr(hit, "snippet", ""), 140),
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
        empty_state="Set a search query to run retrieval trace." if not query else "No retrieval hits.",
    )


def _write_flush_table(
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
            id=_text(event.cursor or event.id, ""),
            cells={
                "time": format_datetime_utc(coerce_utc_datetime(event.occurred_at)),
                "operation": _short_event_name(event.event_name),
                "file": _text(event.payload.get("path") or event.entity_id),
                "status": _status_label(event.status),
                "details": _event_details(event.payload),
                "trace": _text(event.trace_id),
            },
            status=event.status,
            tone=_event_tone(event),
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


def _retrieval_logs_table(
    events: tuple[OperationsObservedEvent, ...],
) -> OperationsTableSectionModel:
    filtered = tuple(
        event
        for event in events
        if any(token in event.event_name.lower() for token in ("search", "retrieval", "recall", "memory"))
    )
    rows = [
        OperationsTableRowModel(
            id=_text(event.cursor or event.id, ""),
            cells={
                "time": format_datetime_utc(coerce_utc_datetime(event.occurred_at)),
                "event": _short_event_name(event.event_name),
                "entity": _text(event.entity_id),
                "status": _status_label(event.status),
                "details": _event_details(event.payload),
                "trace": _text(event.trace_id),
            },
            status=event.status,
            tone=_event_tone(event),
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


def _memory_usage_table(
    files: tuple[Any, ...],
    record: _MemoryContextRecord | None,
) -> OperationsTableSectionModel:
    rows = [
        OperationsTableRowModel(
            id=f"usage:{item['kind']}",
            cells={
                "kind": _kind_label(item["kind"]),
                "files": str(item["files"]),
                "size": _format_bytes(item["bytes"]),
                "latest_updated": item["latest_updated"],
                "percent": _percent(item["bytes"], max(sum(row["bytes"] for row in _usage_rows(files)), 1)),
            },
            status="Ready",
            tone="info",
        )
        for item in _usage_rows(files, record=record)
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


def _source_scan_table(
    records: tuple[_MemoryContextRecord, ...],
    watch_metrics: Any | None,
) -> OperationsTableSectionModel:
    rows = [
        OperationsTableRowModel(
            id=f"scan:{record.agent_id}",
            cells={
                "source": _short(record.storage_root or "-", 80),
                "agent": record.agent_id,
                "type": "directory",
                "status": _record_status(record),
                "files": str(len(record.files)),
                "watcher": _watcher_label(record, watch_metrics),
                "last": _latest_file_update(record.files),
                "next": "-",
            },
            status=_record_status(record),
            tone=_record_tone(record),
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


def _index_health(
    records: tuple[_MemoryContextRecord, ...],
    watch_metrics: Any | None,
) -> OperationsChartSectionModel:
    counts = Counter(_index_status(record) for record in records)
    failures = _watch_failures(watch_metrics)
    segments = [
        OperationsChartSegmentModel("ready", "Ready", counts["Ready"], "success"),
        OperationsChartSegmentModel("dirty", "Dirty", counts["Dirty"], "warning"),
        OperationsChartSegmentModel("missing_index", "Missing Index", counts["Missing Index"], "neutral"),
        OperationsChartSegmentModel("no_context", "No Context", counts["No Context"], "warning"),
    ]
    if failures:
        segments.append(OperationsChartSegmentModel("watch_failures", "Watch Failures", failures, "danger"))
    return OperationsChartSectionModel(
        "index_health",
        "Index Health",
        "donut",
        sum(item.value for item in segments),
        tuple(item for item in segments if item.value),
    )


def _retrieval_performance(
    records: tuple[_MemoryContextRecord, ...],
    search_hits: tuple[Any, ...],
    query: str,
) -> OperationsChartSectionModel:
    if query:
        segments = (
            OperationsChartSegmentModel("hits", "Hits", len(search_hits), "success" if search_hits else "neutral"),
            OperationsChartSegmentModel("misses", "Misses", 0 if search_hits else 1, "warning" if not search_hits else "neutral"),
        )
        return OperationsChartSectionModel("retrieval_performance", "Current Retrieval Trace", "donut", max(len(search_hits), 1), segments)
    counts = Counter(
        record.retrieval_backend or "unknown"
        for record in records
        if _record_resolved(record)
    )
    return OperationsChartSectionModel(
        "retrieval_performance",
        "Retrieval Backend Mix",
        "donut",
        sum(counts.values()),
        tuple(
            OperationsChartSegmentModel(key, _status_label(key), value, _backend_tone(key))
            for key, value in sorted(counts.items())
        ),
    )


def _file_details(
    files: tuple[Any, ...],
    *,
    record: _MemoryContextRecord | None,
    memory_query_service: Any | None,
    events: tuple[OperationsObservedEvent, ...],
) -> tuple[MemoryFileDetailModel, ...]:
    details: list[MemoryFileDetailModel] = []
    for item in files[:80]:
        file_id = _file_id(record, item)
        path = _text(getattr(item, "path", ""))
        excerpt = _excerpt_text(memory_query_service, record=record, path=path)
        details.append(
            MemoryFileDetailModel(
                file_id=file_id,
                title=_text(getattr(item, "title", "") or path),
                status="Indexed" if _file_is_indexed(record, item) else "File Only",
                tone="success" if _file_is_indexed(record, item) else "neutral",
                summary=(
                    OperationsKeyValueItemModel("File", path),
                    OperationsKeyValueItemModel("Title", _text(getattr(item, "title", ""))),
                    OperationsKeyValueItemModel("Kind", _kind_label(_text(getattr(item, "kind", "")))),
                    OperationsKeyValueItemModel("Status", "Indexed" if _file_is_indexed(record, item) else "File Only"),
                    OperationsKeyValueItemModel("Updated At", _text(getattr(item, "updated_at", ""))),
                    OperationsKeyValueItemModel("Size", _file_size(record, item)),
                    OperationsKeyValueItemModel("Agent", record.agent_id if record else "-"),
                    OperationsKeyValueItemModel("Space ID", record.scope_ref if record else "-"),
                ),
                excerpt=excerpt,
                related=_events_for_file_table(events, path),
                raw_payload={
                    "file": {
                        "path": path,
                        "kind": _text(getattr(item, "kind", "")),
                        "title": _text(getattr(item, "title", "")),
                        "preview": _text(getattr(item, "preview", "")),
                        "updated_at": _text(getattr(item, "updated_at", "")),
                    },
                    "context": _context_payload(record),
                },
            )
        )
    return tuple(details)


def _events_for_file_table(
    events: tuple[OperationsObservedEvent, ...],
    path: str,
) -> OperationsTableSectionModel:
    filtered = tuple(
        event
        for event in events
        if event.entity_id == path or _text(event.payload.get("path"), "") == path
    )
    rows = [
        OperationsTableRowModel(
            id=_text(event.cursor or event.id, ""),
            cells={
                "time": format_datetime_utc(coerce_utc_datetime(event.occurred_at)),
                "event": _short_event_name(event.event_name),
                "status": _status_label(event.status),
                "details": _event_details(event.payload),
            },
            status=event.status,
            tone=_event_tone(event),
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


def _filter_files(
    files: tuple[Any, ...],
    query: MemoryOperationsQuery,
) -> tuple[Any, ...]:
    needle = query.search.lower()
    filtered: list[Any] = []
    for item in files:
        kind = _normalized_filter(getattr(item, "kind", ""))
        if query.kind != "all" and kind != query.kind:
            continue
        if needle and needle not in _file_search_blob(item):
            continue
        filtered.append(item)
    filtered.sort(key=lambda item: (_text(getattr(item, "updated_at", "")), _text(getattr(item, "path", ""))), reverse=True)
    return tuple(filtered)


def _usage_rows(
    files: tuple[Any, ...],
    *,
    record: _MemoryContextRecord | None = None,
) -> tuple[dict[str, Any], ...]:
    by_kind: dict[str, dict[str, Any]] = {}
    for item in files:
        kind = _text(getattr(item, "kind", ""), "unknown")
        row = by_kind.setdefault(kind, {"kind": kind, "files": 0, "bytes": 0, "latest_updated": "-"})
        row["files"] += 1
        row["bytes"] += _file_size_bytes(record, item)
        updated_at = _text(getattr(item, "updated_at", ""), "")
        if updated_at and (row["latest_updated"] == "-" or updated_at > row["latest_updated"]):
            row["latest_updated"] = updated_at
    return tuple(by_kind[key] for key in sorted(by_kind))


def _record_for_agent(
    records: tuple[_MemoryContextRecord, ...],
    agent_id: str,
) -> _MemoryContextRecord | None:
    if agent_id:
        for record in records:
            if record.agent_id == agent_id or record.scope_ref == agent_id:
                return record
    return next((record for record in records if _record_resolved(record)), records[0] if records else None)


def _select_profile(profiles: tuple[Any, ...], agent_id: str) -> Any | None:
    if agent_id:
        return next((profile for profile in profiles if getattr(profile, "id", None) == agent_id), None)
    for preferred_id in ("crxzipple", "assistant"):
        for profile in profiles:
            if getattr(profile, "id", None) == preferred_id:
                return profile
    return next((profile for profile in profiles if getattr(profile, "enabled", True)), profiles[0] if profiles else None)


def _overview_rows(section: OperationsTableSectionModel) -> tuple[dict[str, str], ...]:
    return tuple(dict(row.cells) for row in section.rows[:80])


def _record_status(record: _MemoryContextRecord) -> str:
    if not _record_resolved(record):
        return "No Context"
    if record.dirty:
        return "Dirty"
    if record.files and not record.index_db_exists:
        return "Missing Index"
    return "Ready"


def _record_resolved(record: _MemoryContextRecord) -> bool:
    return not record.error and bool(record.scope_ref and record.storage_root)


def _record_tone(record: _MemoryContextRecord) -> str:
    status = _record_status(record)
    if status == "Ready":
        return "success"
    if status == "Missing Index":
        return "neutral"
    return "warning"


def _index_status(record: _MemoryContextRecord) -> str:
    return _record_status(record)


def _index_tone(status: str) -> str:
    if status == "Ready":
        return "success"
    if status == "No Context" or status == "Dirty":
        return "warning"
    return "neutral"


def _file_is_indexed(record: _MemoryContextRecord | None, item: Any) -> bool:
    if record is None:
        return False
    if record.indexed_file_count <= 0:
        return False
    # Index state is exposed as file count by the service contract; avoid leaking
    # persistence internals by treating the selected indexed set as a coverage signal.
    return record.indexed_file_count >= len(record.files)


def _file_id(record: _MemoryContextRecord | None, item: Any) -> str:
    space_id = record.scope_ref if record else "-"
    return f"{space_id}:{_text(getattr(item, 'path', ''))}"


def _file_size(record: _MemoryContextRecord | None, item: Any) -> str:
    return _format_bytes(_file_size_bytes(record, item))


def _file_size_bytes(record: _MemoryContextRecord | None, item: Any) -> int:
    root = record.storage_root if record is not None else ""
    path = _text(getattr(item, "path", ""), "")
    if not root or not path:
        return len(_text(getattr(item, "preview", ""), ""))
    try:
        target = (Path(root).expanduser() / path).resolve()
        return int(target.stat().st_size) if target.is_file() else 0
    except Exception:
        return len(_text(getattr(item, "preview", ""), ""))


def _excerpt_text(
    memory_query_service: Any | None,
    *,
    record: _MemoryContextRecord | None,
    path: str,
) -> str:
    if record is None or not _record_resolved(record) or not path:
        return ""
    get = getattr(memory_query_service, "get_agent_excerpt", None)
    if not callable(get):
        return ""
    try:
        excerpt = get(record.agent_id, path=path, start_line=1, line_count=60)
    except Exception:
        return ""
    return _text(getattr(excerpt, "text", ""), "")


def _context_payload(record: _MemoryContextRecord | None) -> dict[str, str]:
    if record is None or not _record_resolved(record):
        return {}
    return {
        "space_id": record.scope_ref,
        "storage_root": record.storage_root,
        "retrieval_backend": record.retrieval_backend,
    }


def _watch_failures(metrics: Any | None) -> int:
    if metrics is None:
        return 0
    return int(getattr(metrics, "filesystem_sync_failures", 0) or 0) + int(getattr(metrics, "interval_sync_failures", 0) or 0)


def _watcher_label(record: _MemoryContextRecord, metrics: Any | None) -> str:
    if not _record_resolved(record):
        return "-"
    if metrics is None:
        return "Not Configured"
    return f"{getattr(metrics, 'watched_contexts', 0)} contexts"


def _progress(indexed: int, total: int) -> str:
    if total <= 0:
        return "0%"
    return f"{round((indexed / total) * 100)}%"


def _index_updated_at(path: str) -> str:
    if not path or path == "-":
        return "-"
    try:
        target = Path(path)
        if not target.is_file():
            return "-"
        return format_datetime_utc(datetime.fromtimestamp(target.stat().st_mtime, timezone.utc))
    except Exception:
        return "-"


def _latest_file_update(files: tuple[Any, ...]) -> str:
    values = [_text(getattr(item, "updated_at", ""), "") for item in files]
    values = [item for item in values if item]
    return max(values) if values else "-"


def _file_search_blob(item: Any) -> str:
    return " ".join(
        (
            _text(getattr(item, "path", "")),
            _text(getattr(item, "title", "")),
            _text(getattr(item, "kind", "")),
            _text(getattr(item, "preview", "")),
        )
    ).lower()


def _event_details(payload: dict[str, Any]) -> str:
    for key in ("reason", "message", "summary", "error_message", "query", "path", "status"):
        value = payload.get(key)
        if value is not None and _text(value, ""):
            return _short(value, 120)
    return "-"


def _short_event_name(event_name: str) -> str:
    return event_name.removeprefix("memory.")


def _event_tone(event: OperationsObservedEvent) -> str:
    if event.level == "error" or event.status in {"failed", "error"}:
        return "danger"
    if event.level == "warning":
        return "warning"
    return "success" if event.status in {"ready", "success", "observed"} else "neutral"


def _kind_label(kind: str) -> str:
    mapping = {
        "long_term": "Long Term",
        "daily": "Daily",
        "archive": "Archive",
    }
    return mapping.get(kind, _status_label(kind))


def _backend_tone(backend: str) -> str:
    if backend == "vector":
        return "info"
    if backend == "hybrid":
        return "success"
    if backend == "keyword":
        return "neutral"
    return "warning"


def _health_label(health: str) -> str:
    if health == "error":
        return "Error"
    if health == "warning":
        return "Warning"
    return "Healthy"


def _health_delta(health: str) -> str:
    if health == "error":
        return "Memory service is not connected"
    if health == "warning":
        return "Memory context needs attention"
    return "Memory state is queryable"


def _health_tone(health: str) -> str:
    if health == "error":
        return "danger"
    if health == "warning":
        return "warning"
    return "success"


def _status_label(status: Any) -> str:
    text = _text(status, "unknown").replace("_", " ").replace("-", " ")
    return " ".join(part.capitalize() for part in text.split()) or "-"


def _normalized_filter(value: Any) -> str:
    text = _text(value, "all").strip().lower().replace(" ", "_").replace("-", "_")
    return text or "all"


def _format_bytes(size: int) -> str:
    units = ("B", "KB", "MB", "GB")
    value = float(max(size, 0))
    unit = units[0]
    for unit in units:
        if value < 1024 or unit == units[-1]:
            break
        value /= 1024
    if unit == "B":
        return f"{int(value)} B"
    return f"{value:.1f} {unit}"


def _duration_label_from_ms(value: Any) -> str:
    if isinstance(value, str) and value.strip():
        try:
            milliseconds = float(value)
        except ValueError:
            return value
    elif isinstance(value, (int, float)):
        milliseconds = float(value)
    else:
        return "-"
    if milliseconds < 1000:
        return f"{round(milliseconds)}ms"
    return f"{milliseconds / 1000:.2f}s"


def _percent(part: int, total: int) -> str:
    if total <= 0:
        return "0%"
    return f"{round((part / total) * 100, 1)}%"


def _short(value: Any, size: int = 80) -> str:
    text = _text(value)
    if len(text) <= size:
        return text
    return f"{text[: max(8, size - 8)]}...{text[-5:]}"


def _text(value: Any, default: str = "-") -> str:
    if value is None:
        return default
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, tuple, set)):
        return ", ".join(_text(item, "") for item in value if _text(item, ""))
    if isinstance(value, dict):
        return ", ".join(f"{key}={_text(item, '')}" for key, item in sorted(value.items()))
    text = str(value).strip()
    return text if text else default


class _AdHocProfile:
    def __init__(self, agent_id: str) -> None:
        self.id = agent_id
        self.name = agent_id
        self.enabled = True
