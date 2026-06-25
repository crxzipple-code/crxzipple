from __future__ import annotations

from pydantic import BaseModel, Field

from crxzipple.modules.skills.application.models import (
    InstalledSkill,
    SkillCreateRequest,
    SkillDraft,
    SkillDraftAuditRecord,
    SkillDraftCreateRequest,
    SkillDraftDiff,
    SkillDraftFileDiff,
    SkillDraftIntent,
    SkillDraftStatus,
    SkillDraftSupportFile,
    SkillDraftUpdateRequest,
    SkillDraftValidation,
    SkillMutationResult,
    SkillPackage,
    SkillReadiness,
    SkillSource,
    SkillSourceCreateRequest,
    SkillSourceKind,
    SkillSourceMutationResult,
    SkillSourceUpdateRequest,
    SkillSyncResult,
    SkillUpdateRequest,
)
from crxzipple.modules.skills.domain import (
    SkillInstallation,
    SkillInstallScope,
    SkillRequirements,
)


class SkillManifestResponse(BaseModel):
    api_version: str
    kind: str
    name: str
    description: str
    version: str | None = None
    tags: list[str] = Field(default_factory=list)
    when_to_use: str | None = None
    anti_patterns: list[str] = Field(default_factory=list)
    instructions_path: str
    required_tools: list[str] = Field(default_factory=list)
    optional_tools: list[str] = Field(default_factory=list)
    suggested_tools: list[str] = Field(default_factory=list)
    required_effects: list[str] = Field(default_factory=list)
    required_access: list[str] = Field(default_factory=list)
    surfaces: list[str] = Field(default_factory=list)
    supported_platforms: list[str] = Field(default_factory=list)
    setup_hints: list[str] = Field(default_factory=list)


class SkillResourceResponse(BaseModel):
    path: str
    kind: str
    size_bytes: int


class SkillRequirementsResponse(BaseModel):
    required_tools: list[str] = Field(default_factory=list)
    optional_tools: list[str] = Field(default_factory=list)
    suggested_tools: list[str] = Field(default_factory=list)
    required_effects: list[str] = Field(default_factory=list)
    surfaces: list[str] = Field(default_factory=list)
    supported_platforms: list[str] = Field(default_factory=list)
    required_access: list[str] = Field(default_factory=list)
    setup_hints: list[str] = Field(default_factory=list)


class SkillReadinessResponse(BaseModel):
    status: str
    ready: bool
    missing_tools: list[str] = Field(default_factory=list)
    missing_access: list[str] = Field(default_factory=list)
    missing_effects: list[str] = Field(default_factory=list)
    unsupported_surfaces: list[str] = Field(default_factory=list)
    unsupported_platforms: list[str] = Field(default_factory=list)
    validation_errors: list[str] = Field(default_factory=list)
    setup_hints: list[str] = Field(default_factory=list)

    @classmethod
    def from_entity(cls, readiness: SkillReadiness) -> "SkillReadinessResponse":
        return cls(
            status=readiness.status.value,
            ready=readiness.ready,
            missing_tools=list(readiness.missing_tools),
            missing_access=list(readiness.missing_access),
            missing_effects=list(readiness.missing_effects),
            unsupported_surfaces=list(readiness.unsupported_surfaces),
            unsupported_platforms=list(readiness.unsupported_platforms),
            validation_errors=list(readiness.validation_errors),
            setup_hints=list(readiness.setup_hints),
        )


