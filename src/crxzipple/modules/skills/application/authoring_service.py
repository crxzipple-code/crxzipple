from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import timedelta
from uuid import uuid4

from crxzipple.modules.skills.application.authoring_apply import (
    applied_draft,
    apply_validation_error_message,
    assert_apply_target,
    ensure_mutable,
    invalid_draft_for_apply,
)
from crxzipple.modules.skills.application.authoring_diff import build_draft_diff
from crxzipple.modules.skills.application.events import (
    SKILL_DRAFT_APPLIED_EVENT,
    SKILL_DRAFT_APPLY_FAILED_EVENT,
    SKILL_DRAFT_CREATED_EVENT,
    SKILL_DRAFT_DELETED_EVENT,
    SKILL_DRAFT_DIFF_BUILT_EVENT,
    SKILL_DRAFT_REJECTED_EVENT,
    SKILL_DRAFT_UPDATED_EVENT,
    SKILL_DRAFT_VALIDATED_EVENT,
    SkillEventEmitter,
)
from crxzipple.modules.skills.application.exceptions import (
    SkillCapabilityUnavailableError,
)
from crxzipple.modules.skills.application.authoring_conversions import (
    merged_requirements,
    resolve_draft_skill_name,
)
from crxzipple.modules.skills.application.authoring_owner_state import (
    apply_draft_to_owner,
    current_fingerprint,
    current_instructions,
    current_package,
    current_support_file,
)
from crxzipple.modules.skills.application.authoring_readiness import (
    draft_requirement_readiness,
)
from crxzipple.modules.skills.application.authoring_observation import (
    emit_draft_lifecycle_event,
    record_draft_audit,
    utc_now,
)
from crxzipple.modules.skills.application.authoring_validation import (
    draft_validation,
)
from crxzipple.modules.skills.application.models import (
    SkillDraft,
    SkillDraftAuditRecord,
    SkillDraftCreateRequest,
    SkillDraftDiff,
    SkillDraftIntent,
    SkillDraftStatus,
    SkillDraftUpdateRequest,
    SkillDraftValidation,
)
from crxzipple.modules.skills.application.package_service import SkillPackageService
from crxzipple.modules.skills.application.ports import (
    SkillAuthoringDraftRepositoryPort,
)
from crxzipple.modules.skills.application.runtime_request_resolver import (
    SkillRuntimeRequestResolver,
    SkillToolReadinessPort,
)
from crxzipple.modules.skills.domain import (
    SkillNotFoundError,
    SkillValidationError,
)


_DEFAULT_DRAFT_TTL_DAYS = 30


