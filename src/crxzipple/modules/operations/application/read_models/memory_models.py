from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from crxzipple.modules.operations.application.read_models.models import (
    MetricCardModel,
    OperationsChartSectionModel,
    OperationsKeyValueItemModel,
    OperationsModuleRoleModel,
    OperationsTabModel,
    OperationsTableSectionModel,
    RuntimeActionModel,
)


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
class MemoryContextRecord:
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


class AdHocProfile:
    def __init__(self, agent_id: str) -> None:
        self.id = agent_id
        self.name = agent_id
        self.enabled = True
