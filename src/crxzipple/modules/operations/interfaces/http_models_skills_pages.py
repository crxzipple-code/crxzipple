from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from crxzipple.modules.operations.application.read_models import (
    SkillDetailModel,
    SkillsOperationsPage,
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


class SkillDetailResponse(BaseModel):
    skill_id: str
    title: str
    status: str
    tone: str
    summary: list[OperationsKeyValueItemResponse]
    requirements: OperationsTableSectionResponse
    resources: OperationsTableSectionResponse
    events: OperationsTableSectionResponse
    raw_payload: Any

    @classmethod
    def from_value(cls, value: SkillDetailModel) -> "SkillDetailResponse":
        return cls(
            skill_id=value.skill_id,
            title=value.title,
            status=value.status,
            tone=value.tone,
            summary=[
                OperationsKeyValueItemResponse.from_value(item)
                for item in value.summary
            ],
            requirements=OperationsTableSectionResponse.from_value(
                value.requirements,
            ),
            resources=OperationsTableSectionResponse.from_value(value.resources),
            events=OperationsTableSectionResponse.from_value(value.events),
            raw_payload=value.raw_payload,
        )


class SkillsOperationsResponse(BaseModel):
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
    recently_resolved_skills: OperationsTableSectionResponse
    resolution_outcomes: OperationsChartSectionResponse
    top_used_skills: OperationsTableSectionResponse
    missing_capabilities: OperationsTableSectionResponse
    access_requirements: OperationsTableSectionResponse
    capability_requirements: OperationsTableSectionResponse
    resolution_logs: OperationsTableSectionResponse
    skill_reads: OperationsTableSectionResponse
    resolver_detail: OperationsTableSectionResponse
    authoring_backlog: OperationsTableSectionResponse
    authoring_failures: OperationsTableSectionResponse
    import_normalize: list[RuntimeActionResponse]
    skill_package_sources: OperationsChartSectionResponse
    conflicts_overrides: OperationsTableSectionResponse
    profile_usage: OperationsTableSectionResponse
    skill_details: list[SkillDetailResponse]
    projection_freshness: OperationsProjectionFreshnessResponse | None = None

    @classmethod
    def from_view(
        cls,
        view: SkillsOperationsPage,
    ) -> "SkillsOperationsResponse":
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
            recently_resolved_skills=OperationsTableSectionResponse.from_value(
                view.recently_resolved_skills,
            ),
            resolution_outcomes=OperationsChartSectionResponse.from_value(
                view.resolution_outcomes,
            ),
            top_used_skills=OperationsTableSectionResponse.from_value(
                view.top_used_skills,
            ),
            missing_capabilities=OperationsTableSectionResponse.from_value(
                view.missing_capabilities,
            ),
            access_requirements=OperationsTableSectionResponse.from_value(
                view.access_requirements,
            ),
            capability_requirements=OperationsTableSectionResponse.from_value(
                view.capability_requirements,
            ),
            resolution_logs=OperationsTableSectionResponse.from_value(
                view.resolution_logs,
            ),
            skill_reads=OperationsTableSectionResponse.from_value(
                view.skill_reads,
            ),
            resolver_detail=OperationsTableSectionResponse.from_value(
                view.resolver_detail,
            ),
            authoring_backlog=OperationsTableSectionResponse.from_value(
                view.authoring_backlog,
            ),
            authoring_failures=OperationsTableSectionResponse.from_value(
                view.authoring_failures,
            ),
            import_normalize=[
                RuntimeActionResponse.from_value(item) for item in view.import_normalize
            ],
            skill_package_sources=OperationsChartSectionResponse.from_value(
                view.skill_package_sources,
            ),
            conflicts_overrides=OperationsTableSectionResponse.from_value(
                view.conflicts_overrides,
            ),
            profile_usage=OperationsTableSectionResponse.from_value(
                view.profile_usage,
            ),
            skill_details=[
                SkillDetailResponse.from_value(item) for item in view.skill_details
            ],
        )
