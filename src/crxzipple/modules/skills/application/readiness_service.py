from __future__ import annotations

from dataclasses import dataclass, field

from crxzipple.modules.skills.application.catalog_service import SkillCatalogService
from crxzipple.modules.skills.application.models import (
    SkillPackage,
    SkillReadiness,
    SkillReadinessStatus,
)
from crxzipple.modules.skills.application.owner_state import SkillOwnerStateService
from crxzipple.modules.skills.application.prompt_resolver import (
    ResolvedSkillReadiness,
    SkillPromptResolutionContext,
    SkillPromptResolver,
    SkillToolReadinessPort,
)


@dataclass(slots=True)
class SkillReadinessService:
    catalog_service: SkillCatalogService
    owner_state: SkillOwnerStateService
    prompt_resolver: SkillPromptResolver = field(default_factory=SkillPromptResolver)
    tool_readiness_port: SkillToolReadinessPort | None = None

    def readiness(
        self,
        *,
        workspace_dir: str | None,
        skill_name: str | None,
        surface: str,
    ) -> dict[str, SkillReadiness]:
        packages: tuple[SkillPackage, ...]
        if skill_name:
            package = self.catalog_service.get(
                workspace_dir=workspace_dir,
                skill_name=skill_name,
                surface=surface,
                include_disabled=True,
            )
            packages = (package,)
        else:
            packages = self.catalog_service.discover_packages(
                workspace_dir=workspace_dir,
                surface=surface,
            )
        readiness = self._readiness_for_packages(
            packages=packages,
            workspace_dir=workspace_dir,
            surface=surface,
        )
        return readiness

    def package_enabled(self, package: SkillPackage) -> bool:
        return self.owner_state.package_enabled(package)

    def persist_readiness_snapshots(
        self,
        *,
        packages: tuple[SkillPackage, ...],
        readiness: dict[str, SkillReadiness],
    ) -> None:
        self.owner_state.persist_readiness_snapshots(
            packages=packages,
            readiness=readiness,
        )

    def readiness_for_package(self, package: SkillPackage) -> SkillReadiness:
        if self.tool_readiness_port is None:
            return self.owner_state.readiness_for_package(package)
        if not self.package_enabled(package):
            return SkillReadiness(
                status=SkillReadinessStatus.DISABLED,
                ready=False,
                setup_hints=package.requirements.setup_hints,
            )
        resolution = self.prompt_resolver.resolve(
            (package,),
            available_tool_ids=self.tool_readiness_port.list_available_tool_ids(),
            context=SkillPromptResolutionContext(),
        )
        return _skill_readiness_from_resolved(
            resolution.skills[0].readiness,
            setup_hints=package.requirements.setup_hints,
        )

    def _readiness_for_packages(
        self,
        *,
        packages: tuple[SkillPackage, ...],
        workspace_dir: str | None,
        surface: str,
    ) -> dict[str, SkillReadiness]:
        if self.tool_readiness_port is None:
            readiness = {
                package.name: self.owner_state.readiness_for_package(package)
                for package in packages
            }
            self.persist_readiness_snapshots(packages=packages, readiness=readiness)
            return readiness

        disabled_readiness: dict[str, SkillReadiness] = {}
        enabled_packages: list[SkillPackage] = []
        for package in packages:
            if self.package_enabled(package):
                enabled_packages.append(package)
                continue
            disabled_readiness[package.name] = SkillReadiness(
                status=SkillReadinessStatus.DISABLED,
                ready=False,
                setup_hints=package.requirements.setup_hints,
            )

        context = SkillPromptResolutionContext(
            workspace_dir=workspace_dir,
            surface=surface,
        )
        resolution = self.prompt_resolver.resolve(
            tuple(enabled_packages),
            available_tool_ids=self.tool_readiness_port.list_available_tool_ids(),
            context=context,
        )
        readiness: dict[str, SkillReadiness] = {
            resolved.package.name: _skill_readiness_from_resolved(
                resolved.readiness,
                setup_hints=resolved.package.requirements.setup_hints,
            )
            for resolved in resolution.skills
        }
        readiness.update(disabled_readiness)
        if enabled_packages:
            self.owner_state.persist_prompt_readiness_snapshots(
                packages=tuple(enabled_packages),
                resolution=resolution,
                context=context,
            )
        if disabled_readiness:
            disabled_packages = tuple(
                package
                for package in packages
                if package.name in disabled_readiness
            )
            self.persist_readiness_snapshots(
                packages=disabled_packages,
                readiness=readiness,
            )
        return readiness


def _skill_readiness_from_resolved(
    readiness: ResolvedSkillReadiness,
    *,
    setup_hints: tuple[str, ...],
) -> SkillReadiness:
    return SkillReadiness(
        status=SkillReadinessStatus(readiness.status),
        ready=readiness.ready,
        missing_tools=readiness.missing_tools,
        missing_access=readiness.missing_access,
        missing_effects=readiness.missing_effects,
        unsupported_surfaces=readiness.unsupported_surfaces,
        unsupported_platforms=readiness.unsupported_platforms,
        setup_hints=setup_hints,
    )
