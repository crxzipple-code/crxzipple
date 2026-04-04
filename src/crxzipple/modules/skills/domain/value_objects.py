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
    instructions_path: str = "SKILL.md"
    required_tools: tuple[str, ...] = field(default_factory=tuple)
    optional_tools: tuple[str, ...] = field(default_factory=tuple)
    allowed_tools: tuple[str, ...] = field(default_factory=tuple)
