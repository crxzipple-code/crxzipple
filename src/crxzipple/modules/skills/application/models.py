from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from datetime import datetime

from crxzipple.modules.skills.domain import (
    SkillEnablementPolicy,
    SkillInstallScope,
    SkillManifest,
    SkillPackageIndex,
    SkillReadinessSnapshot as DomainSkillReadinessSnapshot,
    SkillRequirements,
    SkillSource as DomainSkillSource,
)


@dataclass(frozen=True, slots=True)
class SkillResource:
    path: str
    kind: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class SkillPackage:
    manifest: SkillManifest
    root_path: str
    manifest_path: str
    instructions_path: str
    source: str
    resources: tuple[SkillResource, ...] = ()
    fingerprint: str = ""

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
    def requirements(self) -> SkillRequirements:
        return SkillRequirements.from_manifest(self.manifest)

    @property
    def suggested_tools(self) -> tuple[str, ...]:
        return self.requirements.suggested_tools

    @property
    def required_tools(self) -> tuple[str, ...]:
        return self.requirements.required_tools


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


@dataclass(frozen=True, slots=True)
class SkillCreateRequest:
    name: str
    description: str
    instructions: str
    scope: SkillInstallScope = SkillInstallScope.WORKSPACE
    workspace_dir: str | None = None
    version: str | None = None
    tags: tuple[str, ...] = ()
    required_tools: tuple[str, ...] = ()
    optional_tools: tuple[str, ...] = ()
    suggested_tools: tuple[str, ...] = ()
    required_effects: tuple[str, ...] = ()
    required_access: tuple[str, ...] = ()
    surfaces: tuple[str, ...] = ()
    supported_platforms: tuple[str, ...] = ()
    setup_hints: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SkillUpdateRequest:
    skill_name: str
    workspace_dir: str | None = None
    description: str | None = None
    version: str | None = None
    tags: tuple[str, ...] | None = None
    required_tools: tuple[str, ...] | None = None
    optional_tools: tuple[str, ...] | None = None
    suggested_tools: tuple[str, ...] | None = None
    required_effects: tuple[str, ...] | None = None
    required_access: tuple[str, ...] | None = None
    surfaces: tuple[str, ...] | None = None
    supported_platforms: tuple[str, ...] | None = None
    setup_hints: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class SkillOwnerCatalogSnapshot:
    sources: tuple[DomainSkillSource, ...] = ()
    packages: tuple[SkillPackageIndex, ...] = ()
    policies: tuple[SkillEnablementPolicy, ...] = ()
    readiness: tuple[DomainSkillReadinessSnapshot, ...] = ()


class SkillSourceKind(str, Enum):
    WORKSPACE = "workspace"
    GLOBAL = "global"
    MANAGED = "managed"
    EXTERNAL = "external"
    SYSTEM = "system"
    UNKNOWN = "unknown"


class SkillReadinessStatus(str, Enum):
    READY = "ready"
    SETUP_NEEDED = "setup_needed"
    DISABLED = "disabled"
    INVALID = "invalid"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True, slots=True)
class SkillSource:
    source_id: str
    source_kind: SkillSourceKind
    root_path: str
    enabled: bool
    readonly: bool
    package_count: int
    metadata: dict[str, object]
    status: str = "active"
    sync_status: str = "never_synced"
    priority: int = 100


@dataclass(frozen=True, slots=True)
class SkillSourceCreateRequest:
    source_id: str
    root_path: str
    source_kind: SkillSourceKind = SkillSourceKind.EXTERNAL
    enabled: bool = True
    readonly: bool = False
    priority: int = 100
    metadata: dict[str, object] | None = None


@dataclass(frozen=True, slots=True)
class SkillSourceUpdateRequest:
    source_id: str
    root_path: str | None = None
    enabled: bool | None = None
    readonly: bool | None = None
    priority: int | None = None
    metadata: dict[str, object] | None = None


@dataclass(frozen=True, slots=True)
class SkillSourceMutationResult:
    source: SkillSource
    action: str
    changed: bool
    message: str


