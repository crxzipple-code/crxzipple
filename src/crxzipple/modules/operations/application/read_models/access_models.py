from __future__ import annotations

from dataclasses import dataclass
from typing import Any

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
class AccessOperationsQuery:
    status: str = "all"
    kind: str = "all"
    usage_type: str = "all"
    search: str = ""
    include_ready: bool = True
    include_disabled: bool = False
    limit: int = 80
    offset: int = 0


@dataclass(frozen=True, slots=True)
class AccessTargetDetailModel:
    target_id: str
    title: str
    status: str
    tone: str
    summary: tuple[OperationsKeyValueItemModel, ...]
    checks: OperationsTableSectionModel
    usages: OperationsTableSectionModel
    setup: OperationsTableSectionModel
    events: OperationsTableSectionModel
    raw_payload: dict[str, Any]


@dataclass(frozen=True, slots=True)
class AccessOperationsPage:
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
    access_targets: OperationsTableSectionModel
    access_requirements: OperationsTableSectionModel
    access_audit_summary: OperationsTableSectionModel
    missing_access: OperationsTableSectionModel
    credential_health: OperationsChartSectionModel
    provider_auth_blocked: OperationsTableSectionModel
    credentials_by_kind: OperationsChartSectionModel
    expiring_soon: OperationsTableSectionModel
    auth_success_rate: OperationsChartSectionModel
    authentication_status: OperationsTableSectionModel
    access_usage: OperationsTableSectionModel
    recent_access_events: OperationsTableSectionModel
    fallback_problems: OperationsTableSectionModel
    setup_flows: OperationsTableSectionModel
    target_details: tuple[AccessTargetDetailModel, ...]
