from __future__ import annotations

from pydantic import BaseModel, Field

from crxzipple.modules.operations.application.read_models import (
    ToolOperationsPage,
)
from crxzipple.modules.operations.interfaces.http_models_tool_details import (
    ToolRunDetailResponse,
    ToolWorkerDetailResponse,
)
from crxzipple.modules.operations.interfaces.http_models_core import (
    MetricCardResponse,
    OperationsChartSectionResponse,
    OperationsKeyValueSectionResponse,
    OperationsModuleRoleResponse,
    OperationsProjectionDiagnosticsResponse,
    OperationsProjectionFreshnessResponse,
    OperationsTabResponse,
    OperationsTableSectionResponse,
    RuntimeActionResponse,
)


class ToolOperationsResponse(BaseModel):
    module: str
    title: str
    subtitle: str
    health: str
    updated_at: str
    auto_refresh: bool
    role: OperationsModuleRoleResponse
    metrics: list[MetricCardResponse]
    tabs: list[OperationsTabResponse]
    active_tab: str
    actions: list[RuntimeActionResponse]
    active_tool_runs: OperationsTableSectionResponse
    tool_queue_runs: OperationsTableSectionResponse
    tool_waiting_io: OperationsTableSectionResponse
    tool_runs: OperationsTableSectionResponse
    tool_types: OperationsChartSectionResponse
    source_health: OperationsTableSectionResponse
    discovery_failures: OperationsTableSectionResponse
    function_catalog: OperationsTableSectionResponse
    provider_backend_health: OperationsTableSectionResponse
    cli_process_health: OperationsTableSectionResponse
    auth_missing: OperationsTableSectionResponse
    worker_pool: OperationsChartSectionResponse
    workers: OperationsTableSectionResponse
    tool_queue: OperationsTableSectionResponse
    capability_limits: OperationsTableSectionResponse
    provider_limits: OperationsTableSectionResponse
    provider_history: OperationsTableSectionResponse
    run_blockers: OperationsTableSectionResponse
    inline_risk: OperationsKeyValueSectionResponse
    recent_artifacts: OperationsTableSectionResponse
    tool_lifecycle_events: OperationsTableSectionResponse
    strategies: OperationsTableSectionResponse
    worker_details: list[ToolWorkerDetailResponse]
    tool_run_details: list[ToolRunDetailResponse] = Field(default_factory=list)
    projection_diagnostics: OperationsProjectionDiagnosticsResponse | None = None
    projection_freshness: OperationsProjectionFreshnessResponse | None = None

    @classmethod
    def from_view(
        cls,
        view: ToolOperationsPage,
    ) -> "ToolOperationsResponse":
        return cls(
            module=view.module,
            title=view.title,
            subtitle=view.subtitle,
            health=view.health,
            updated_at=view.updated_at,
            auto_refresh=view.auto_refresh,
            role=OperationsModuleRoleResponse.from_value(view.role),
            metrics=[MetricCardResponse.from_value(item) for item in view.metrics],
            tabs=[OperationsTabResponse.from_value(item) for item in view.tabs],
            active_tab=view.active_tab,
            actions=[RuntimeActionResponse.from_value(item) for item in view.actions],
            active_tool_runs=OperationsTableSectionResponse.from_value(
                view.active_tool_runs,
            ),
            tool_queue_runs=OperationsTableSectionResponse.from_value(
                view.tool_queue_runs,
            ),
            tool_waiting_io=OperationsTableSectionResponse.from_value(
                view.tool_waiting_io,
            ),
            tool_runs=OperationsTableSectionResponse.from_value(view.tool_runs),
            tool_types=OperationsChartSectionResponse.from_value(view.tool_types),
            source_health=OperationsTableSectionResponse.from_value(
                view.source_health,
            ),
            discovery_failures=OperationsTableSectionResponse.from_value(
                view.discovery_failures,
            ),
            function_catalog=OperationsTableSectionResponse.from_value(
                view.function_catalog,
            ),
            provider_backend_health=OperationsTableSectionResponse.from_value(
                view.provider_backend_health,
            ),
            cli_process_health=OperationsTableSectionResponse.from_value(
                view.cli_process_health,
            ),
            auth_missing=OperationsTableSectionResponse.from_value(view.auth_missing),
            worker_pool=OperationsChartSectionResponse.from_value(view.worker_pool),
            workers=OperationsTableSectionResponse.from_value(view.workers),
            tool_queue=OperationsTableSectionResponse.from_value(view.tool_queue),
            capability_limits=OperationsTableSectionResponse.from_value(
                view.capability_limits,
            ),
            provider_limits=OperationsTableSectionResponse.from_value(
                view.provider_limits,
            ),
            provider_history=OperationsTableSectionResponse.from_value(
                view.provider_history,
            ),
            run_blockers=OperationsTableSectionResponse.from_value(view.run_blockers),
            inline_risk=OperationsKeyValueSectionResponse.from_value(
                view.inline_risk,
            ),
            recent_artifacts=OperationsTableSectionResponse.from_value(
                view.recent_artifacts,
            ),
            tool_lifecycle_events=OperationsTableSectionResponse.from_value(
                view.tool_lifecycle_events,
            ),
            strategies=OperationsTableSectionResponse.from_value(view.strategies),
            worker_details=[
                ToolWorkerDetailResponse.from_value(item)
                for item in view.worker_details
            ],
            tool_run_details=[
                ToolRunDetailResponse.from_value(item) for item in view.tool_run_details
            ],
            projection_diagnostics=OperationsProjectionDiagnosticsResponse.from_value(
                view.projection_diagnostics,
            ),
        )
