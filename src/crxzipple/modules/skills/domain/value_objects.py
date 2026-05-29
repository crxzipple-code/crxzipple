from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class SkillInstallScope(str, Enum):
    WORKSPACE = "workspace"
    GLOBAL = "global"


@dataclass(frozen=True, slots=True)
class SkillManifest:
    api_version: str
    kind: str
    name: str
    description: str
    version: str | None = None
    tags: tuple[str, ...] = field(default_factory=tuple)
    when_to_use: str | None = None
    anti_patterns: tuple[str, ...] = field(default_factory=tuple)
    instructions_path: str = "SKILL.md"
    required_tools: tuple[str, ...] = field(default_factory=tuple)
    optional_tools: tuple[str, ...] = field(default_factory=tuple)
    suggested_tools: tuple[str, ...] = field(default_factory=tuple)
    allowed_tools: tuple[str, ...] = field(default_factory=tuple)
    required_effects: tuple[str, ...] = field(default_factory=tuple)
    required_access: tuple[str, ...] = field(default_factory=tuple)
    surfaces: tuple[str, ...] = field(default_factory=tuple)
    supported_platforms: tuple[str, ...] = field(default_factory=tuple)
    setup_hints: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class SkillRequirements:
    required_tools: tuple[str, ...] = field(default_factory=tuple)
    optional_tools: tuple[str, ...] = field(default_factory=tuple)
    suggested_tools: tuple[str, ...] = field(default_factory=tuple)
    required_effects: tuple[str, ...] = field(default_factory=tuple)
    surfaces: tuple[str, ...] = field(default_factory=tuple)
    supported_platforms: tuple[str, ...] = field(default_factory=tuple)
    required_access: tuple[str, ...] = field(default_factory=tuple)
    setup_hints: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_manifest(cls, manifest: SkillManifest) -> "SkillRequirements":
        suggested_tools = manifest.suggested_tools or manifest.allowed_tools
        return cls(
            required_tools=manifest.required_tools,
            optional_tools=manifest.optional_tools,
            suggested_tools=suggested_tools,
            required_effects=manifest.required_effects,
            surfaces=manifest.surfaces,
            supported_platforms=manifest.supported_platforms,
            required_access=manifest.required_access,
            setup_hints=manifest.setup_hints,
        )

    def to_payload(self) -> dict[str, object]:
        return {
            "required_tools": list(self.required_tools),
            "optional_tools": list(self.optional_tools),
            "suggested_tools": list(self.suggested_tools),
            "required_effects": list(self.required_effects),
            "surfaces": list(self.surfaces),
            "supported_platforms": list(self.supported_platforms),
            "required_access": list(self.required_access),
            "setup_hints": list(self.setup_hints),
        }
