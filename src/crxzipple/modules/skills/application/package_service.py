from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

from crxzipple.modules.skills.application.catalog_service import SkillCatalogService
from crxzipple.modules.skills.application.events import (
    SKILL_CREATE_SUCCEEDED_EVENT,
    SKILL_DELETE_SUCCEEDED_EVENT,
    SKILL_INSTALL_FAILED_EVENT,
    SKILL_INSTALL_SUCCEEDED_EVENT,
    SKILL_READ_FAILED_EVENT,
    SKILL_READ_SUCCEEDED_EVENT,
    SKILL_UPDATE_SUCCEEDED_EVENT,
    SKILL_VALIDATE_FAILED_EVENT,
    SKILL_VALIDATE_SUCCEEDED_EVENT,
    SkillEventEmitter,
    emit_skill_event,
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
        self.source_service.sync(
            workspace_dir=request.workspace_dir,
            source_id=result.skill.source,
            surface="",
        )
        emit_skill_event(
            self.event_emitter,
            SKILL_CREATE_SUCCEEDED_EVENT,
            status="succeeded",
            payload={
                "skill": result.skill.name,
                "skill_name": result.skill.name,
                "source": result.skill.source,
                "workspace_dir": request.workspace_dir or "",
                "path": result.skill.root_path,
            },
        )
        self._record_installation(
            action="package_create",
            status=SkillInstallationStatus.SUCCEEDED,
            package=result.skill,
            target_uri=result.skill.root_path,
            workspace_dir=request.workspace_dir,
            message=result.message,
        )
        return result

    def update(self, request: SkillUpdateRequest) -> SkillMutationResult:
        result = self.repository.update(request)
        self.source_service.sync(
            workspace_dir=request.workspace_dir,
            source_id=result.skill.source,
            surface="",
        )
        emit_skill_event(
            self.event_emitter,
            SKILL_UPDATE_SUCCEEDED_EVENT,
            status="succeeded",
            payload={
                "skill": result.skill.name,
                "skill_name": result.skill.name,
                "source": result.skill.source,
                "workspace_dir": request.workspace_dir or "",
                "path": result.skill.root_path,
            },
        )
        self._record_installation(
            action="package_update",
            status=SkillInstallationStatus.SUCCEEDED,
            package=result.skill,
            target_uri=result.skill.root_path,
            workspace_dir=request.workspace_dir,
            message=result.message,
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
        self.source_service.sync(
            workspace_dir=workspace_dir,
            source_id=result.skill.source,
            surface="",
        )
        self._emit_package_updated(
            result,
            workspace_dir=workspace_dir,
            update_kind="instructions",
            path=result.skill.instructions_path,
        )
        self._record_installation(
            action="package_update",
            status=SkillInstallationStatus.SUCCEEDED,
            package=result.skill,
            target_uri=result.skill.instructions_path,
            workspace_dir=workspace_dir,
            message=result.message,
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
        self.source_service.sync(
            workspace_dir=workspace_dir,
            source_id=result.skill.source,
            surface="",
        )
        self._emit_package_updated(
            result,
            workspace_dir=workspace_dir,
            update_kind="file",
            path=path,
        )
        self._record_installation(
            action="package_update",
            status=SkillInstallationStatus.SUCCEEDED,
            package=result.skill,
            target_uri=path,
            workspace_dir=workspace_dir,
            message=result.message,
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
        self.source_service.sync(
            workspace_dir=workspace_dir,
            source_id=result.skill.source,
            surface="",
        )
        self._emit_package_updated(
            result,
            workspace_dir=workspace_dir,
            update_kind="file_deleted",
            path=path,
        )
        self._record_installation(
            action="package_update",
            status=SkillInstallationStatus.SUCCEEDED,
            package=result.skill,
            target_uri=path,
            workspace_dir=workspace_dir,
            message=result.message,
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
            emit_skill_event(
                self.event_emitter,
                SKILL_READ_FAILED_EVENT,
                status="failed",
                level="error",
                payload={
                    "skill": skill_name,
                    "skill_name": skill_name,
                    "surface": surface,
                    "workspace_dir": workspace_dir or "",
                    "path": path or "",
                    "duration_ms": _duration_ms(started_at),
                    "error_message": str(exc),
                },
            )
            raise
        emit_skill_event(
            self.event_emitter,
            SKILL_READ_SUCCEEDED_EVENT,
            status="succeeded",
            payload={
                "skill": result.package.name,
                "skill_name": result.package.name,
                "surface": surface,
                "workspace_dir": workspace_dir or "",
                "path": result.requested_path,
                "resolved_path": result.resolved_path,
                "source": result.package.source,
                "duration_ms": _duration_ms(started_at),
            },
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
        self.source_service.sync(
            workspace_dir=workspace_dir,
            source_id=result.skill.source,
            surface="",
        )
        emit_skill_event(
            self.event_emitter,
            SKILL_DELETE_SUCCEEDED_EVENT,
            status="succeeded",
            payload={
                "skill": result.skill.name,
                "skill_name": result.skill.name,
                "source": result.skill.source,
                "workspace_dir": workspace_dir or "",
                "path": result.skill.root_path,
            },
        )
        self._record_installation(
            action="package_delete",
            status=SkillInstallationStatus.SUCCEEDED,
            package=result.skill,
            target_uri=result.skill.root_path,
            workspace_dir=workspace_dir,
            message=result.message,
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
            emit_skill_event(
                self.event_emitter,
                SKILL_VALIDATE_FAILED_EVENT,
                status="failed",
                level="error",
                payload={
                    "path": path,
                    "duration_ms": _duration_ms(started_at),
                    "error_message": str(exc),
                },
            )
            raise
        emit_skill_event(
            self.event_emitter,
            SKILL_VALIDATE_SUCCEEDED_EVENT,
            status="succeeded",
            payload={
                "skill": package.name,
                "skill_name": package.name,
                "path": path,
                "source": package.source,
                "root_path": package.root_path,
                "required_tools": list(package.requirements.required_tools),
                "duration_ms": _duration_ms(started_at),
            },
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
            emit_skill_event(
                self.event_emitter,
                SKILL_INSTALL_FAILED_EVENT,
                status="failed",
                level="error",
                payload={
                    "source_dir": source_dir,
                    "scope": scope.value,
                    "workspace_dir": workspace_dir or "",
                    "duration_ms": _duration_ms(started_at),
                    "error_message": str(exc),
                },
            )
            self._record_installation(
                action="package_install",
                status=SkillInstallationStatus.FAILED,
                source_uri=source_dir,
                target_uri=workspace_dir or scope.value,
                workspace_dir=workspace_dir,
                message=str(exc),
                metadata={"scope": scope.value},
            )
            raise
        emit_skill_event(
            self.event_emitter,
            SKILL_INSTALL_SUCCEEDED_EVENT,
            status="succeeded",
            payload={
                "skill": result.package.name,
                "skill_name": result.package.name,
                "source": result.package.source,
                "source_dir": source_dir,
                "scope": result.scope.value,
                "workspace_dir": workspace_dir or "",
                "target_root": result.target_root,
                "target_path": result.target_path,
                "required_tools": list(result.package.requirements.required_tools),
                "duration_ms": _duration_ms(started_at),
            },
        )
        self.source_service.sync(
            workspace_dir=workspace_dir,
            source_id=result.package.source,
            surface="",
        )
        self._record_installation(
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

    def _emit_package_updated(
        self,
        result: SkillMutationResult,
        *,
        workspace_dir: str | None,
        update_kind: str,
        path: str,
    ) -> None:
        emit_skill_event(
            self.event_emitter,
            SKILL_UPDATE_SUCCEEDED_EVENT,
            status="succeeded",
            payload={
                "skill": result.skill.name,
                "skill_name": result.skill.name,
                "source": result.skill.source,
                "workspace_dir": workspace_dir or "",
                "path": path,
                "update_kind": update_kind,
            },
        )

    def _record_installation(
        self,
        *,
        action: str,
        status: SkillInstallationStatus,
        package: SkillPackage | None = None,
        source_uri: str | None = None,
        target_uri: str | None = None,
        workspace_dir: str | None = None,
        message: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        self.owner_state.record_installation(
            action=action,
            status=status,
            package=package,
            source_uri=source_uri,
            target_uri=target_uri,
            workspace_dir=workspace_dir,
            message=message,
            metadata=metadata,
        )


def _duration_ms(started_at: float) -> int:
    return max(0, round((perf_counter() - started_at) * 1000))
