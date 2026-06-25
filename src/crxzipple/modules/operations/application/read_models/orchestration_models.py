from __future__ import annotations

from dataclasses import dataclass

from crxzipple.modules.operations.application.read_models.models import (
    MetricCardModel,
    OperationsChartSectionModel,
    OperationsKeyValueSectionModel,
    OperationsModuleRoleModel,
    OperationsProjectionDiagnosticsModel,
    OperationsTabModel,
    OperationsTableSectionModel,
    RuntimeActionModel,
)


@dataclass(frozen=True, slots=True)
class OrchestrationOperationsPage:
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
    scheduler_status: OperationsKeyValueSectionModel
    backpressure: OperationsChartSectionModel
    stuck_runs: OperationsTableSectionModel
    policy_limits: OperationsKeyValueSectionModel
    run_queue: OperationsTableSectionModel
    execution_chains: OperationsTableSectionModel
    repeated_probes: OperationsTableSectionModel
    lane_locks: OperationsTableSectionModel
    executor_overview: OperationsTableSectionModel
    ingress_queue: OperationsTableSectionModel
    recent_failures: OperationsTableSectionModel
    ops_event_log: OperationsTableSectionModel
    projection_diagnostics: OperationsProjectionDiagnosticsModel | None = None