@dataclass(slots=True)
class SkillAuthoringService:
    draft_repository: SkillAuthoringDraftRepositoryPort | None
    package_service: SkillPackageService
    runtime_request_resolver: SkillRuntimeRequestResolver = field(default_factory=SkillRuntimeRequestResolver)
    tool_readiness_port: SkillToolReadinessPort | None = None
    event_emitter: SkillEventEmitter | None = None

    def create_draft(self, request: SkillDraftCreateRequest) -> SkillDraft:
        repository = self._repository()
        now = utc_now()
        skill_name = resolve_draft_skill_name(request.skill_name, request.manifest)
        base_fingerprint = request.base_fingerprint or current_fingerprint(
            self.package_service,
            workspace_dir=request.workspace_dir,
            skill_name=skill_name,
        )
        draft = SkillDraft(
            draft_id=f"skill-draft:{uuid4().hex}",
            status=SkillDraftStatus.DRAFT,
            intent=request.intent,
            skill_name=skill_name,
            target_source_id=request.target_source_id,
            target_scope=request.target_scope,
            workspace_dir=request.workspace_dir,
            base_fingerprint=base_fingerprint,
            manifest=dict(request.manifest),
            instructions_body=request.instructions_body,
            support_files=request.support_files,
            requirements=merged_requirements(request.manifest, request.requirements),
            validation=None,
            diff=None,
            created_by_run_id=request.created_by_run_id,
            created_by_turn_id=request.created_by_turn_id,
            actor=request.actor,
            reason=request.reason,
            created_at=now,
            updated_at=now,
            expires_at=request.expires_at or now + timedelta(days=_DEFAULT_DRAFT_TTL_DAYS),
        )
        saved = repository.save_draft(draft)
        record_draft_audit(
            repository,
            action="create",
            status="succeeded",
            after=saved,
        )
        emit_draft_lifecycle_event(
            self.event_emitter,
            SKILL_DRAFT_CREATED_EVENT,
            saved,
        )
        return saved

    def update_draft(
        self,
        *,
        draft_id: str,
        request: SkillDraftUpdateRequest,
    ) -> SkillDraft:
        draft = self.get_draft(draft_id)
        ensure_mutable(draft)
        manifest = dict(request.manifest) if request.manifest is not None else draft.manifest
        requirements = (
            merged_requirements(manifest or {}, request.requirements)
            if request.requirements is not None or request.manifest is not None
            else draft.requirements
        )
        updated = replace(
            draft,
            status=SkillDraftStatus.DRAFT,
            manifest=manifest,
            instructions_body=(
                request.instructions_body
                if request.instructions_body is not None
                else draft.instructions_body
            ),
            support_files=(
                request.support_files
                if request.support_files is not None
                else draft.support_files
            ),
            requirements=requirements,
            target_source_id=(
                request.target_source_id
                if request.target_source_id is not None
                else draft.target_source_id
            ),
            target_scope=(
                request.target_scope
                if request.target_scope is not None
                else draft.target_scope
            ),
            workspace_dir=(
                request.workspace_dir
                if request.workspace_dir is not None
                else draft.workspace_dir
            ),
            actor=request.actor if request.actor is not None else draft.actor,
            reason=request.reason if request.reason is not None else draft.reason,
            validation=None,
            diff=None,
            updated_at=utc_now(),
            expires_at=(
                request.expires_at
                if request.expires_at is not None
                else draft.expires_at
            ),
        )
        saved = self._repository().save_draft(updated)
        record_draft_audit(
            self._repository(),
            action="update",
            status="succeeded",
            before=draft,
            after=saved,
        )
        emit_draft_lifecycle_event(
            self.event_emitter,
            SKILL_DRAFT_UPDATED_EVENT,
            saved,
        )
        return saved

    def list_drafts(
        self,
        *,
        status: str | None = None,
        skill_name: str | None = None,
        run_id: str | None = None,
        workspace_dir: str | None = None,
        limit: int = 100,
    ) -> tuple[SkillDraft, ...]:
        return self._repository().list_drafts(
            status=status,
            skill_name=skill_name,
            run_id=run_id,
            workspace_dir=workspace_dir,
            limit=limit,
        )

    def get_draft(self, draft_id: str) -> SkillDraft:
        draft = self._repository().get_draft(draft_id)
        if draft is None:
            raise SkillNotFoundError(f"Skill draft '{draft_id}' was not found.")
        return draft

    def list_draft_audit(
        self,
        *,
        draft_id: str,
        limit: int = 100,
    ) -> tuple[SkillDraftAuditRecord, ...]:
        return self._repository().list_draft_audit(
            draft_id=draft_id,
            limit=limit,
        )

    def delete_draft(self, draft_id: str) -> SkillDraft:
        draft = self.get_draft(draft_id)
        deleted = self._repository().delete_draft(draft_id)
        if not deleted:
            raise SkillNotFoundError(f"Skill draft '{draft_id}' was not found.")
        record_draft_audit(
            self._repository(),
            action="delete",
            status="succeeded",
            before=draft,
            draft_id=draft_id,
        )
        emit_draft_lifecycle_event(
            self.event_emitter,
            SKILL_DRAFT_DELETED_EVENT,
            draft,
        )
        return draft

    def reject_draft(self, *, draft_id: str, reason: str | None = None) -> SkillDraft:
        draft = self.get_draft(draft_id)
        ensure_mutable(draft)
        rejected = self._repository().save_draft(
            replace(
                draft,
                status=SkillDraftStatus.REJECTED,
                reason=reason or draft.reason,
                updated_at=utc_now(),
            ),
        )
        record_draft_audit(
            self._repository(),
            action="reject",
            status="succeeded",
            before=draft,
            after=rejected,
        )
        emit_draft_lifecycle_event(
            self.event_emitter,
            SKILL_DRAFT_REJECTED_EVENT,
            rejected,
        )
        return rejected

    def validate_draft(self, draft_id: str) -> SkillDraft:
        draft = self.get_draft(draft_id)
        validation = self._validate(draft)
        status = (
            SkillDraftStatus.VALIDATED
            if validation.valid
            else SkillDraftStatus.INVALID
        )
        saved = self._repository().save_draft(
            replace(
                draft,
                status=status,
                validation=validation,
                updated_at=utc_now(),
            ),
        )
        record_draft_audit(
            self._repository(),
            action="validate",
            status="succeeded" if validation.valid else "invalid",
            before=draft,
            after=saved,
            metadata={
                "readiness_status": validation.readiness_status,
                "error_count": len(validation.errors),
                "warning_count": len(validation.warnings),
            },
        )
        emit_draft_lifecycle_event(
            self.event_emitter,
            SKILL_DRAFT_VALIDATED_EVENT,
            saved,
            status=validation.readiness_status,
            level="info" if validation.valid else "warning",
        )
        return saved

    def build_diff(self, draft_id: str) -> SkillDraft:
        draft = self.get_draft(draft_id)
        diff = self._diff(draft)
        saved = self._repository().save_draft(
            replace(
                draft,
                diff=diff,
                updated_at=utc_now(),
            ),
        )
        record_draft_audit(
            self._repository(),
            action="diff",
            status="succeeded",
            before=draft,
            after=saved,
            metadata={"summary": list(diff.summary)},
        )
        emit_draft_lifecycle_event(
            self.event_emitter,
            SKILL_DRAFT_DIFF_BUILT_EVENT,
            saved,
        )
        return saved

    def apply_draft(
        self,
        *,
        draft_id: str,
        reason: str | None = None,
    ) -> SkillDraft:
        draft = self.get_draft(draft_id)
        before = draft
        try:
            ensure_mutable(draft)
            validation = draft.validation or self._validate(draft)
            if validation.errors:
                invalid = self._repository().save_draft(
                    invalid_draft_for_apply(
                        draft,
                        validation=validation,
                        updated_at=utc_now(),
                    ),
                )
                draft = invalid
                raise SkillValidationError(apply_validation_error_message(validation))
            assert_apply_target(
                draft,
                current_package=(
                    current_package(
                        self.package_service,
                        workspace_dir=draft.workspace_dir,
                        skill_name=draft.skill_name,
                    )
                    if draft.intent is SkillDraftIntent.UPDATE
                    else None
                ),
            )
            result = apply_draft_to_owner(self.package_service, draft)
            applied = applied_draft(
                draft,
                validation=validation,
                result=result,
                reason=reason,
                updated_at=utc_now(),
            )
        except SkillValidationError as exc:
            record_draft_audit(
                self._repository(),
                action="apply",
                status="failed",
                before=before,
                after=draft,
                metadata={"error_message": str(exc)},
            )
            emit_draft_lifecycle_event(
                self.event_emitter,
                SKILL_DRAFT_APPLY_FAILED_EVENT,
                draft,
                status="failed",
                level="error",
                extra={"error_message": str(exc)},
            )
            raise
        saved = self._repository().save_draft(applied)
        record_draft_audit(
            self._repository(),
            action="apply",
            status="succeeded",
            before=before,
            after=saved,
        )
        emit_draft_lifecycle_event(
            self.event_emitter,
            SKILL_DRAFT_APPLIED_EVENT,
            saved,
        )
        return saved

    def _validate(self, draft: SkillDraft) -> SkillDraftValidation:
        existing = current_package(
            self.package_service,
            workspace_dir=draft.workspace_dir,
            skill_name=draft.skill_name,
        )
        return draft_validation(
            draft,
            existing_package=existing,
            requirement_readiness=draft_requirement_readiness(
                draft,
                runtime_request_resolver=self.runtime_request_resolver,
                tool_readiness_port=self.tool_readiness_port,
            ),
        )

    def _diff(self, draft: SkillDraft) -> SkillDraftDiff:
        current = (
            None
            if draft.intent is SkillDraftIntent.CREATE
            else current_package(
                self.package_service,
                workspace_dir=draft.workspace_dir,
                skill_name=draft.skill_name,
            )
        )
        current_support_files = (
            {
                item.path: current_support_file(
                    self.package_service,
                    draft,
                    item.path,
                )
                for item in draft.support_files
            }
            if current is not None
            else {}
        )
        return build_draft_diff(
            draft,
            current=current,
            current_instructions=(
                current_instructions(self.package_service, draft)
                if current is not None
                else ""
            ),
            current_support_files=current_support_files,
        )

    def _repository(self) -> SkillAuthoringDraftRepositoryPort:
        if self.draft_repository is None:
            raise SkillCapabilityUnavailableError(
                "Skill draft persistence is not available.",
            )
        return self.draft_repository