class SkillDraftRequirementsPayload(BaseModel):
    required_tools: list[str] = Field(default_factory=list)
    optional_tools: list[str] = Field(default_factory=list)
    suggested_tools: list[str] = Field(default_factory=list)
    required_effects: list[str] = Field(default_factory=list)
    surfaces: list[str] = Field(default_factory=list)
    supported_platforms: list[str] = Field(default_factory=list)
    required_access: list[str] = Field(default_factory=list)
    setup_hints: list[str] = Field(default_factory=list)

    def to_entity(self) -> SkillRequirements:
        return SkillRequirements(
            required_tools=tuple(self.required_tools),
            optional_tools=tuple(self.optional_tools),
            suggested_tools=tuple(self.suggested_tools),
            required_effects=tuple(self.required_effects),
            surfaces=tuple(self.surfaces),
            supported_platforms=tuple(self.supported_platforms),
            required_access=tuple(self.required_access),
            setup_hints=tuple(self.setup_hints),
        )

    @classmethod
    def from_entity(
        cls,
        requirements: SkillRequirements,
    ) -> "SkillDraftRequirementsPayload":
        return cls(
            required_tools=list(requirements.required_tools),
            optional_tools=list(requirements.optional_tools),
            suggested_tools=list(requirements.suggested_tools),
            required_effects=list(requirements.required_effects),
            surfaces=list(requirements.surfaces),
            supported_platforms=list(requirements.supported_platforms),
            required_access=list(requirements.required_access),
            setup_hints=list(requirements.setup_hints),
        )


class SkillDraftSupportFilePayload(BaseModel):
    path: str = Field(min_length=1)
    content: str = Field(default="")

    def to_entity(self) -> SkillDraftSupportFile:
        return SkillDraftSupportFile(path=self.path, content=self.content)

    @classmethod
    def from_entity(
        cls,
        item: SkillDraftSupportFile,
    ) -> "SkillDraftSupportFilePayload":
        return cls(path=item.path, content=item.content)


class CreateSkillDraftRequest(BaseModel):
    intent: SkillDraftIntent
    skill_name: str = Field(min_length=1)
    manifest: dict[str, object] = Field(default_factory=dict)
    instructions_body: str = Field(default="")
    target_scope: SkillInstallScope = SkillInstallScope.WORKSPACE
    target_source_id: str | None = None
    workspace_dir: str | None = None
    base_fingerprint: str | None = None
    support_files: list[SkillDraftSupportFilePayload] = Field(default_factory=list)
    requirements: SkillDraftRequirementsPayload = Field(
        default_factory=SkillDraftRequirementsPayload,
    )
    created_by_run_id: str | None = None
    created_by_turn_id: str | None = None
    actor: str | None = None
    reason: str | None = None

    def to_application_request(self) -> SkillDraftCreateRequest:
        return SkillDraftCreateRequest(
            intent=self.intent,
            skill_name=self.skill_name,
            manifest=dict(self.manifest),
            instructions_body=self.instructions_body,
            target_scope=self.target_scope,
            target_source_id=self.target_source_id,
            workspace_dir=self.workspace_dir,
            base_fingerprint=self.base_fingerprint,
            support_files=tuple(item.to_entity() for item in self.support_files),
            requirements=self.requirements.to_entity(),
            created_by_run_id=self.created_by_run_id,
            created_by_turn_id=self.created_by_turn_id,
            actor=self.actor,
            reason=self.reason,
        )


class UpdateSkillDraftRequest(BaseModel):
    manifest: dict[str, object] | None = None
    instructions_body: str | None = None
    support_files: list[SkillDraftSupportFilePayload] | None = None
    requirements: SkillDraftRequirementsPayload | None = None
    target_scope: SkillInstallScope | None = None
    target_source_id: str | None = None
    workspace_dir: str | None = None
    actor: str | None = None
    reason: str | None = None

    def to_application_request(self) -> SkillDraftUpdateRequest:
        return SkillDraftUpdateRequest(
            manifest=dict(self.manifest) if self.manifest is not None else None,
            instructions_body=self.instructions_body,
            support_files=(
                tuple(item.to_entity() for item in self.support_files)
                if self.support_files is not None
                else None
            ),
            requirements=(
                self.requirements.to_entity()
                if self.requirements is not None
                else None
            ),
            target_scope=self.target_scope,
            target_source_id=self.target_source_id,
            workspace_dir=self.workspace_dir,
            actor=self.actor,
            reason=self.reason,
        )


