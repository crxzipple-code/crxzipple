from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter

from crxzipple.modules.skills.application.catalog import (
    build_skill_catalog_prompt,
)
from crxzipple.modules.skills.application.events import (
    SKILL_INSTALL_FAILED_EVENT,
    SKILL_INSTALL_SUCCEEDED_EVENT,
    SKILL_READ_FAILED_EVENT,
    SKILL_READ_SUCCEEDED_EVENT,
    SKILL_VALIDATE_FAILED_EVENT,
    SKILL_VALIDATE_SUCCEEDED_EVENT,
    SkillEventEmitter,
    emit_skill_event,
)
from crxzipple.modules.skills.application.models import (
    InstalledSkill,
    SkillCatalogPrompt,
    SkillPackage,
    SkillReadResult,
)
from crxzipple.modules.skills.application.ports import (
    SkillCatalogPort,
    SkillInspectionPort,
    SkillInstallationPort,
    SkillReadPort,
    SkillRepositoryPort,
)
from crxzipple.modules.skills.domain import SkillError, SkillInstallScope, SkillNotFoundError


@dataclass(slots=True)
class SkillManager(
    SkillCatalogPort,
    SkillReadPort,
    SkillInspectionPort,
    SkillInstallationPort,
):
    repository: SkillRepositoryPort
    event_emitter: SkillEventEmitter | None = None

    def build_prompt_catalog(
        self,
        *,
        workspace_dir: str | None,
        surface: str,
    ) -> SkillCatalogPrompt | None:
        return build_skill_catalog_prompt(
            self.list_available(
                workspace_dir=workspace_dir,
                surface=surface,
            ),
        )

    def list_available(
        self,
        *,
        workspace_dir: str | None,
        surface: str,
    ) -> tuple[SkillPackage, ...]:
        packages = self.repository.list_available(workspace_dir=workspace_dir)
        normalized_surface = surface.strip() if surface else ""
        if not normalized_surface:
            return packages
        return tuple(
            package
            for package in packages
            if not package.manifest.surfaces
            or normalized_surface in package.manifest.surfaces
        )

    def get(
        self,
        *,
        workspace_dir: str | None,
        skill_name: str,
        surface: str,
    ) -> SkillPackage:
        normalized_name = skill_name.strip()
        for package in self.list_available(workspace_dir=workspace_dir, surface=surface):
            if package.name == normalized_name:
                return package
        raise SkillNotFoundError(f"Skill '{normalized_name}' is not available.")

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
            self.get(
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
        return result


def _duration_ms(started_at: float) -> int:
    return max(0, round((perf_counter() - started_at) * 1000))
