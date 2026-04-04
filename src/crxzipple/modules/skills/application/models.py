from __future__ import annotations

from dataclasses import dataclass

from crxzipple.modules.skills.domain import SkillInstallScope, SkillManifest


@dataclass(frozen=True, slots=True)
class SkillPackage:
    manifest: SkillManifest
    root_path: str
    manifest_path: str
    instructions_path: str
    source: str

    @property
    def name(self) -> str:
        return self.manifest.name

    @property
    def description(self) -> str:
        return self.manifest.description

    @property
    def version(self) -> str | None:
        return self.manifest.version

    @property
    def tags(self) -> tuple[str, ...]:
        return self.manifest.tags

    @property
    def allowed_tools(self) -> tuple[str, ...]:
        return self.manifest.allowed_tools

    @property
    def required_tools(self) -> tuple[str, ...]:
        return self.manifest.required_tools


@dataclass(frozen=True, slots=True)
class SkillReadResult:
    package: SkillPackage
    requested_path: str
    resolved_path: str
    content: str


@dataclass(frozen=True, slots=True)
class SkillCatalogPrompt:
    content: str
    metadata: dict[str, object]


@dataclass(frozen=True, slots=True)
class InstalledSkill:
    package: SkillPackage
    scope: SkillInstallScope
    target_root: str
    target_path: str
