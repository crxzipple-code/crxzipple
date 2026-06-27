from __future__ import annotations

from dataclasses import dataclass, field

from crxzipple.modules.skills.application.catalog_service import SkillCatalogService
from crxzipple.modules.skills.application.authoring_service import SkillAuthoringService
from crxzipple.modules.skills.application.events import (
    SkillEventEmitter,
)
from crxzipple.modules.skills.application.governance_service import SkillGovernanceService
from crxzipple.modules.skills.application.models import (
    InstalledSkill,
    SkillRuntimeRequestCatalog,
    SkillCreateRequest,
    SkillDraft,
    SkillDraftAuditRecord,
    SkillDraftCreateRequest,
    SkillDraftUpdateRequest,
    SkillMutationResult,
    SkillPackage,
    SkillReadResult,
    SkillReadiness,
    SkillSource,
    SkillSourceCreateRequest,
    SkillSourceMutationResult,
    SkillSourceUpdateRequest,
    SkillSyncResult,
    SkillUpdateRequest,
)
from crxzipple.modules.skills.application.ports import (
    SkillCatalogPort,
    SkillGovernancePort,
    SkillInspectionPort,
    SkillInstallationPort,
    SkillReadPort,
    SkillOwnerCatalogRepositoryPort,
    SkillRepositoryPort,
)
from crxzipple.modules.skills.application.owner_state import (
    SkillOwnerStateService,
)
from crxzipple.modules.skills.application.package_service import SkillPackageService
from crxzipple.modules.skills.application.manager_services import (
    build_skill_manager_service_graph,
)
from crxzipple.modules.skills.application.runtime_request_resolver import (
    SkillRuntimeRequestResolution,
    SkillRuntimeRequestResolver,
    SkillToolReadinessPort,
)
from crxzipple.modules.skills.application.readiness_service import SkillReadinessService
from crxzipple.modules.skills.application.source_service import SkillSourceService
from crxzipple.modules.skills.domain import (
    SkillInstallScope,
)


