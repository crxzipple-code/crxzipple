from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatchcase
from typing import Any, Iterable, Mapping

from crxzipple.modules.skills.application.catalog import build_skill_catalog_prompt
from crxzipple.modules.skills.application.models import (
    InstalledSkill,
    SkillCatalogPrompt,
    SkillPackage,
    SkillReadResult,
)
from crxzipple.modules.skills.domain import SkillInstallScope, SkillNotFoundError
from crxzipple.shared.settings import SkillEnablementConfig


SkillEnablementConfigLike = SkillEnablementConfig | Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class SkillEnablementTarget:
    skill_id: str
    source: str
    tags: tuple[str, ...] = ()


class SkillEnablementService:
    def __init__(
        self,
        configs: Iterable[SkillEnablementConfigLike] = (),
    ) -> None:
        self._configs = tuple(_skill_enablement_config(config) for config in configs)

    @property
    def configs(self) -> tuple[SkillEnablementConfig, ...]:
        return self._configs

    def is_enabled(self, package: SkillPackage) -> bool:
        enabled = True
        target = SkillEnablementTarget(
            skill_id=package.name,
            source=package.source,
            tags=package.tags,
        )
        for config in self._configs:
            if _skill_enablement_matches(config, target):
                enabled = config.enabled
        return enabled


@dataclass(slots=True)
class SkillEnablementManagerAdapter:
    manager: Any
    enablement: SkillEnablementService

    def build_prompt_catalog(
        self,
        *,
        workspace_dir: str | None,
        surface: str,
    ) -> SkillCatalogPrompt | None:
        return build_skill_catalog_prompt(
            self.list_available(workspace_dir=workspace_dir, surface=surface),
        )

    def list_available(
        self,
        *,
        workspace_dir: str | None,
        surface: str,
    ) -> tuple[SkillPackage, ...]:
        return tuple(
            package
            for package in self.manager.list_available(
                workspace_dir=workspace_dir,
                surface=surface,
            )
            if self.enablement.is_enabled(package)
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
        self.get(workspace_dir=workspace_dir, skill_name=skill_name, surface=surface)
        return self.manager.read(
            workspace_dir=workspace_dir,
            skill_name=skill_name,
            path=path,
            surface=surface,
        )

    def validate(self, *, path: str) -> SkillPackage:
        return self.manager.validate(path=path)

    def install(
        self,
        *,
        source_dir: str,
        scope: SkillInstallScope,
        workspace_dir: str | None,
    ) -> InstalledSkill:
        return self.manager.install(
            source_dir=source_dir,
            scope=scope,
            workspace_dir=workspace_dir,
        )


def _skill_enablement_config(
    config: SkillEnablementConfigLike,
) -> SkillEnablementConfig:
    if isinstance(config, SkillEnablementConfig):
        return config
    return SkillEnablementConfig.from_payload(config)


def _skill_enablement_matches(
    config: SkillEnablementConfig,
    target: SkillEnablementTarget,
) -> bool:
    scope = config.scope.strip().lower()
    if scope in {"*", "all"}:
        scope_matches = True
    elif scope in {"skill", "skills"}:
        scope_matches = True
    elif scope in {"source", "package_source"}:
        scope_matches = config.source is not None and config.source == target.source
    else:
        scope_matches = scope == target.source
    if not scope_matches:
        return False

    if config.source is not None and config.source != target.source:
        return False
    if config.skill_id is not None and config.skill_id != target.skill_id:
        return False
    if config.pattern is not None and not fnmatchcase(target.skill_id, config.pattern):
        return False
    if (
        config.skill_id is None
        and config.pattern is None
        and config.source is None
        and scope in {"skill", "skills"}
    ):
        return False
    return True
