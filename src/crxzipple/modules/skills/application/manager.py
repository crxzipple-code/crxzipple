from __future__ import annotations

from dataclasses import dataclass

from crxzipple.modules.skills.application.catalog import (
    build_skill_catalog_prompt,
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
)
from crxzipple.modules.skills.domain import SkillInstallScope
from crxzipple.modules.skills.infrastructure.filesystem.repository import (
    FilesystemSkillRepository,
)


@dataclass(slots=True)
class SkillManager(
    SkillCatalogPort,
    SkillReadPort,
    SkillInspectionPort,
    SkillInstallationPort,
):
    repository: FilesystemSkillRepository

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
        del surface
        return self.repository.list_available(workspace_dir=workspace_dir)

    def get(
        self,
        *,
        workspace_dir: str | None,
        skill_name: str,
        surface: str,
    ) -> SkillPackage:
        del surface
        return self.repository.get(
            workspace_dir=workspace_dir,
            skill_name=skill_name,
        )

    def read(
        self,
        *,
        workspace_dir: str | None,
        skill_name: str,
        path: str | None,
        surface: str,
    ) -> SkillReadResult:
        del surface
        return self.repository.read(
            workspace_dir=workspace_dir,
            skill_name=skill_name,
            path=path,
        )

    def validate(
        self,
        *,
        path: str,
    ) -> SkillPackage:
        return self.repository.validate(path=path)

    def install(
        self,
        *,
        source_dir: str,
        scope: SkillInstallScope,
        workspace_dir: str | None,
    ) -> InstalledSkill:
        return self.repository.install(
            source_dir=source_dir,
            scope=scope,
            workspace_dir=workspace_dir,
        )
