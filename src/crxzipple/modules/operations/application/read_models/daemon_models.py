from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from crxzipple.modules.operations.application.read_models.models import (
    MetricCardModel,
    OperationsChartSectionModel,
    OperationsKeyValueItemModel,
    OperationsKeyValueSectionModel,
    OperationsModuleRoleModel,
    OperationsTabModel,
    OperationsTableSectionModel,
    RuntimeActionModel,
)


@dataclass(frozen=True, slots=True)
class DaemonOperationsQuery:
    status: str = "all"
    service_key: str = "all"
    service_group: str = "all"
    search: str = ""
    limit: int = 80
    offset: int = 0


@dataclass(frozen=True, slots=True)
class DaemonInstanceDetailModel:
    instance_id: str
    title: str
    status: str
    tone: str
    summary: tuple[OperationsKeyValueItemModel, ...]
    environment: OperationsKeyValueSectionModel
    service: OperationsKeyValueSectionModel
    leases: OperationsTableSectionModel
    events: OperationsTableSectionModel
    raw_payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class DaemonLeaseDetailModel:
    lease_id: str
    title: str
    status: str
    tone: str
    summary: tuple[OperationsKeyValueItemModel, ...]
    metadata: OperationsKeyValueSectionModel
    events: OperationsTableSectionModel
    raw_payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class DaemonProcessDetailModel:
    process_id: str
    title: str
    status: str
    tone: str
    summary: tuple[OperationsKeyValueItemModel, ...]
    metadata: OperationsKeyValueSectionModel
    output: OperationsTableSectionModel
    raw_payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class DaemonOperationsPage:
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
    service_sets: OperationsTableSectionModel
    services: OperationsTableSectionModel
    instances: OperationsTableSectionModel
    leases: OperationsTableSectionModel
    processes: OperationsTableSectionModel
    process_health: OperationsChartSectionModel
    restart_summary: OperationsChartSectionModel
    lease_health: OperationsChartSectionModel
    dependency_health: OperationsTableSectionModel
    drain_overview: OperationsKeyValueSectionModel
    daemon_events: OperationsTableSectionModel
    quick_actions: tuple[RuntimeActionModel, ...]
    links_to_operations: tuple[dict[str, str], ...]
    instance_details: tuple[DaemonInstanceDetailModel, ...]
    lease_details: tuple[DaemonLeaseDetailModel, ...]
    process_details: tuple[DaemonProcessDetailModel, ...]
