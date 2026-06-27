from __future__ import annotations

from pydantic import BaseModel, Field

from crxzipple.modules.skills.application.models import (
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
)
from crxzipple.modules.skills.domain import SkillInstallScope, SkillRequirements


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
    ) -> SkillDraftRequirementsPayload:
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
    ) -> SkillDraftSupportFilePayload:
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
    ) -> SkillDraftValidationResponse:
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
    ) -> SkillDraftFileDiffResponse:
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
    def from_entity(cls, diff: SkillDraftDiff) -> SkillDraftDiffResponse:
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
    def from_entity(cls, draft: SkillDraft) -> SkillDraftResponse:
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
    ) -> SkillDraftAuditResponse:
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
