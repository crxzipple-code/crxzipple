from __future__ import annotations

from typing import Protocol

from crxzipple.modules.skills.application.models import (
    SkillCatalogPrompt,
    InstalledSkill,
    SkillPackage,
    SkillReadResult,
)
from crxzipple.modules.skills.domain import SkillInstallScope


class SkillCatalogPort(Protocol):
    def build_prompt_catalog(
        self,
        *,
        workspace_dir: str | None,
        surface: str,
    ) -> SkillCatalogPrompt | None:
        ...

    def list_available(
        self,
        *,
        workspace_dir: str | None,
        surface: str,
    ) -> tuple[SkillPackage, ...]:
        ...


class SkillReadPort(Protocol):
    def read(
        self,
        *,
        workspace_dir: str | None,
        skill_name: str,
        path: str | None,
        surface: str,
    ) -> SkillReadResult:
        ...


class SkillInspectionPort(Protocol):
    def get(
        self,
        *,
        workspace_dir: str | None,
        skill_name: str,
        surface: str,
    ) -> SkillPackage:
        ...

    def validate(
        self,
        *,
        path: str,
    ) -> SkillPackage:
        ...


class SkillInstallationPort(Protocol):
    def install(
        self,
        *,
        source_dir: str,
        scope: SkillInstallScope,
        workspace_dir: str | None,
    ) -> InstalledSkill:
        ...
