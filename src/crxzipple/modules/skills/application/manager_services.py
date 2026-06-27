from __future__ import annotations

from dataclasses import dataclass

from crxzipple.modules.skills.application.authoring_service import SkillAuthoringService
from crxzipple.modules.skills.application.catalog_service import SkillCatalogService
from crxzipple.modules.skills.application.events import SkillEventEmitter
from crxzipple.modules.skills.application.governance_service import SkillGovernanceService
from crxzipple.modules.skills.application.owner_state import SkillOwnerStateService
from crxzipple.modules.skills.application.package_service import SkillPackageService
from crxzipple.modules.skills.application.ports import (
    SkillAuthoringDraftRepositoryPort,
    SkillOwnerCatalogRepositoryPort,
    SkillRepositoryPort,
)
from crxzipple.modules.skills.application.readiness_service import SkillReadinessService
from crxzipple.modules.skills.application.runtime_request_resolver import (
    SkillRuntimeRequestResolver,
    SkillToolReadinessPort,
)
from crxzipple.modules.skills.application.source_service import SkillSourceService


@dataclass(slots=True)
class SkillManagerServiceGraph:
    owner_state: SkillOwnerStateService
    catalog_service: SkillCatalogService
    source_service: SkillSourceService
    package_service: SkillPackageService
    governance_service: SkillGovernanceService
    readiness_service: SkillReadinessService
    authoring_service: SkillAuthoringService


def build_skill_manager_service_graph(
    *,
    repository: SkillRepositoryPort,
    owner_catalog_repository: SkillOwnerCatalogRepositoryPort | None,
    event_emitter: SkillEventEmitter | None,
    runtime_request_resolver: SkillRuntimeRequestResolver,
    persist_runtime_request_readiness: bool,
    tool_readiness_port: SkillToolReadinessPort | None,
    owner_state: SkillOwnerStateService | None,
    catalog_service: SkillCatalogService | None,
    source_service: SkillSourceService | None,
    package_service: SkillPackageService | None,
    governance_service: SkillGovernanceService | None,
    readiness_service: SkillReadinessService | None,
    authoring_service: SkillAuthoringService | None,
) -> SkillManagerServiceGraph:
    resolved_owner_state = owner_state or SkillOwnerStateService(
        owner_catalog_repository=owner_catalog_repository,
        event_emitter=event_emitter,
    )
    resolved_catalog_service = catalog_service or SkillCatalogService(
        repository=repository,
        owner_state=resolved_owner_state,
        runtime_request_resolver=runtime_request_resolver,
        persist_runtime_request_readiness=persist_runtime_request_readiness,
    )
    resolved_source_service = source_service or SkillSourceService(
        catalog_service=resolved_catalog_service,
        owner_state=resolved_owner_state,
        owner_catalog_repository=owner_catalog_repository,
        event_emitter=event_emitter,
    )
    resolved_package_service = package_service or SkillPackageService(
        repository=repository,
        catalog_service=resolved_catalog_service,
        source_service=resolved_source_service,
        owner_state=resolved_owner_state,
        event_emitter=event_emitter,
    )
    resolved_governance_service = governance_service or SkillGovernanceService(
        catalog_service=resolved_catalog_service,
        owner_state=resolved_owner_state,
        owner_catalog_repository=owner_catalog_repository,
        event_emitter=event_emitter,
    )
    resolved_readiness_service = readiness_service or SkillReadinessService(
        catalog_service=resolved_catalog_service,
        owner_state=resolved_owner_state,
        runtime_request_resolver=runtime_request_resolver,
        tool_readiness_port=tool_readiness_port,
    )
    resolved_authoring_service = authoring_service or SkillAuthoringService(
        draft_repository=authoring_draft_repository(owner_catalog_repository),
        package_service=resolved_package_service,
        runtime_request_resolver=runtime_request_resolver,
        tool_readiness_port=tool_readiness_port,
        event_emitter=event_emitter,
    )
    return SkillManagerServiceGraph(
        owner_state=resolved_owner_state,
        catalog_service=resolved_catalog_service,
        source_service=resolved_source_service,
        package_service=resolved_package_service,
        governance_service=resolved_governance_service,
        readiness_service=resolved_readiness_service,
        authoring_service=resolved_authoring_service,
    )


def authoring_draft_repository(
    repository: object | None,
) -> SkillAuthoringDraftRepositoryPort | None:
    if repository is None:
        return None
    required = (
        "save_draft",
        "get_draft",
        "list_drafts",
        "delete_draft",
        "append_draft_audit",
        "list_draft_audit",
    )
    if all(hasattr(repository, name) for name in required):
        return repository  # type: ignore[return-value]
    return None
