from __future__ import annotations

from dataclasses import dataclass

from crxzipple.modules.skills.application.catalog import (
    build_skill_catalog_prompt,
)
from crxzipple.modules.skills.application.models import (
    SkillCatalogPrompt,
    SkillPackage,
)
from crxzipple.modules.skills.application.owner_state import SkillOwnerStateService
from crxzipple.modules.skills.application.ports import SkillRepositoryPort
from crxzipple.modules.skills.application.prompt_resolver import (
    SkillPromptResolution,
    SkillPromptResolutionContext,
    SkillPromptResolver,
)
from crxzipple.modules.skills.application.surface import skill_surface_matches
from crxzipple.modules.skills.domain import SkillNotFoundError


@dataclass(slots=True)
class SkillCatalogService:
    repository: SkillRepositoryPort
    owner_state: SkillOwnerStateService
    prompt_resolver: SkillPromptResolver

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

    def resolve_prompt_catalog(
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
    ) -> SkillPromptResolution:
        packages = self.list_available(
            workspace_dir=workspace_dir,
            surface=surface,
        )
        context = SkillPromptResolutionContext(
            workspace_dir=workspace_dir,
            surface=surface,
            interface=interface,
            agent_id=agent_id,
            run_id=run_id,
            session_key=session_key,
            active_session_id=active_session_id,
        )
        resolution = self.prompt_resolver.resolve(
            packages,
            available_tool_ids=available_tool_ids,
            context=context,
        )
        self.owner_state.persist_prompt_readiness_snapshots(
            packages=packages,
            resolution=resolution,
            context=context,
        )
        return resolution

    def list_available(
        self,
        *,
        workspace_dir: str | None,
        surface: str,
        include_disabled: bool = False,
    ) -> tuple[SkillPackage, ...]:
        packages = self.discover_packages(
            workspace_dir=workspace_dir,
            surface=surface,
        )
        if include_disabled:
            return packages
        return tuple(package for package in packages if self.owner_state.package_enabled(package))

    def discover_packages(
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
            if skill_surface_matches(package.manifest.surfaces, normalized_surface)
        )

    def get(
        self,
        *,
        workspace_dir: str | None,
        skill_name: str,
        surface: str,
        include_disabled: bool = False,
    ) -> SkillPackage:
        normalized_name = skill_name.strip()
        for package in self.list_available(
            workspace_dir=workspace_dir,
            surface=surface,
            include_disabled=include_disabled,
        ):
            if package.name == normalized_name:
                return package
        raise SkillNotFoundError(f"Skill '{normalized_name}' is not available.")
