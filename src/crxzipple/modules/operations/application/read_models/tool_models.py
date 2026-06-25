from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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
from crxzipple.modules.operations.application.read_models.tool_run_details import (
    ToolRunDetailModel,
)
from crxzipple.modules.operations.application.read_models.tool_worker_details import (
    ToolWorkerDetailModel,
)


@dataclass(frozen=True, slots=True)
class ToolOperationsPage:
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
    active_tool_runs: OperationsTableSectionModel
    tool_queue_runs: OperationsTableSectionModel
    tool_waiting_io: OperationsTableSectionModel
    tool_runs: OperationsTableSectionModel
    tool_types: OperationsChartSectionModel
    source_health: OperationsTableSectionModel
    discovery_failures: OperationsTableSectionModel
    function_catalog: OperationsTableSectionModel
    provider_backend_health: OperationsTableSectionModel
    cli_process_health: OperationsTableSectionModel
    auth_missing: OperationsTableSectionModel
    worker_pool: OperationsChartSectionModel
    workers: OperationsTableSectionModel
    tool_queue: OperationsTableSectionModel
    capability_limits: OperationsTableSectionModel
    provider_limits: OperationsTableSectionModel
    provider_history: OperationsTableSectionModel
    run_blockers: OperationsTableSectionModel
    inline_risk: OperationsKeyValueSectionModel
    recent_artifacts: OperationsTableSectionModel
    tool_lifecycle_events: OperationsTableSectionModel
    strategies: OperationsTableSectionModel
    worker_details: tuple[ToolWorkerDetailModel, ...]
    tool_run_details: tuple[ToolRunDetailModel, ...]
    projection_diagnostics: OperationsProjectionDiagnosticsModel | None = None


def defer_tool_run_details_payload(payload: dict[str, Any]) -> None:
    payload["tool_run_details"] = []


def find_tool_run_detail_payload(
    payload: dict[str, Any],
    run_id: str,
) -> dict[str, Any] | None:
    details = payload.get("tool_run_details")
    if not isinstance(details, list):
        return None
    normalized_run_id = run_id.strip()
    for item in details:
        if isinstance(item, dict) and str(item.get("run_id") or "") == normalized_run_id:
            return item
    return None
