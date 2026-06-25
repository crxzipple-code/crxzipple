from __future__ import annotations

from dataclasses import dataclass

from crxzipple.modules.operations.application.read_models.models import (
    MetricCardModel,
    OperationsModuleRoleModel,
    OperationsTabModel,
    OperationsTableSectionModel,
    RuntimeActionModel,
)


@dataclass(frozen=True, slots=True)
class BrowserOperationsQuery:
    status: str = "all"
    profile: str = "all"
    search: str = ""
    limit: int = 80
    offset: int = 0


@dataclass(frozen=True, slots=True)
class BrowserOperationsPage:
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
    profiles: OperationsTableSectionModel
    profile_pools: OperationsTableSectionModel
    profile_allocations: OperationsTableSectionModel
    page_observations: OperationsTableSectionModel
    daemon_runtimes: OperationsTableSectionModel
    network_activity: OperationsTableSectionModel
    diagnostics: OperationsTableSectionModel
