from __future__ import annotations

from pydantic import BaseModel, Field

from crxzipple.modules.operations.application.read_models import (
    LlmOperationsPage,
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
from crxzipple.modules.operations.interfaces.http_models_llm_details import (
    LlmInvocationDetailResponse,
)


class LlmOperationsResponse(BaseModel):
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
    provider_access_health: OperationsTableSectionResponse
    provider_auth_blocked: OperationsTableSectionResponse
    model_resolver: OperationsChartSectionResponse
    rate_limiter: OperationsKeyValueSectionResponse
    limiter_queue: OperationsTableSectionResponse
    streaming_requests: OperationsTableSectionResponse
    recent_invocations: OperationsTableSectionResponse
    failed_invocations: OperationsTableSectionResponse
    latency: OperationsChartSectionResponse
    token_usage: OperationsChartSectionResponse
    invocation_rate: OperationsChartSectionResponse
    stream_health: OperationsKeyValueSectionResponse
    execution_blocking_risk: OperationsKeyValueSectionResponse
    fallback_problems: OperationsTableSectionResponse
    context_pressure: OperationsChartSectionResponse
    model_availability: OperationsTableSectionResponse
    error_summary: OperationsTableSectionResponse
    llm_lifecycle_events: OperationsTableSectionResponse
    invocation_details: list[LlmInvocationDetailResponse] = Field(default_factory=list)
    projection_diagnostics: OperationsProjectionDiagnosticsResponse | None = None
    projection_freshness: OperationsProjectionFreshnessResponse | None = None

    @classmethod
    def from_view(
        cls,
        view: LlmOperationsPage,
    ) -> "LlmOperationsResponse":
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
            provider_access_health=OperationsTableSectionResponse.from_value(
                view.provider_access_health,
            ),
            provider_auth_blocked=OperationsTableSectionResponse.from_value(
                view.provider_auth_blocked,
            ),
            model_resolver=OperationsChartSectionResponse.from_value(
                view.model_resolver,
            ),
            rate_limiter=OperationsKeyValueSectionResponse.from_value(
                view.rate_limiter,
            ),
            limiter_queue=OperationsTableSectionResponse.from_value(
                view.limiter_queue,
            ),
            streaming_requests=OperationsTableSectionResponse.from_value(
                view.streaming_requests,
            ),
            recent_invocations=OperationsTableSectionResponse.from_value(
                view.recent_invocations,
            ),
            failed_invocations=OperationsTableSectionResponse.from_value(
                view.failed_invocations,
            ),
            latency=OperationsChartSectionResponse.from_value(view.latency),
            token_usage=OperationsChartSectionResponse.from_value(view.token_usage),
            invocation_rate=OperationsChartSectionResponse.from_value(
                view.invocation_rate,
            ),
            stream_health=OperationsKeyValueSectionResponse.from_value(
                view.stream_health,
            ),
            execution_blocking_risk=OperationsKeyValueSectionResponse.from_value(
                view.execution_blocking_risk,
            ),
            fallback_problems=OperationsTableSectionResponse.from_value(
                view.fallback_problems,
            ),
            context_pressure=OperationsChartSectionResponse.from_value(
                view.context_pressure,
            ),
            model_availability=OperationsTableSectionResponse.from_value(
                view.model_availability,
            ),
            error_summary=OperationsTableSectionResponse.from_value(
                view.error_summary,
            ),
            llm_lifecycle_events=OperationsTableSectionResponse.from_value(
                view.llm_lifecycle_events,
            ),
            invocation_details=[
                LlmInvocationDetailResponse.from_value(item)
                for item in view.invocation_details
            ],
            projection_diagnostics=OperationsProjectionDiagnosticsResponse.from_value(
                view.projection_diagnostics,
            ),
        )
