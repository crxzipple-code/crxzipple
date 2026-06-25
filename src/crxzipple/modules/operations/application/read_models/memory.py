from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from crxzipple.modules.operations.application.read_models.memory_common import (
    overview_rows as _overview_rows,
)
from crxzipple.modules.operations.application.read_models.memory_details import (
    file_details as _file_details,
)
from crxzipple.modules.operations.application.read_models.memory_context_tables import (
    context_resolution_table as _context_resolution_table,
)
from crxzipple.modules.operations.application.read_models.memory_event_tables import (
    index_sync_activity_table as _index_sync_activity_table,
    retrieval_logs_table as _retrieval_logs_table,
    write_flush_table as _write_flush_table,
)
from crxzipple.modules.operations.application.read_models.memory_charts import (
    index_health as _index_health,
    retrieval_performance as _retrieval_performance,
)
from crxzipple.modules.operations.application.read_models.memory_page_summary import (
    actions as _actions,
    metrics as _metrics,
    tabs as _tabs,
)
from crxzipple.modules.operations.application.read_models.memory_models import (
    MemoryOperationsPage,
    MemoryOperationsQuery,
)
from crxzipple.modules.operations.application.read_models.memory_page_facts import (
    collect_memory_page_facts,
)
from crxzipple.modules.operations.application.read_models.memory_records import (
    usage_rows as _usage_rows,
)
from crxzipple.modules.operations.application.read_models.memory_tables import (
    index_jobs_table as _index_jobs_table,
    memory_stores_table as _memory_stores_table,
    memory_usage_table as _memory_usage_table,
)
from crxzipple.modules.operations.application.read_models.memory_source_tables import (
    retrieval_trace_table as _retrieval_trace_table,
    source_files_table as _source_files_table,
    source_scan_table as _source_scan_table,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsModuleOverview,
    OperationsModuleRoleModel,
)
from crxzipple.shared.time import format_datetime_utc


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
        facts = collect_memory_page_facts(
            query=query,
            agent_service=self.agent_service,
            memory_query_service=self.memory_query_service,
            memory_watch_registry=self.memory_watch_registry,
            events_service=self.events_service,
            event_definition_registry=self.event_definition_registry,
            operations_observation=self.operations_observation,
        )
        memory_stores = _memory_stores_table(facts.records)
        source_files = _source_files_table(
            files=facts.visible_files,
            total=len(facts.filtered_files),
            record=facts.selected_record,
        )
        index_jobs = _index_jobs_table(facts.records)
        context_resolution = _context_resolution_table(facts.records, facts.events)
        index_sync_activity = _index_sync_activity_table(facts.events)
        retrieval_trace = _retrieval_trace_table(
            search_hits=facts.search_hits,
            query=facts.query.search,
        )
        write_flush = _write_flush_table(facts.events)
        retrieval_logs = _retrieval_logs_table(facts.events)

        return MemoryOperationsPage(
            module="memory",
            title="Memory",
            subtitle="观察文件存储记忆空间、记忆文件、索引同步、检索与写入事件的运维视图。",
            health=facts.health,
            updated_at=format_datetime_utc(facts.now),
            auto_refresh=True,
            role=OperationsModuleRoleModel(
                label="Memory operator",
                can_operate=True,
                scope="memory",
            ),
            metrics=_metrics(
                health=facts.health,
                records=facts.records,
                selected_record=facts.selected_record,
                filtered_files=facts.filtered_files,
                search_hits=facts.search_hits,
                watch_metrics=facts.watch_metrics,
                events=facts.events,
            ),
            tabs=_tabs(
                stores=memory_stores.total,
                context=context_resolution.total,
                files=len(facts.filtered_files),
                index=index_jobs.total,
                sync=index_sync_activity.total,
                retrieval=retrieval_trace.total,
                writes=write_flush.total,
                usage=len(_usage_rows(facts.selected_files)),
                scans=len(facts.records),
                events=len(facts.events),
            ),
            active_tab="files",
            actions=_actions(facts.selected_agent_id),
            memory_stores=memory_stores,
            context_resolution=context_resolution,
            index_health=_index_health(facts.records, facts.watch_metrics),
            index_jobs=index_jobs,
            index_sync_activity=index_sync_activity,
            retrieval_performance=_retrieval_performance(
                facts.records,
                facts.search_hits,
                facts.query.search,
            ),
            retrieval_trace=retrieval_trace,
            write_flush=write_flush,
            memory_usage=_memory_usage_table(
                facts.selected_files,
                facts.selected_record,
            ),
            recent_retrieval_logs=retrieval_logs,
            source_scan_status=_source_scan_table(facts.records, facts.watch_metrics),
            source_files=source_files,
            file_details=_file_details(
                facts.visible_files,
                record=facts.selected_record,
                memory_query_service=self.memory_query_service,
                events=facts.events,
            ),
        )
