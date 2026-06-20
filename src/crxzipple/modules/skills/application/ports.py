from __future__ import annotations

from typing import Protocol

from crxzipple.modules.skills.application.models import (
    InstalledSkill,
    SkillRuntimeRequestCatalog,
    SkillCreateRequest,
    SkillDraft,
    SkillDraftAuditRecord,
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
from crxzipple.modules.skills.application.runtime_request_resolver import SkillRuntimeRequestResolution
from crxzipple.modules.skills.domain import (
    SkillEnablementPolicy,
    SkillInstallation,
    SkillInstallScope,
    SkillPackageIndex,
    SkillReadinessSnapshot as DomainSkillReadinessSnapshot,
    SkillSource as DomainSkillSource,
)


class SkillCatalogPort(Protocol):
    def build_runtime_request_catalog(
        self,
        *,
        workspace_dir: str | None,
        surface: str,
    ) -> SkillRuntimeRequestCatalog | None: ...

    def list_available(
        self,
        *,
        workspace_dir: str | None,
        surface: str,
        include_disabled: bool = False,
    ) -> tuple[SkillPackage, ...]: ...

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
    ) -> SkillRuntimeRequestResolution: ...


class SkillReadPort(Protocol):
    def read(
        self,
        *,
        workspace_dir: str | None,
        skill_name: str,
        path: str | None,
        surface: str,
    ) -> SkillReadResult: ...


class SkillInspectionPort(Protocol):
    def get(
        self,
        *,
        workspace_dir: str | None,
        skill_name: str,
        surface: str,
        include_disabled: bool = False,
    ) -> SkillPackage: ...

    def validate(
        self,
        *,
        path: str,
    ) -> SkillPackage: ...


class SkillInstallationPort(Protocol):
    def create(self, request: SkillCreateRequest) -> SkillMutationResult: ...

    def update(self, request: SkillUpdateRequest) -> SkillMutationResult: ...

    def install(
        self,
        *,
        source_dir: str,
        scope: SkillInstallScope,
        workspace_dir: str | None,
    ) -> InstalledSkill: ...


class SkillGovernancePort(Protocol):
    def list_sources(
        self,
        *,
        workspace_dir: str | None,
        surface: str,
    ) -> tuple[SkillSource, ...]: ...

    def create_source(
        self,
        request: SkillSourceCreateRequest,
    ) -> SkillSourceMutationResult: ...

    def update_source(
        self,
        request: SkillSourceUpdateRequest,
    ) -> SkillSourceMutationResult: ...

    def delete_source(
        self,
        *,
        source_id: str,
    ) -> SkillSourceMutationResult: ...

    def sync(
        self,
        *,
        workspace_dir: str | None,
        source_id: str | None,
        surface: str,
    ) -> SkillSyncResult: ...

    def readiness(
        self,
        *,
        workspace_dir: str | None,
        skill_name: str | None,
        surface: str,
    ) -> dict[str, SkillReadiness]: ...

    def enable(
        self,
        *,
        workspace_dir: str | None,
        skill_name: str,
        reason: str | None,
        surface: str,
    ) -> SkillMutationResult: ...

    def disable(
        self,
        *,
        workspace_dir: str | None,
        skill_name: str,
        reason: str | None,
        surface: str,
    ) -> SkillMutationResult: ...

    def uninstall(
        self,
        *,
        workspace_dir: str | None,
        skill_name: str,
        surface: str,
    ) -> SkillMutationResult: ...


class SkillRepositoryPort(Protocol):
    def list_available(
        self, *, workspace_dir: str | None
    ) -> tuple[SkillPackage, ...]: ...

    def read(
        self,
        *,
        workspace_dir: str | None,
        skill_name: str,
        path: str | None,
    ) -> SkillReadResult: ...

    def validate(self, *, path: str) -> SkillPackage: ...

    def install(
        self,
        *,
        source_dir: str,
        scope: SkillInstallScope,
        workspace_dir: str | None,
    ) -> InstalledSkill: ...

    def delete(
        self,
        *,
        workspace_dir: str | None,
        skill_name: str,
    ) -> SkillMutationResult: ...

    def create(self, request: SkillCreateRequest) -> SkillMutationResult: ...

    def update(self, request: SkillUpdateRequest) -> SkillMutationResult: ...

    def write_instructions(
        self,
        *,
        workspace_dir: str | None,
        skill_name: str,
        content: str,
    ) -> SkillMutationResult: ...

    def write_file(
        self,
        *,
        workspace_dir: str | None,
        skill_name: str,
        path: str,
        content: str,
    ) -> SkillMutationResult: ...

    def delete_file(
        self,
        *,
        workspace_dir: str | None,
        skill_name: str,
        path: str,
    ) -> SkillMutationResult: ...


class SkillOwnerCatalogRepositoryPort(Protocol):
    def upsert_source(self, source: DomainSkillSource) -> DomainSkillSource: ...

    def get_source(self, source_id: str) -> DomainSkillSource | None: ...

    def list_sources(self) -> tuple[DomainSkillSource, ...]: ...

    def upsert_package(self, package: SkillPackageIndex) -> SkillPackageIndex: ...

    def get_package(self, package_id: str) -> SkillPackageIndex | None: ...

    def get_package_by_skill(
        self,
        *,
        source_id: str,
        skill_id: str,
    ) -> SkillPackageIndex | None: ...

    def list_packages(
        self,
        *,
        source_id: str | None = None,
        include_removed: bool = False,
    ) -> tuple[SkillPackageIndex, ...]: ...

    def upsert_enablement_policy(
        self,
        policy: SkillEnablementPolicy,
    ) -> SkillEnablementPolicy: ...

    def get_enablement_policy(
        self,
        policy_id: str,
    ) -> SkillEnablementPolicy | None: ...

    def list_enablement_policies(
        self,
        *,
        target_kind: str | None = None,
        target_id: str | None = None,
    ) -> tuple[SkillEnablementPolicy, ...]: ...

    def upsert_readiness(
        self,
        snapshot: DomainSkillReadinessSnapshot,
    ) -> DomainSkillReadinessSnapshot: ...

    def get_readiness(self, skill_id: str) -> DomainSkillReadinessSnapshot | None: ...

    def list_readiness(
        self,
        *,
        source_id: str | None = None,
    ) -> tuple[DomainSkillReadinessSnapshot, ...]: ...

    def record_installation(
        self,
        installation: SkillInstallation,
    ) -> SkillInstallation: ...

    def list_installations(
        self,
        *,
        skill_id: str | None = None,
        source_id: str | None = None,
        limit: int = 100,
    ) -> tuple[SkillInstallation, ...]: ...


class SkillAuthoringDraftRepositoryPort(Protocol):
    def save_draft(self, draft: SkillDraft) -> SkillDraft: ...

    def get_draft(self, draft_id: str) -> SkillDraft | None: ...

    def list_drafts(
        self,
        *,
        status: str | None = None,
        skill_name: str | None = None,
        run_id: str | None = None,
        workspace_dir: str | None = None,
        limit: int = 100,
    ) -> tuple[SkillDraft, ...]: ...

    def delete_draft(self, draft_id: str) -> bool: ...

    def append_draft_audit(
        self,
        record: SkillDraftAuditRecord,
    ) -> SkillDraftAuditRecord: ...

    def list_draft_audit(
        self,
        *,
        draft_id: str,
        limit: int = 100,
    ) -> tuple[SkillDraftAuditRecord, ...]: ...