class SkillDraftValidationResponse(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    missing_tools: list[str] = Field(default_factory=list)
    missing_access: list[str] = Field(default_factory=list)
    missing_effects: list[str] = Field(default_factory=list)
    unsupported_surfaces: list[str] = Field(default_factory=list)
    unsupported_platforms: list[str] = Field(default_factory=list)
    readiness_status: str

    @classmethod
    def from_entity(
        cls,
        validation: SkillDraftValidation,
    ) -> "SkillDraftValidationResponse":
        return cls(
            valid=validation.valid,
            errors=list(validation.errors),
            warnings=list(validation.warnings),
            missing_tools=list(validation.missing_tools),
            missing_access=list(validation.missing_access),
            missing_effects=list(validation.missing_effects),
            unsupported_surfaces=list(validation.unsupported_surfaces),
            unsupported_platforms=list(validation.unsupported_platforms),
            readiness_status=validation.readiness_status,
        )


class SkillDraftFileDiffResponse(BaseModel):
    path: str
    status: str
    unified_diff: str

    @classmethod
    def from_entity(
        cls,
        diff: SkillDraftFileDiff,
    ) -> "SkillDraftFileDiffResponse":
        return cls(
            path=diff.path,
            status=diff.status,
            unified_diff=diff.unified_diff,
        )


class SkillDraftDiffResponse(BaseModel):
    manifest_diff: dict[str, object] = Field(default_factory=dict)
    instructions_diff: str
    file_diffs: list[SkillDraftFileDiffResponse] = Field(default_factory=list)
    summary: list[str] = Field(default_factory=list)

    @classmethod
    def from_entity(cls, diff: SkillDraftDiff) -> "SkillDraftDiffResponse":
        return cls(
            manifest_diff=dict(diff.manifest_diff),
            instructions_diff=diff.instructions_diff,
            file_diffs=[
                SkillDraftFileDiffResponse.from_entity(item)
                for item in diff.file_diffs
            ],
            summary=list(diff.summary),
        )


class SkillDraftResponse(BaseModel):
    draft_id: str
    status: SkillDraftStatus
    intent: SkillDraftIntent
    skill_name: str
    target_source_id: str | None = None
    target_scope: SkillInstallScope
    workspace_dir: str | None = None
    base_fingerprint: str | None = None
    manifest: dict[str, object] = Field(default_factory=dict)
    instructions_body: str
    support_files: list[SkillDraftSupportFilePayload] = Field(default_factory=list)
    requirements: SkillDraftRequirementsPayload
    validation: SkillDraftValidationResponse | None = None
    diff: SkillDraftDiffResponse | None = None
    created_by_run_id: str | None = None
    created_by_turn_id: str | None = None
    actor: str | None = None
    reason: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    expires_at: str | None = None

    @classmethod
    def from_entity(cls, draft: SkillDraft) -> "SkillDraftResponse":
        return cls(
            draft_id=draft.draft_id,
            status=draft.status,
            intent=draft.intent,
            skill_name=draft.skill_name,
            target_source_id=draft.target_source_id,
            target_scope=draft.target_scope,
            workspace_dir=draft.workspace_dir,
            base_fingerprint=draft.base_fingerprint,
            manifest=dict(draft.manifest or {}),
            instructions_body=draft.instructions_body,
            support_files=[
                SkillDraftSupportFilePayload.from_entity(item)
                for item in draft.support_files
            ],
            requirements=SkillDraftRequirementsPayload.from_entity(
                draft.requirements,
            ),
            validation=(
                SkillDraftValidationResponse.from_entity(draft.validation)
                if draft.validation is not None
                else None
            ),
            diff=(
                SkillDraftDiffResponse.from_entity(draft.diff)
                if draft.diff is not None
                else None
            ),
            created_by_run_id=draft.created_by_run_id,
            created_by_turn_id=draft.created_by_turn_id,
            actor=draft.actor,
            reason=draft.reason,
            created_at=(
                draft.created_at.isoformat()
                if draft.created_at is not None
                else None
            ),
            updated_at=(
                draft.updated_at.isoformat()
                if draft.updated_at is not None
                else None
            ),
            expires_at=(
                draft.expires_at.isoformat()
                if draft.expires_at is not None
                else None
            ),
        )


class SkillDraftActionRequest(BaseModel):
    reason: str | None = None


class SkillDraftAuditResponse(BaseModel):
    audit_id: str
    draft_id: str
    action: str
    status: str
    actor: str | None = None
    reason: str | None = None
    before_payload: dict[str, object] = Field(default_factory=dict)
    after_payload: dict[str, object] = Field(default_factory=dict)
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: str | None = None

    @classmethod
    def from_entity(
        cls,
        record: SkillDraftAuditRecord,
    ) -> "SkillDraftAuditResponse":
        return cls(
            audit_id=record.audit_id,
            draft_id=record.draft_id,
            action=record.action,
            status=record.status,
            actor=record.actor,
            reason=record.reason,
            before_payload=dict(record.before_payload or {}),
            after_payload=dict(record.after_payload or {}),
            metadata=dict(record.metadata or {}),
            created_at=(
                record.created_at.isoformat()
                if record.created_at is not None
                else None
            ),
        )


class SkillResponse(BaseModel):
    name: str
    description: str
    version: str | None = None
    tags: list[str] = Field(default_factory=list)
    source: str
    root_path: str
    manifest_path: str
    instructions_path: str
    resources: list[SkillResourceResponse] = Field(default_factory=list)
    requirements: SkillRequirementsResponse
    manifest: SkillManifestResponse
    enabled: bool = True
    readiness: SkillReadinessResponse | None = None

    @classmethod
    def from_entity(
        cls,
        package: SkillPackage,
        *,
        enabled: bool = True,
        readiness: SkillReadiness | None = None,
    ) -> "SkillResponse":
        requirements = package.requirements
        return cls(
            name=package.name,
            description=package.description,
            version=package.version,
            tags=list(package.tags),
            source=package.source,
            root_path=package.root_path,
            manifest_path=package.manifest_path,
            instructions_path=package.instructions_path,
            resources=[
                SkillResourceResponse(
                    path=resource.path,
                    kind=resource.kind,
                    size_bytes=resource.size_bytes,
                )
                for resource in package.resources
            ],
            requirements=SkillRequirementsResponse(
                required_tools=list(requirements.required_tools),
                optional_tools=list(requirements.optional_tools),
                suggested_tools=list(requirements.suggested_tools),
                required_effects=list(requirements.required_effects),
                surfaces=list(requirements.surfaces),
                supported_platforms=list(requirements.supported_platforms),
                required_access=list(requirements.required_access),
                setup_hints=list(requirements.setup_hints),
            ),
            manifest=SkillManifestResponse(
                api_version=package.manifest.api_version,
                kind=package.manifest.kind,
                name=package.manifest.name,
                description=package.manifest.description,
                version=package.manifest.version,
                tags=list(package.manifest.tags),
                when_to_use=package.manifest.when_to_use,
                anti_patterns=list(package.manifest.anti_patterns),
                instructions_path=package.manifest.instructions_path,
                required_tools=list(package.manifest.required_tools),
                optional_tools=list(package.manifest.optional_tools),
                suggested_tools=list(package.manifest.suggested_tools),
                required_effects=list(package.manifest.required_effects),
                required_access=list(package.manifest.required_access),
                surfaces=list(package.manifest.surfaces),
                supported_platforms=list(package.manifest.supported_platforms),
                setup_hints=list(package.manifest.setup_hints),
            ),
            enabled=enabled,
            readiness=(
                SkillReadinessResponse.from_entity(readiness)
                if readiness is not None
                else None
            ),
        )


class SkillDetailResponse(SkillResponse):
    instructions: str | None = None


class ValidateSkillRequest(BaseModel):
    path: str = Field(min_length=1)


class InstallSkillRequest(BaseModel):
    source_dir: str = Field(min_length=1)
    scope: SkillInstallScope = SkillInstallScope.WORKSPACE
    workspace_dir: str | None = None


class SkillWriteRequest(BaseModel):
    content: str = Field(default="")
    workspace_dir: str | None = None


class CreateSkillRequest(BaseModel):
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    instructions: str = Field(min_length=1)
    scope: SkillInstallScope = SkillInstallScope.WORKSPACE
    workspace_dir: str | None = None
    version: str | None = None
    tags: list[str] = Field(default_factory=list)
    required_tools: list[str] = Field(default_factory=list)
    optional_tools: list[str] = Field(default_factory=list)
    suggested_tools: list[str] = Field(default_factory=list)
    required_effects: list[str] = Field(default_factory=list)
    required_access: list[str] = Field(default_factory=list)
    surfaces: list[str] = Field(default_factory=list)
    supported_platforms: list[str] = Field(default_factory=list)
    setup_hints: list[str] = Field(default_factory=list)

    def to_application_request(self) -> SkillCreateRequest:
        return SkillCreateRequest(
            name=self.name,
            description=self.description,
            instructions=self.instructions,
            scope=self.scope,
            workspace_dir=self.workspace_dir,
            version=self.version,
            tags=tuple(self.tags),
            required_tools=tuple(self.required_tools),
            optional_tools=tuple(self.optional_tools),
            suggested_tools=tuple(self.suggested_tools),
            required_effects=tuple(self.required_effects),
            required_access=tuple(self.required_access),
            surfaces=tuple(self.surfaces),
            supported_platforms=tuple(self.supported_platforms),
            setup_hints=tuple(self.setup_hints),
        )


class UpdateSkillRequest(BaseModel):
    workspace_dir: str | None = None
    description: str | None = None
    version: str | None = None
    tags: list[str] | None = None
    required_tools: list[str] | None = None
    optional_tools: list[str] | None = None
    suggested_tools: list[str] | None = None
    required_effects: list[str] | None = None
    required_access: list[str] | None = None
    surfaces: list[str] | None = None
    supported_platforms: list[str] | None = None
    setup_hints: list[str] | None = None

    def to_application_request(self, skill_name: str) -> SkillUpdateRequest:
        return SkillUpdateRequest(
            skill_name=skill_name,
            workspace_dir=self.workspace_dir,
            description=self.description,
            version=self.version,
            tags=_optional_tuple(self.tags),
            required_tools=_optional_tuple(self.required_tools),
            optional_tools=_optional_tuple(self.optional_tools),
            suggested_tools=_optional_tuple(self.suggested_tools),
            required_effects=_optional_tuple(self.required_effects),
            required_access=_optional_tuple(self.required_access),
            surfaces=_optional_tuple(self.surfaces),
            supported_platforms=_optional_tuple(self.supported_platforms),
            setup_hints=_optional_tuple(self.setup_hints),
        )


class SkillInstallResponse(BaseModel):
    scope: str
    target_root: str
    target_path: str
    skill: SkillResponse

    @classmethod
    def from_entity(cls, result: InstalledSkill) -> "SkillInstallResponse":
        return cls(
            scope=result.scope.value,
            target_root=result.target_root,
            target_path=result.target_path,
            skill=SkillResponse.from_entity(result.package),
        )


class SkillSourceResponse(BaseModel):
    source_id: str
    source_kind: str
    root_path: str
    enabled: bool
    readonly: bool
    package_count: int
    metadata: dict[str, object] = Field(default_factory=dict)
    status: str = "active"
    sync_status: str = "never_synced"
    priority: int = 100

    @classmethod
    def from_entity(cls, source: SkillSource) -> "SkillSourceResponse":
        return cls(
            source_id=source.source_id,
            source_kind=source.source_kind.value,
            root_path=source.root_path,
            enabled=source.enabled,
            readonly=source.readonly,
            package_count=source.package_count,
            metadata=source.metadata,
            status=source.status,
            sync_status=source.sync_status,
            priority=source.priority,
        )


class CreateSkillSourceRequest(BaseModel):
    source_id: str = Field(min_length=1)
    root_path: str = Field(min_length=1)
    source_kind: SkillSourceKind = SkillSourceKind.EXTERNAL
    enabled: bool = True
    readonly: bool = False
    priority: int = 100
    metadata: dict[str, object] = Field(default_factory=dict)

    def to_application_request(self) -> SkillSourceCreateRequest:
        return SkillSourceCreateRequest(
            source_id=self.source_id,
            root_path=self.root_path,
            source_kind=self.source_kind,
            enabled=self.enabled,
            readonly=self.readonly,
            priority=self.priority,
            metadata=dict(self.metadata),
        )


class UpdateSkillSourceRequest(BaseModel):
    root_path: str | None = None
    enabled: bool | None = None
    readonly: bool | None = None
    priority: int | None = None
    metadata: dict[str, object] | None = None

    def to_application_request(self, source_id: str) -> SkillSourceUpdateRequest:
        return SkillSourceUpdateRequest(
            source_id=source_id,
            root_path=self.root_path,
            enabled=self.enabled,
            readonly=self.readonly,
            priority=self.priority,
            metadata=dict(self.metadata) if self.metadata is not None else None,
        )


class SkillSourceMutationResponse(BaseModel):
    action: str
    changed: bool
    message: str
    source: SkillSourceResponse

    @classmethod
    def from_entity(
        cls,
        result: SkillSourceMutationResult,
    ) -> "SkillSourceMutationResponse":
        return cls(
            action=result.action,
            changed=result.changed,
            message=result.message,
            source=SkillSourceResponse.from_entity(result.source),
        )


class SkillInstallationResponse(BaseModel):
    installation_id: str
    action: str
    status: str
    source_id: str | None = None
    skill_id: str | None = None
    skill_name: str | None = None
    source_uri: str | None = None
    target_uri: str | None = None
    actor_id: str | None = None
    reason: str | None = None
    message: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: str | None = None

    @classmethod
    def from_entity(
        cls,
        installation: SkillInstallation,
    ) -> "SkillInstallationResponse":
        status_value = getattr(installation.status, "value", installation.status)
        return cls(
            installation_id=installation.installation_id,
            action=installation.action,
            status=str(status_value),
            source_id=installation.source_id,
            skill_id=installation.skill_id,
            skill_name=installation.skill_name,
            source_uri=installation.source_uri,
            target_uri=installation.target_uri,
            actor_id=installation.actor_id,
            reason=installation.reason,
            message=installation.message,
            metadata=dict(installation.metadata),
            created_at=installation.created_at.isoformat()
            if installation.created_at is not None
            else None,
        )


class SkillSyncRequest(BaseModel):
    workspace_dir: str | None = None
    source_id: str | None = None
    surface: str = "interactive"


class SkillSyncResponse(BaseModel):
    source_id: str | None = None
    synced_count: int
    skills: list[SkillResponse] = Field(default_factory=list)

    @classmethod
    def from_entity(cls, result: SkillSyncResult) -> "SkillSyncResponse":
        return cls(
            source_id=result.source_id,
            synced_count=result.synced_count,
            skills=[SkillResponse.from_entity(package) for package in result.packages],
        )


class SkillEnablementRequest(BaseModel):
    workspace_dir: str | None = None
    surface: str = "interactive"
    reason: str | None = None


class SkillMutationResponse(BaseModel):
    action: str
    changed: bool
    message: str
    skill: SkillResponse

    @classmethod
    def from_entity(cls, result: SkillMutationResult) -> "SkillMutationResponse":
        return cls(
            action=result.action,
            changed=result.changed,
            message=result.message,
            skill=SkillResponse.from_entity(
                result.skill,
                enabled=result.action != "disable",
            ),
        )


class SkillReadinessMapResponse(BaseModel):
    skills: dict[str, SkillReadinessResponse]

    @classmethod
    def from_entities(
        cls,
        readiness: dict[str, SkillReadiness],
    ) -> "SkillReadinessMapResponse":
        return cls(
            skills={
                name: SkillReadinessResponse.from_entity(item)
                for name, item in readiness.items()
            },
        )


def _optional_tuple(value: list[str] | None) -> tuple[str, ...] | None:
    if value is None:
        return None
    return tuple(value)
