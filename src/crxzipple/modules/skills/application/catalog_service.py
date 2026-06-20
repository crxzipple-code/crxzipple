from __future__ import annotations

from dataclasses import dataclass

from crxzipple.modules.skills.application.catalog import (
    build_skill_runtime_request_catalog,
)
from crxzipple.modules.skills.application.models import (
    SkillRuntimeRequestCatalog,
    SkillPackage,
)
from crxzipple.modules.skills.application.owner_state import SkillOwnerStateService
from crxzipple.modules.skills.application.ports import SkillRepositoryPort
from crxzipple.modules.skills.application.runtime_request_resolver import (
    SkillRuntimeRequestResolution,
    SkillRuntimeRequestResolutionContext,
    SkillRuntimeRequestResolver,
)
from crxzipple.modules.skills.application.surface import skill_surface_matches
from crxzipple.modules.skills.domain import SkillNotFoundError


@dataclass(slots=True)
class SkillCatalogService:
    repository: SkillRepositoryPort
    owner_state: SkillOwnerStateService
    runtime_request_resolver: SkillRuntimeRequestResolver
    persist_runtime_request_readiness: bool = True

    def build_runtime_request_catalog(
        self,
        *,
        workspace_dir: str | None,
        surface: str,
    ) -> SkillRuntimeRequestCatalog | None:
        return build_skill_runtime_request_catalog(
            self.list_available(
                workspace_dir=workspace_dir,
                surface=surface,
            ),
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
        packages = self.list_available(
            workspace_dir=workspace_dir,
            surface=surface,
        )
        context = SkillRuntimeRequestResolutionContext(
            workspace_dir=workspace_dir,
            surface=surface,
            interface=interface,
            agent_id=agent_id,
            run_id=run_id,
            session_key=session_key,
            active_session_id=active_session_id,
        )
        resolution = self.runtime_request_resolver.resolve(
            packages,
            available_tool_ids=available_tool_ids,
            context=context,
        )
        if self.persist_runtime_request_readiness:
            self.owner_state.persist_runtime_request_readiness_snapshots(
                packages=packages,
                resolution=resolution,
                context=context,
            )
            self.owner_state.record_runtime_request_resolution_completed(
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