@dataclass(slots=True)
class SkillManager(
    SkillCatalogPort,
    SkillReadPort,
    SkillInspectionPort,
    SkillInstallationPort,
    SkillGovernancePort,
):
    repository: SkillRepositoryPort
    owner_catalog_repository: SkillOwnerCatalogRepositoryPort | None = None
    event_emitter: SkillEventEmitter | None = None
    runtime_request_resolver: SkillRuntimeRequestResolver = field(default_factory=SkillRuntimeRequestResolver)
    persist_runtime_request_readiness: bool = True
    tool_readiness_port: SkillToolReadinessPort | None = None
    owner_state: SkillOwnerStateService | None = None
    catalog_service: SkillCatalogService | None = None
    source_service: SkillSourceService | None = None
    package_service: SkillPackageService | None = None
    governance_service: SkillGovernanceService | None = None
    readiness_service: SkillReadinessService | None = None
    authoring_service: SkillAuthoringService | None = None

    def __post_init__(self) -> None:
        graph = build_skill_manager_service_graph(
            repository=self.repository,
            owner_catalog_repository=self.owner_catalog_repository,
            event_emitter=self.event_emitter,
            runtime_request_resolver=self.runtime_request_resolver,
            persist_runtime_request_readiness=self.persist_runtime_request_readiness,
            tool_readiness_port=self.tool_readiness_port,
            owner_state=self.owner_state,
            catalog_service=self.catalog_service,
            source_service=self.source_service,
            package_service=self.package_service,
            governance_service=self.governance_service,
            readiness_service=self.readiness_service,
            authoring_service=self.authoring_service,
        )
        self.owner_state = graph.owner_state
        self.catalog_service = graph.catalog_service
        self.source_service = graph.source_service
        self.package_service = graph.package_service
        self.governance_service = graph.governance_service
        self.readiness_service = graph.readiness_service
        self.authoring_service = graph.authoring_service

    def configure_runtime_readiness(
        self,
        *,
        tool_readiness_port: SkillToolReadinessPort,
    ) -> None:
        self.tool_readiness_port = tool_readiness_port
        if self.readiness_service is not None:
            self.readiness_service.tool_readiness_port = tool_readiness_port
        if self.authoring_service is not None:
            self.authoring_service.tool_readiness_port = tool_readiness_port

    def create(self, request: SkillCreateRequest) -> SkillMutationResult:
        assert self.package_service is not None
        return self.package_service.create(request)

    def update(self, request: SkillUpdateRequest) -> SkillMutationResult:
        assert self.package_service is not None
        return self.package_service.update(request)

    def write_instructions(
        self,
        *,
        workspace_dir: str | None,
        skill_name: str,
        content: str,
    ) -> SkillMutationResult:
        assert self.package_service is not None
        return self.package_service.write_instructions(
            workspace_dir=workspace_dir,
            skill_name=skill_name,
            content=content,
        )

    def write_file(
        self,
        *,
        workspace_dir: str | None,
        skill_name: str,
        path: str,
        content: str,
    ) -> SkillMutationResult:
        assert self.package_service is not None
        return self.package_service.write_file(
            workspace_dir=workspace_dir,
            skill_name=skill_name,
            path=path,
            content=content,
        )

    def delete_file(
        self,
        *,
        workspace_dir: str | None,
        skill_name: str,
        path: str,
    ) -> SkillMutationResult:
        assert self.package_service is not None
        return self.package_service.delete_file(
            workspace_dir=workspace_dir,
            skill_name=skill_name,
            path=path,
        )

    def build_runtime_request_catalog(
        self,
        *,
        workspace_dir: str | None,
        surface: str,
    ) -> SkillRuntimeRequestCatalog | None:
        assert self.catalog_service is not None
        return self.catalog_service.build_runtime_request_catalog(
            workspace_dir=workspace_dir,
            surface=surface,
        )

    def resolve_runtime_request_catalog(
        self,
        *,
        workspace_dir: str | None,
        surface: str,
        available_tool_ids: tuple[str, ...],
        interface: str | None = None,
        agent_id: str | None = None,
        run_id: str | None = None,
        session_key: str | None = None,
        active_session_id: str | None = None,
    ) -> SkillRuntimeRequestResolution:
        assert self.catalog_service is not None
        return self.catalog_service.resolve_runtime_request_catalog(
            workspace_dir=workspace_dir,
            surface=surface,
            available_tool_ids=available_tool_ids,
            interface=interface,
            agent_id=agent_id,
            run_id=run_id,
            session_key=session_key,
            active_session_id=active_session_id,
        )

    def list_available(
        self,
        *,
        workspace_dir: str | None,
        surface: str,
        include_disabled: bool = False,
    ) -> tuple[SkillPackage, ...]:
        assert self.catalog_service is not None
        return self.catalog_service.list_available(
            workspace_dir=workspace_dir,
            surface=surface,
            include_disabled=include_disabled,
        )

    def get(
        self,
        *,
        workspace_dir: str | None,
        skill_name: str,
        surface: str,
        include_disabled: bool = False,
    ) -> SkillPackage:
        assert self.catalog_service is not None
        return self.catalog_service.get(
            workspace_dir=workspace_dir,
            skill_name=skill_name,
            surface=surface,
            include_disabled=include_disabled,
        )

    def read(
        self,
        *,
        workspace_dir: str | None,
        skill_name: str,
        path: str | None,
        surface: str,
    ) -> SkillReadResult:
        assert self.package_service is not None
        return self.package_service.read(
            workspace_dir=workspace_dir,
            skill_name=skill_name,
            path=path,
            surface=surface,
        )

    def list_sources(
        self,
        *,
        workspace_dir: str | None,
        surface: str,
    ) -> tuple[SkillSource, ...]:
        assert self.source_service is not None
        return self.source_service.list_sources(
            workspace_dir=workspace_dir,
            surface=surface,
        )

    def create_source(
        self,
        request: SkillSourceCreateRequest,
    ) -> SkillSourceMutationResult:
        assert self.source_service is not None
        return self.source_service.create_source(request)

    def update_source(
        self,
        request: SkillSourceUpdateRequest,
    ) -> SkillSourceMutationResult:
        assert self.source_service is not None
        return self.source_service.update_source(request)

    def delete_source(
        self,
        *,
        source_id: str,
    ) -> SkillSourceMutationResult:
        assert self.source_service is not None
        return self.source_service.delete_source(source_id=source_id)

    def sync(
        self,
        *,
        workspace_dir: str | None,
        source_id: str | None,
        surface: str,
    ) -> SkillSyncResult:
        assert self.source_service is not None
        return self.source_service.sync(
            workspace_dir=workspace_dir,
            source_id=source_id,
            surface=surface,
        )

    def list_installations(
        self,
        *,
        skill_name: str | None = None,
        source_id: str | None = None,
        limit: int = 100,
    ) -> tuple[object, ...]:
        if self.owner_catalog_repository is None:
            return ()
        return self.owner_catalog_repository.list_installations(
            skill_id=skill_name,
            source_id=source_id,
            limit=limit,
        )

    def readiness(
        self,
        *,
        workspace_dir: str | None,
        skill_name: str | None,
        surface: str,
    ) -> dict[str, SkillReadiness]:
        assert self.readiness_service is not None
        return self.readiness_service.readiness(
            workspace_dir=workspace_dir,
            skill_name=skill_name,
            surface=surface,
        )

    def enable(
        self,
        *,
        workspace_dir: str | None,
        skill_name: str,
        reason: str | None,
        surface: str,
    ) -> SkillMutationResult:
        assert self.governance_service is not None
        return self.governance_service.enable(
            workspace_dir=workspace_dir,
            skill_name=skill_name,
            reason=reason,
            surface=surface,
        )

    def disable(
        self,
        *,
        workspace_dir: str | None,
        skill_name: str,
        reason: str | None,
        surface: str,
    ) -> SkillMutationResult:
        assert self.governance_service is not None
        return self.governance_service.disable(
            workspace_dir=workspace_dir,
            skill_name=skill_name,
            reason=reason,
            surface=surface,
        )

    def uninstall(
        self,
        *,
        workspace_dir: str | None,
        skill_name: str,
        surface: str,
    ) -> SkillMutationResult:
        assert self.package_service is not None
        return self.package_service.uninstall(
            workspace_dir=workspace_dir,
            skill_name=skill_name,
            surface=surface,
        )

    def package_enabled(self, package: SkillPackage) -> bool:
        assert self.readiness_service is not None
        return self.readiness_service.package_enabled(package)

    def validate(
        self,
        *,
        path: str,
    ) -> SkillPackage:
        assert self.package_service is not None
        return self.package_service.validate(path=path)

    def install(
        self,
        *,
        source_dir: str,
        scope: SkillInstallScope,
        workspace_dir: str | None,
    ) -> InstalledSkill:
        assert self.package_service is not None
        return self.package_service.install(
            source_dir=source_dir,
            scope=scope,
            workspace_dir=workspace_dir,
        )

    def create_draft(self, request: SkillDraftCreateRequest) -> SkillDraft:
        assert self.authoring_service is not None
        return self.authoring_service.create_draft(request)

    def update_draft(
        self,
        *,
        draft_id: str,
        request: SkillDraftUpdateRequest,
    ) -> SkillDraft:
        assert self.authoring_service is not None
        return self.authoring_service.update_draft(
            draft_id=draft_id,
            request=request,
        )

    def list_drafts(
        self,
        *,
        status: str | None = None,
        skill_name: str | None = None,
        run_id: str | None = None,
        workspace_dir: str | None = None,
        limit: int = 100,
    ) -> tuple[SkillDraft, ...]:
        assert self.authoring_service is not None
        return self.authoring_service.list_drafts(
            status=status,
            skill_name=skill_name,
            run_id=run_id,
            workspace_dir=workspace_dir,
            limit=limit,
        )

    def get_draft(self, draft_id: str) -> SkillDraft:
        assert self.authoring_service is not None
        return self.authoring_service.get_draft(draft_id)

    def validate_draft(self, draft_id: str) -> SkillDraft:
        assert self.authoring_service is not None
        return self.authoring_service.validate_draft(draft_id)

    def build_draft_diff(self, draft_id: str) -> SkillDraft:
        assert self.authoring_service is not None
        return self.authoring_service.build_diff(draft_id)

    def apply_draft(
        self,
        *,
        draft_id: str,
        reason: str | None = None,
    ) -> SkillDraft:
        assert self.authoring_service is not None
        return self.authoring_service.apply_draft(draft_id=draft_id, reason=reason)

    def reject_draft(
        self,
        *,
        draft_id: str,
        reason: str | None = None,
    ) -> SkillDraft:
        assert self.authoring_service is not None
        return self.authoring_service.reject_draft(
            draft_id=draft_id,
            reason=reason,
        )

    def delete_draft(self, draft_id: str) -> SkillDraft:
        assert self.authoring_service is not None
        return self.authoring_service.delete_draft(draft_id)

    def list_draft_audit(
        self,
        *,
        draft_id: str,
        limit: int = 100,
    ) -> tuple[SkillDraftAuditRecord, ...]:
        assert self.authoring_service is not None
        return self.authoring_service.list_draft_audit(
            draft_id=draft_id,
            limit=limit,
        )
