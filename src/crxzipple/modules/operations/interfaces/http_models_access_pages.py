from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from crxzipple.modules.operations.application.read_models import (
    AccessOperationsPage,
    AccessTargetDetailModel,
)
from crxzipple.modules.operations.interfaces.http_models_core import (
    MetricCardResponse,
    OperationsChartSectionResponse,
    OperationsKeyValueItemResponse,
    OperationsModuleRoleResponse,
    OperationsProjectionFreshnessResponse,
    OperationsTabResponse,
    OperationsTableSectionResponse,
    RuntimeActionResponse,
)


class AccessTargetDetailResponse(BaseModel):
    target_id: str
    title: str
    status: str
    tone: str
    summary: list[OperationsKeyValueItemResponse]
    checks: OperationsTableSectionResponse
    usages: OperationsTableSectionResponse
    setup: OperationsTableSectionResponse
    events: OperationsTableSectionResponse
    raw_payload: Any

    @classmethod
    def from_value(
        cls,
        value: AccessTargetDetailModel,
    ) -> "AccessTargetDetailResponse":
        return cls(
            target_id=value.target_id,
            title=value.title,
            status=value.status,
            tone=value.tone,
            summary=[
                OperationsKeyValueItemResponse.from_value(item)
                for item in value.summary
            ],
            checks=OperationsTableSectionResponse.from_value(value.checks),
            usages=OperationsTableSectionResponse.from_value(value.usages),
            setup=OperationsTableSectionResponse.from_value(value.setup),
            events=OperationsTableSectionResponse.from_value(value.events),
            raw_payload=value.raw_payload,
        )


class AccessOperationsResponse(BaseModel):
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
    access_targets: OperationsTableSectionResponse
    access_requirements: OperationsTableSectionResponse
    access_audit_summary: OperationsTableSectionResponse
    missing_access: OperationsTableSectionResponse
    credential_health: OperationsChartSectionResponse
    provider_auth_blocked: OperationsTableSectionResponse
    credentials_by_kind: OperationsChartSectionResponse
    expiring_soon: OperationsTableSectionResponse
    auth_success_rate: OperationsChartSectionResponse
    authentication_status: OperationsTableSectionResponse
    access_usage: OperationsTableSectionResponse
    recent_access_events: OperationsTableSectionResponse
    fallback_problems: OperationsTableSectionResponse
    setup_flows: OperationsTableSectionResponse
    target_details: list[AccessTargetDetailResponse]
    projection_freshness: OperationsProjectionFreshnessResponse | None = None

    @classmethod
    def from_view(
        cls,
        view: AccessOperationsPage,
    ) -> "AccessOperationsResponse":
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
            access_targets=OperationsTableSectionResponse.from_value(
                view.access_targets,
            ),
            access_requirements=OperationsTableSectionResponse.from_value(
                view.access_requirements,
            ),
            access_audit_summary=OperationsTableSectionResponse.from_value(
                view.access_audit_summary,
            ),
            missing_access=OperationsTableSectionResponse.from_value(
                view.missing_access,
            ),
            credential_health=OperationsChartSectionResponse.from_value(
                view.credential_health,
            ),
            provider_auth_blocked=OperationsTableSectionResponse.from_value(
                view.provider_auth_blocked,
            ),
            credentials_by_kind=OperationsChartSectionResponse.from_value(
                view.credentials_by_kind,
            ),
            expiring_soon=OperationsTableSectionResponse.from_value(
                view.expiring_soon,
            ),
            auth_success_rate=OperationsChartSectionResponse.from_value(
                view.auth_success_rate,
            ),
            authentication_status=OperationsTableSectionResponse.from_value(
                view.authentication_status,
            ),
            access_usage=OperationsTableSectionResponse.from_value(view.access_usage),
            recent_access_events=OperationsTableSectionResponse.from_value(
                view.recent_access_events,
            ),
            fallback_problems=OperationsTableSectionResponse.from_value(
                view.fallback_problems,
            ),
            setup_flows=OperationsTableSectionResponse.from_value(view.setup_flows),
            target_details=[
                AccessTargetDetailResponse.from_value(item)
                for item in view.target_details
            ],
        )
