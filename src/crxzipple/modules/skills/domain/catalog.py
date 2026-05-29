from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from crxzipple.modules.skills.domain.exceptions import SkillValidationError
from crxzipple.modules.skills.domain.value_objects import SkillRequirements


class SkillSourceType(StrEnum):
    WORKSPACE = "workspace"
    GLOBAL = "global"
    MANAGED = "managed"
    EXTERNAL = "external"
    SYSTEM = "system"


class SkillSourceStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"
    ERROR = "error"
    DELETED = "deleted"


class SkillSourceSyncStatus(StrEnum):
    NEVER_SYNCED = "never_synced"
    SYNCING = "syncing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    STALE = "stale"


class SkillPackageStatus(StrEnum):
    ACTIVE = "active"
    INVALID = "invalid"
    REMOVED = "removed"
    DISABLED = "disabled"
    DELETED = "deleted"


class SkillEnablementTargetKind(StrEnum):
    GLOBAL = "global"
    SOURCE = "source"
    SKILL = "skill"
    TAG = "tag"
    SURFACE = "surface"


class SkillRuntimeVisibility(StrEnum):
    VISIBLE = "visible"
    HIDDEN = "hidden"
    READ_ONLY = "read_only"


class SkillReadinessStatus(StrEnum):
    READY = "ready"
    SETUP_NEEDED = "setup_needed"
    UNSUPPORTED = "unsupported"
    DISABLED = "disabled"
    INVALID = "invalid"


class SkillInstallationStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class SkillSource:
    source_id: str
    source_type: SkillSourceType | str
    root_uri: str
    status: SkillSourceStatus | str = SkillSourceStatus.ACTIVE
    sync_status: SkillSourceSyncStatus | str = SkillSourceSyncStatus.NEVER_SYNCED
    scope: str | None = None
    priority: int = 100
    enabled: bool = True
    readonly: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    last_synced_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        _require_text(self.source_id, "Skill source id")
        _require_text(self.root_uri, "Skill source root_uri")
        object.__setattr__(self, "source_type", SkillSourceType(self.source_type))
        object.__setattr__(self, "status", SkillSourceStatus(self.status))
        object.__setattr__(self, "sync_status", SkillSourceSyncStatus(self.sync_status))
        if self.priority < 0:
            raise SkillValidationError("Skill source priority cannot be negative.")
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True, slots=True)
class SkillPackageIndex:
    package_id: str
    skill_id: str
    name: str
    source_id: str
    root_uri: str
    manifest_uri: str
    instructions_uri: str
    version: str | None = None
    fingerprint: str = ""
    status: SkillPackageStatus | str = SkillPackageStatus.ACTIVE
    requirements: SkillRequirements = field(default_factory=SkillRequirements)
    capability_requirements: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    indexed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        _require_text(self.package_id, "Skill package id")
        _require_text(self.skill_id, "Skill id")
        _require_text(self.name, "Skill name")
        _require_text(self.source_id, "Skill package source_id")
        _require_text(self.root_uri, "Skill package root_uri")
        _require_text(self.manifest_uri, "Skill package manifest_uri")
        _require_text(self.instructions_uri, "Skill package instructions_uri")
        object.__setattr__(self, "status", SkillPackageStatus(self.status))
        object.__setattr__(
            self,
            "capability_requirements",
            dict(self.capability_requirements),
        )
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True, slots=True)
class SkillEnablementPolicy:
    policy_id: str
    target_kind: SkillEnablementTargetKind | str
    target_id: str | None = None
    enabled: bool = True
    trusted: bool = False
    runtime_visibility: SkillRuntimeVisibility | str = SkillRuntimeVisibility.VISIBLE
    priority: int = 100
    reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        _require_text(self.policy_id, "Skill enablement policy id")
        object.__setattr__(
            self, "target_kind", SkillEnablementTargetKind(self.target_kind)
        )
        if self.target_kind is not SkillEnablementTargetKind.GLOBAL:
            _require_text(self.target_id or "", "Skill enablement policy target_id")
        object.__setattr__(
            self,
            "runtime_visibility",
            SkillRuntimeVisibility(self.runtime_visibility),
        )
        if self.priority < 0:
            raise SkillValidationError(
                "Skill enablement policy priority cannot be negative."
            )
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True, slots=True)
class SkillReadinessSnapshot:
    skill_id: str
    status: SkillReadinessStatus | str
    checks: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    reason: str | None = None
    source_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        _require_text(self.skill_id, "Skill readiness skill_id")
        object.__setattr__(self, "status", SkillReadinessStatus(self.status))
        object.__setattr__(self, "checks", tuple(dict(check) for check in self.checks))
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True, slots=True)
class SkillInstallation:
    installation_id: str
    action: str
    status: SkillInstallationStatus | str
    source_id: str | None = None
    skill_id: str | None = None
    skill_name: str | None = None
    source_uri: str | None = None
    target_uri: str | None = None
    actor_id: str | None = None
    reason: str | None = None
    message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        _require_text(self.installation_id, "Skill installation id")
        _require_text(self.action, "Skill installation action")
        object.__setattr__(self, "status", SkillInstallationStatus(self.status))
        object.__setattr__(self, "metadata", dict(self.metadata))


def _require_text(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise SkillValidationError(f"{label} cannot be empty.")
