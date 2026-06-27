from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

from crxzipple.modules.skills.application.catalog_service import SkillCatalogService
from crxzipple.modules.skills.application.events import (
    SkillEventEmitter,
)
from crxzipple.modules.skills.application.exceptions import (
    SkillCapabilityUnavailableError,
)
from crxzipple.modules.skills.application.models import (
    InstalledSkill,
    SkillCreateRequest,
    SkillMutationResult,
    SkillPackage,
    SkillReadResult,
    SkillUpdateRequest,
)
from crxzipple.modules.skills.application.owner_state import SkillOwnerStateService
from crxzipple.modules.skills.application.package_observation import (
    emit_package_created,
    emit_package_deleted,
    emit_package_install_failed,
    emit_package_install_succeeded,
    emit_package_read_failed,
    emit_package_read_succeeded,
    emit_package_updated,
    emit_package_validate_failed,
    emit_package_validate_succeeded,
    record_package_installation,
)
from crxzipple.modules.skills.application.ports import SkillRepositoryPort
from crxzipple.modules.skills.application.source_service import SkillSourceService
from crxzipple.modules.skills.domain import (
    SkillError,
    SkillInstallationStatus,
    SkillInstallScope,
)


@dataclass(slots=True)
class SkillPackageService:
    repository: SkillRepositoryPort
    catalog_service: SkillCatalogService
    source_service: SkillSourceService
    owner_state: SkillOwnerStateService
    event_emitter: SkillEventEmitter | None = None

    def create(self, request: SkillCreateRequest) -> SkillMutationResult:
        result = self.repository.create(request)
        self._sync_package_source(result.skill, workspace_dir=request.workspace_dir)
        emit_package_created(
            self.event_emitter,
            result,
            workspace_dir=request.workspace_dir,
        )
        self._record_mutation_success(
            action="package_create",
            result=result,
            target_uri=result.skill.root_path,
            workspace_dir=request.workspace_dir,
        )
        return result

    def update(self, request: SkillUpdateRequest) -> SkillMutationResult:
        result = self.repository.update(request)
        self._sync_package_source(result.skill, workspace_dir=request.workspace_dir)
        emit_package_updated(
            self.event_emitter,
            result,
            workspace_dir=request.workspace_dir,
            update_kind="package",
            path=result.skill.root_path,
        )
        self._record_mutation_success(
            action="package_update",
            result=result,
            target_uri=result.skill.root_path,
            workspace_dir=request.workspace_dir,
        )
        return result

    def write_instructions(
        self,
        *,
        workspace_dir: str | None,
        skill_name: str,
        content: str,
    ) -> SkillMutationResult:
        result = self.repository.write_instructions(
            workspace_dir=workspace_dir,
            skill_name=skill_name,
            content=content,
        )
        self._sync_package_source(result.skill, workspace_dir=workspace_dir)
        emit_package_updated(
            self.event_emitter,
            result,
            workspace_dir=workspace_dir,
            update_kind="instructions",
            path=result.skill.instructions_path,
        )
        self._record_mutation_success(
            action="package_update",
            result=result,
            target_uri=result.skill.instructions_path,
            workspace_dir=workspace_dir,
            metadata={"update_kind": "instructions"},
        )
        return result

    def write_file(
        self,
        *,
        workspace_dir: str | None,
        skill_name: str,
        path: str,
        content: str,
    ) -> SkillMutationResult:
        result = self.repository.write_file(
            workspace_dir=workspace_dir,
            skill_name=skill_name,
            path=path,
            content=content,
        )
        self._sync_package_source(result.skill, workspace_dir=workspace_dir)
        emit_package_updated(
            self.event_emitter,
            result,
            workspace_dir=workspace_dir,
            update_kind="file",
            path=path,
        )
        self._record_mutation_success(
            action="package_update",
            result=result,
            target_uri=path,
            workspace_dir=workspace_dir,
            metadata={"update_kind": "file"},
        )
        return result

    def delete_file(
        self,
        *,
        workspace_dir: str | None,
        skill_name: str,
        path: str,
    ) -> SkillMutationResult:
        result = self.repository.delete_file(
            workspace_dir=workspace_dir,
            skill_name=skill_name,
            path=path,
        )
        self._sync_package_source(result.skill, workspace_dir=workspace_dir)
        emit_package_updated(
            self.event_emitter,
            result,
            workspace_dir=workspace_dir,
            update_kind="file_deleted",
            path=path,
        )
        self._record_mutation_success(
            action="package_update",
            result=result,
            target_uri=path,
            workspace_dir=workspace_dir,
            metadata={"update_kind": "file_deleted"},
        )
        return result

    def read(
        self,
        *,
        workspace_dir: str | None,
        skill_name: str,
        path: str | None,
        surface: str,
    ) -> SkillReadResult:
        started_at = perf_counter()
        try:
            self.catalog_service.get(
                workspace_dir=workspace_dir,
                skill_name=skill_name,
                surface=surface,
            )
            result = self.repository.read(
                workspace_dir=workspace_dir,
                skill_name=skill_name,
                path=path,
            )
        except SkillError as exc:
            emit_package_read_failed(
                self.event_emitter,
                skill_name=skill_name,
                surface=surface,
                workspace_dir=workspace_dir,
                path=path,
                started_at=started_at,
                error=exc,
            )
            raise
        emit_package_read_succeeded(
            self.event_emitter,
            result,
            surface=surface,
            workspace_dir=workspace_dir,
            started_at=started_at,
        )
        return result

    def uninstall(
        self,
        *,
        workspace_dir: str | None,
        skill_name: str,
        surface: str,
    ) -> SkillMutationResult:
        package = self.catalog_service.get(
            workspace_dir=workspace_dir,
            skill_name=skill_name,
            surface=surface,
            include_disabled=True,
        )
        if package.source == "system":
            raise SkillCapabilityUnavailableError(
                f"Skill '{package.name}' is from a readonly system source and cannot be deleted.",
            )
        result = self.repository.delete(
            workspace_dir=workspace_dir,
            skill_name=skill_name,
        )
        self._sync_package_source(result.skill, workspace_dir=workspace_dir)
        emit_package_deleted(
            self.event_emitter,
            result,
            workspace_dir=workspace_dir,
        )
        self._record_mutation_success(
            action="package_delete",
            result=result,
            target_uri=result.skill.root_path,
            workspace_dir=workspace_dir,
        )
        return result

    def validate(
        self,
        *,
        path: str,
    ) -> SkillPackage:
        started_at = perf_counter()
        try:
            package = self.repository.validate(path=path)
        except SkillError as exc:
            emit_package_validate_failed(
                self.event_emitter,
                path=path,
                started_at=started_at,
                error=exc,
            )
            raise
        emit_package_validate_succeeded(
            self.event_emitter,
            package,
            path=path,
            started_at=started_at,
        )
        return package

    def install(
        self,
        *,
        source_dir: str,
        scope: SkillInstallScope,
        workspace_dir: str | None,
    ) -> InstalledSkill:
        started_at = perf_counter()
        try:
            result = self.repository.install(
                source_dir=source_dir,
                scope=scope,
                workspace_dir=workspace_dir,
            )
        except SkillError as exc:
            emit_package_install_failed(
                self.event_emitter,
                source_dir=source_dir,
                scope=scope.value,
                workspace_dir=workspace_dir,
                started_at=started_at,
                error=exc,
            )
            record_package_installation(
                self.owner_state,
                action="package_install",
                status=SkillInstallationStatus.FAILED,
                source_uri=source_dir,
                target_uri=workspace_dir or scope.value,
                workspace_dir=workspace_dir,
                message=str(exc),
                metadata={"scope": scope.value},
            )
            raise
        emit_package_install_succeeded(
            self.event_emitter,
            result,
            source_dir=source_dir,
            workspace_dir=workspace_dir,
            started_at=started_at,
        )
        self._sync_package_source(result.package, workspace_dir=workspace_dir)
        record_package_installation(
            self.owner_state,
            action="package_install",
            status=SkillInstallationStatus.SUCCEEDED,
            package=result.package,
            source_uri=source_dir,
            target_uri=result.target_path,
            workspace_dir=workspace_dir,
            message=f"Skill '{result.package.name}' installed.",
            metadata={
                "scope": result.scope.value,
                "target_root": result.target_root,
            },
        )
        return result

    def _sync_package_source(
        self,
        package: SkillPackage,
        *,
        workspace_dir: str | None,
    ) -> None:
        self.source_service.sync(
            workspace_dir=workspace_dir,
            source_id=package.source,
            surface="",
        )

    def _record_mutation_success(
        self,
        *,
        action: str,
        result: SkillMutationResult,
        target_uri: str,
        workspace_dir: str | None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        record_package_installation(
            self.owner_state,
            action=action,
            status=SkillInstallationStatus.SUCCEEDED,
            package=result.skill,
            target_uri=target_uri,
            workspace_dir=workspace_dir,
            message=result.message,
            metadata=metadata,
        )
