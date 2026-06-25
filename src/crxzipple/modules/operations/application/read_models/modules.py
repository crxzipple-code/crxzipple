from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from crxzipple.modules.operations.application.read_models.models import (
    MetricCardModel,
    OperationsModuleOverview,
    OperationsTabModel,
    RuntimeActionModel,
    OperationsModuleRoleModel,
    OperationsTableSectionModel,
)
from crxzipple.modules.operations.application.read_models.modules_access import (
    access_operations_overview,
)
from crxzipple.modules.operations.application.read_models.modules_channels import (
    channels_operations_overview,
)
from crxzipple.modules.operations.application.read_models.modules_daemon import (
    daemon_operations_overview,
)
from crxzipple.modules.operations.application.read_models.modules_events import (
    events_operations_overview,
)
from crxzipple.modules.operations.application.read_models.modules_overview_sections import (
    sections_for_overview as _sections_for_overview,
)
from crxzipple.modules.operations.application.read_models.modules_memory import (
    memory_operations_overview,
)
from crxzipple.modules.operations.application.read_models.modules_skills import (
    skills_operations_overview,
)
from crxzipple.modules.operations.application.read_models.ports_access_settings import (
    OperationsAccessReadinessPort,
    OperationsSettingsQueryPort,
)
from crxzipple.modules.operations.application.read_models.ports_context import (
    OperationsMemoryQueryPort,
    OperationsSkillCatalogPort,
)
from crxzipple.modules.operations.application.read_models.ports_llm_agent import (
    OperationsAgentProfilePort,
    OperationsLlmQueryPort,
)
from crxzipple.modules.operations.application.read_models.ports_runtime import (
    OperationsEventContractRegistryPort,
    OperationsEventDefinitionRegistryPort,
    OperationsEventStreamPort,
    OperationsObservationReadPort,
)
from crxzipple.modules.operations.application.read_models.ports_runtime_sources import (
    OperationsBrowserProfilePort,
    OperationsChannelProfilePort,
    OperationsChannelRuntimePort,
    OperationsDaemonManagerPort,
    OperationsDaemonRegistryPort,
)
from crxzipple.modules.operations.application.read_models.ports_tooling import (
    OperationsToolQueryPort,
)

@dataclass(frozen=True, slots=True)
class OperationsModuleQuerySet:
    access_service: OperationsAccessReadinessPort
    access_governance_repository: Any | None
    settings_query_service: OperationsSettingsQueryPort | None
    settings_environment: str | None
    agent_service: OperationsAgentProfilePort
    channel_profile_service: OperationsChannelProfilePort
    channel_runtime_manager: OperationsChannelRuntimePort
    daemon_manager: OperationsDaemonManagerPort
    daemon_service: OperationsDaemonRegistryPort
    event_contract_registry: OperationsEventContractRegistryPort
    event_definition_registry: OperationsEventDefinitionRegistryPort
    events_service: OperationsEventStreamPort | None
    operations_observation_store: OperationsObservationReadPort | None
    llm_service: OperationsLlmQueryPort
    memory_query_service: OperationsMemoryQueryPort
    skill_manager: OperationsSkillCatalogPort
    browser_profile_service: OperationsBrowserProfilePort
    tool_service: OperationsToolQueryPort


@dataclass(frozen=True, slots=True)
class OperationsModulePage:
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
    sections: tuple[OperationsTableSectionModel, ...]


@dataclass(frozen=True, slots=True)
class OperationsModuleReadModelProvider:
    module_query: OperationsModuleQuerySet

    def page(self, module: str) -> OperationsModulePage | None:
        return operations_module_page(module, self.module_query)

    def overview(self, module: str) -> OperationsModuleOverview | None:
        return operations_module_overview(module, self.module_query)


def operations_module_page(
    module: str,
    query: OperationsModuleQuerySet,
) -> OperationsModulePage | None:
    overview = operations_module_overview(module, query)
    if overview is None:
        return None
    sections = _sections_for_overview(overview)
    return OperationsModulePage(
        module=overview.module,
        title=overview.title,
        subtitle=overview.subtitle,
        health=overview.health,
        updated_at=overview.updated_at,
        auto_refresh=True,
        role=OperationsModuleRoleModel(
            label=f"{overview.title} operator",
            can_operate=True,
            scope=overview.module,
        ),
        metrics=overview.metrics,
        tabs=tuple(
            OperationsTabModel(
                id=section.id,
                label=section.title,
                count=section.total,
                tone="neutral",
            )
            for section in sections
        ),
        active_tab=sections[0].id if sections else "overview",
        actions=overview.actions,
        sections=sections,
    )


def operations_module_overview(
    module: str,
    query: OperationsModuleQuerySet,
) -> OperationsModuleOverview | None:
    if module == "access":
        return access_operations_overview(query)
    if module == "channels":
        return channels_operations_overview(query)
    if module == "memory":
        return memory_operations_overview(query)
    if module == "skills":
        return skills_operations_overview(query)
    if module == "events":
        return events_operations_overview(query)
    if module == "daemon":
        return daemon_operations_overview(query)
    return None
