from __future__ import annotations

from dataclasses import dataclass

from crxzipple.modules.agent.domain.entities import AgentProfile


@dataclass(frozen=True, slots=True)
class MigrateAgentHomeInput:
    id: str
    home_dir: str
    workdir: str | None = None


@dataclass(frozen=True, slots=True)
class MigrateAgentHomeResult:
    profile: AgentProfile
    source_dir: str | None
    copied_paths: tuple[str, ...] = ()
    skipped_paths: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SyncAgentHomeInput:
    id: str
    home_dir: str | None = None


@dataclass(frozen=True, slots=True)
class SyncAgentHomeResult:
    profile: AgentProfile
    home_dir: str
    path: str


@dataclass(frozen=True, slots=True)
class ExportAgentHomeInput:
    id: str
    home_dir: str | None = None


@dataclass(frozen=True, slots=True)
class ExportAgentHomeResult:
    profile: AgentProfile
    home_dir: str
    path: str


@dataclass(frozen=True, slots=True)
class AgentHomeFileSnapshot:
    name: str
    path: str
    exists: bool
    language: str
    content: str


@dataclass(frozen=True, slots=True)
class AgentHomeSnapshot:
    profile: AgentProfile
    home_dir: str
    workdir: str | None
    files: tuple[AgentHomeFileSnapshot, ...]


@dataclass(frozen=True, slots=True)
class UpdateAgentHomeFilesInput:
    id: str
    files: dict[str, str]


__all__ = [
    "AgentHomeFileSnapshot",
    "AgentHomeSnapshot",
    "ExportAgentHomeInput",
    "ExportAgentHomeResult",
    "MigrateAgentHomeInput",
    "MigrateAgentHomeResult",
    "SyncAgentHomeInput",
    "SyncAgentHomeResult",
    "UpdateAgentHomeFilesInput",
]
