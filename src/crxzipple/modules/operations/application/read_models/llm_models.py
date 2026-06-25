from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from crxzipple.modules.operations.application.read_models.models import (
    MetricCardModel,
    OperationsChartSectionModel,
    OperationsKeyValueItemModel,
    OperationsKeyValueSectionModel,
    OperationsModuleRoleModel,
    OperationsProjectionDiagnosticsModel,
    OperationsTabModel,
    OperationsTableSectionModel,
    RuntimeActionModel,
)


@dataclass(frozen=True, slots=True)
class LlmInvocationDetailModel:
    invocation_id: str
    title: str
    status: str
    tone: str
    summary: tuple[OperationsKeyValueItemModel, ...]
    request_context: tuple[OperationsKeyValueItemModel, ...]
    runtime_observations: OperationsKeyValueSectionModel
    runtime_request_summary: dict[str, Any]
    request_payload: Any
    provider_render_report: dict[str, Any]
    provider_wire_preview: dict[str, Any]
    provider_context_mapping: OperationsTableSectionModel
    result_payload: Any
    result_summary: str
    error: str
    resolver: OperationsKeyValueSectionModel
    error_facts: OperationsKeyValueSectionModel
    policy_trace: OperationsTableSectionModel
    response_items: OperationsTableSectionModel
    response_runtime_mapping: OperationsTableSectionModel
    response_events: OperationsTableSectionModel
    events: OperationsTableSectionModel


@dataclass(frozen=True, slots=True)
class LlmOperationsPage:
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
    provider_access_health: OperationsTableSectionModel
    provider_auth_blocked: OperationsTableSectionModel
    model_resolver: OperationsChartSectionModel
    rate_limiter: OperationsKeyValueSectionModel
    limiter_queue: OperationsTableSectionModel
    streaming_requests: OperationsTableSectionModel
    recent_invocations: OperationsTableSectionModel
    failed_invocations: OperationsTableSectionModel
    latency: OperationsChartSectionModel
    token_usage: OperationsChartSectionModel
    invocation_rate: OperationsChartSectionModel
    stream_health: OperationsKeyValueSectionModel
    execution_blocking_risk: OperationsKeyValueSectionModel
    fallback_problems: OperationsTableSectionModel
    context_pressure: OperationsChartSectionModel
    model_availability: OperationsTableSectionModel
    error_summary: OperationsTableSectionModel
    llm_lifecycle_events: OperationsTableSectionModel
    invocation_details: tuple[LlmInvocationDetailModel, ...]
    projection_diagnostics: OperationsProjectionDiagnosticsModel | None = None


def defer_llm_invocation_details_payload(payload: dict[str, Any]) -> None:
    payload["invocation_details"] = []


def find_llm_invocation_detail_payload(
    payload: dict[str, Any],
    invocation_id: str,
) -> dict[str, Any] | None:
    details = payload.get("invocation_details")
    if not isinstance(details, list):
        return None
    normalized_invocation_id = invocation_id.strip()
    for item in details:
        if (
            isinstance(item, dict)
            and str(item.get("invocation_id") or "") == normalized_invocation_id
        ):
            return item
    return None
