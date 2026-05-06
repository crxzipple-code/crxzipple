from __future__ import annotations

from typing import Protocol

from crxzipple.modules.skills.application import SkillCatalogPrompt, SkillPackage


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