@dataclass(frozen=True, slots=True)
class SkillReadiness:
    status: SkillReadinessStatus
    ready: bool
    missing_tools: tuple[str, ...] = ()
    missing_access: tuple[str, ...] = ()
    missing_effects: tuple[str, ...] = ()
    unsupported_surfaces: tuple[str, ...] = ()
    unsupported_platforms: tuple[str, ...] = ()
    validation_errors: tuple[str, ...] = ()
    setup_hints: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SkillSyncResult:
    source_id: str | None
    synced_count: int
    packages: tuple[SkillPackage, ...]


@dataclass(frozen=True, slots=True)
class SkillMutationResult:
    skill: SkillPackage
    action: str
    changed: bool
    message: str


class SkillDraftIntent(str, Enum):
    CREATE = "create"
    UPDATE = "update"


class SkillDraftStatus(str, Enum):
    DRAFT = "draft"
    VALIDATED = "validated"
    INVALID = "invalid"
    APPLIED = "applied"
    REJECTED = "rejected"
    EXPIRED = "expired"


@dataclass(frozen=True, slots=True)
class SkillDraftSupportFile:
    path: str
    content: str


@dataclass(frozen=True, slots=True)
class SkillDraftValidation:
    errors: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    missing_tools: tuple[str, ...] = ()
    missing_access: tuple[str, ...] = ()
    missing_effects: tuple[str, ...] = ()
    unsupported_surfaces: tuple[str, ...] = ()
    unsupported_platforms: tuple[str, ...] = ()
    readiness_status: str = "ready"

    @property
    def valid(self) -> bool:
        return not self.errors


@dataclass(frozen=True, slots=True)
class SkillDraftFileDiff:
    path: str
    status: str
    unified_diff: str


@dataclass(frozen=True, slots=True)
class SkillDraftDiff:
    manifest_diff: dict[str, object]
    instructions_diff: str
    file_diffs: tuple[SkillDraftFileDiff, ...] = ()
    summary: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SkillDraft:
    draft_id: str
    status: SkillDraftStatus
    intent: SkillDraftIntent
    skill_name: str
    target_scope: SkillInstallScope = SkillInstallScope.WORKSPACE
    target_source_id: str | None = None
    workspace_dir: str | None = None
    base_fingerprint: str | None = None
    manifest: dict[str, object] | None = None
    instructions_body: str = ""
    support_files: tuple[SkillDraftSupportFile, ...] = ()
    requirements: SkillRequirements = SkillRequirements()
    validation: SkillDraftValidation | None = None
    diff: SkillDraftDiff | None = None
    created_by_run_id: str | None = None
    created_by_turn_id: str | None = None
    actor: str | None = None
    reason: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    expires_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class SkillDraftAuditRecord:
    audit_id: str
    draft_id: str
    action: str
    status: str
    actor: str | None = None
    reason: str | None = None
    created_at: datetime | None = None
    before_payload: dict[str, object] | None = None
    after_payload: dict[str, object] | None = None
    metadata: dict[str, object] | None = None


@dataclass(frozen=True, slots=True)
class SkillDraftCreateRequest:
    intent: SkillDraftIntent
    skill_name: str
    manifest: dict[str, object]
    instructions_body: str
    target_scope: SkillInstallScope = SkillInstallScope.WORKSPACE
    target_source_id: str | None = None
    workspace_dir: str | None = None
    base_fingerprint: str | None = None
    support_files: tuple[SkillDraftSupportFile, ...] = ()
    requirements: SkillRequirements = SkillRequirements()
    created_by_run_id: str | None = None
    created_by_turn_id: str | None = None
    actor: str | None = None
    reason: str | None = None
    expires_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class SkillDraftUpdateRequest:
    manifest: dict[str, object] | None = None
    instructions_body: str | None = None
    support_files: tuple[SkillDraftSupportFile, ...] | None = None
    requirements: SkillRequirements | None = None
    target_source_id: str | None = None
    target_scope: SkillInstallScope | None = None
    workspace_dir: str | None = None
    actor: str | None = None
    reason: str | None = None
    expires_at: datetime | None = None
