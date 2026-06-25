from __future__ import annotations

from pydantic import BaseModel

from crxzipple.modules.operations.application.read_models import (
    OrchestrationOperationsPage,
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


class OrchestrationOperationsResponse(BaseModel):
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
    scheduler_status: OperationsKeyValueSectionResponse
    backpressure: OperationsChartSectionResponse
    stuck_runs: OperationsTableSectionResponse
    policy_limits: OperationsKeyValueSectionResponse
    run_queue: OperationsTableSectionResponse
    execution_chains: OperationsTableSectionResponse
    lane_locks: OperationsTableSectionResponse
    executor_overview: OperationsTableSectionResponse
    ingress_queue: OperationsTableSectionResponse
    recent_failures: OperationsTableSectionResponse
    ops_event_log: OperationsTableSectionResponse
    projection_diagnostics: OperationsProjectionDiagnosticsResponse | None = None
    projection_freshness: OperationsProjectionFreshnessResponse | None = None

    @classmethod
    def from_view(
        cls,
        view: OrchestrationOperationsPage,
    ) -> "OrchestrationOperationsResponse":
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
            scheduler_status=OperationsKeyValueSectionResponse.from_value(
                view.scheduler_status,
            ),
            backpressure=OperationsChartSectionResponse.from_value(view.backpressure),
            stuck_runs=OperationsTableSectionResponse.from_value(view.stuck_runs),
            policy_limits=OperationsKeyValueSectionResponse.from_value(
                view.policy_limits
            ),
            run_queue=OperationsTableSectionResponse.from_value(view.run_queue),
            execution_chains=OperationsTableSectionResponse.from_value(
                view.execution_chains,
            ),
            lane_locks=OperationsTableSectionResponse.from_value(view.lane_locks),
            executor_overview=OperationsTableSectionResponse.from_value(
                view.executor_overview,
            ),
            ingress_queue=OperationsTableSectionResponse.from_value(view.ingress_queue),
            recent_failures=OperationsTableSectionResponse.from_value(
                view.recent_failures
            ),
            ops_event_log=OperationsTableSectionResponse.from_value(view.ops_event_log),
            projection_diagnostics=OperationsProjectionDiagnosticsResponse.from_value(
                view.projection_diagnostics,
            ),
        )
