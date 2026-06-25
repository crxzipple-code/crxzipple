from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from crxzipple.modules.operations.application.observation_models import OperationsObservedEvent
from crxzipple.modules.operations.application.read_models.models import (
    MetricCardModel,
    OperationsChartSectionModel,
    OperationsKeyValueItemModel,
    OperationsModuleRoleModel,
    OperationsTabModel,
    OperationsTableSectionModel,
    RuntimeActionModel,
)


@dataclass(frozen=True, slots=True)
class SkillsOperationsQuery:
    surface: str = "interactive"
    source: str = "all"
    status: str = "all"
    search: str = ""
    limit: int = 80
    offset: int = 0


@dataclass(frozen=True, slots=True)
class SkillDetailModel:
    skill_id: str
    title: str
    status: str
    tone: str
    summary: tuple[OperationsKeyValueItemModel, ...]
    requirements: OperationsTableSectionModel
    resources: OperationsTableSectionModel
    events: OperationsTableSectionModel
    raw_payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class SkillsOperationsPage:
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
    recently_resolved_skills: OperationsTableSectionModel
    resolution_outcomes: OperationsChartSectionModel
    top_used_skills: OperationsTableSectionModel
    missing_capabilities: OperationsTableSectionModel
    access_requirements: OperationsTableSectionModel
    capability_requirements: OperationsTableSectionModel
    resolution_logs: OperationsTableSectionModel
    skill_reads: OperationsTableSectionModel
    resolver_detail: OperationsTableSectionModel
    authoring_backlog: OperationsTableSectionModel
    authoring_failures: OperationsTableSectionModel
    import_normalize: tuple[RuntimeActionModel, ...]
    skill_package_sources: OperationsChartSectionModel
    conflicts_overrides: OperationsTableSectionModel
    profile_usage: OperationsTableSectionModel
    skill_details: tuple[SkillDetailModel, ...]


@dataclass(frozen=True, slots=True)
class SkillRecord:
    package: Any
    status: str
    tone: str
    missing_tools: tuple[str, ...]
    missing_access: tuple[str, ...]
    missing_effects: tuple[str, ...]
    unsupported_surfaces: tuple[str, ...]
    unsupported_platforms: tuple[str, ...]
    access_checks: tuple[Any, ...]
    readiness_event: OperationsObservedEvent | None = None
