from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from difflib import unified_diff
from uuid import uuid4

from crxzipple.modules.skills.application.environment import unsupported_platforms
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
    emit_skill_event,
)
from crxzipple.modules.skills.application.exceptions import (
    SkillCapabilityUnavailableError,
)
from crxzipple.modules.skills.application.models import (
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
    SkillUpdateRequest,
)
from crxzipple.modules.skills.application.package_service import SkillPackageService
from crxzipple.modules.skills.application.ports import (
    SkillAuthoringDraftRepositoryPort,
)
from crxzipple.modules.skills.application.prompt_resolver import (
    ResolvedSkillReadiness,
    SkillPromptResolutionContext,
    SkillPromptResolver,
    SkillToolReadinessPort,
)
from crxzipple.modules.skills.domain import (
    SkillManifest,
    SkillNotFoundError,
    SkillRequirements,
    SkillValidationError,
)


_SUPPORT_FILE_DIRS = ("references", "templates", "assets", "scripts")
_DEFAULT_DRAFT_TTL_DAYS = 30


@dataclass(slots=True)
class SkillAuthoringService:
    draft_repository: SkillAuthoringDraftRepositoryPort | None
    package_service: SkillPackageService
    prompt_resolver: SkillPromptResolver = field(default_factory=SkillPromptResolver)
    tool_readiness_port: SkillToolReadinessPort | None = None
    event_emitter: SkillEventEmitter | None = None

    def create_draft(self, request: SkillDraftCreateRequest) -> SkillDraft:
        repository = self._repository()
        now = _utc_now()
        skill_name = _skill_name(request.skill_name, request.manifest)
        base_fingerprint = request.base_fingerprint or self._current_fingerprint(
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
            requirements=_merged_requirements(request.manifest, request.requirements),
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
        self._record_audit(action="create", status="succeeded", after=saved)
        self._emit_draft_event(SKILL_DRAFT_CREATED_EVENT, saved)
        return saved

    def update_draft(
        self,
        *,
        draft_id: str,
        request: SkillDraftUpdateRequest,
    ) -> SkillDraft:
        draft = self.get_draft(draft_id)
        self._ensure_mutable(draft)
        manifest = dict(request.manifest) if request.manifest is not None else draft.manifest
        requirements = (
            _merged_requirements(manifest or {}, request.requirements)
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
            updated_at=_utc_now(),
            expires_at=(
                request.expires_at
                if request.expires_at is not None
                else draft.expires_at
            ),
        )
        saved = self._repository().save_draft(updated)
        self._record_audit(
            action="update",
            status="succeeded",
            before=draft,
            after=saved,
        )
        self._emit_draft_event(SKILL_DRAFT_UPDATED_EVENT, saved)
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
        self._record_audit(
            action="delete",
            status="succeeded",
            before=draft,
            draft_id=draft_id,
        )
        self._emit_draft_event(SKILL_DRAFT_DELETED_EVENT, draft)
        return draft

    def reject_draft(self, *, draft_id: str, reason: str | None = None) -> SkillDraft:
        draft = self.get_draft(draft_id)
        self._ensure_mutable(draft)
        rejected = self._repository().save_draft(
            replace(
                draft,
                status=SkillDraftStatus.REJECTED,
                reason=reason or draft.reason,
                updated_at=_utc_now(),
            ),
        )
        self._record_audit(
            action="reject",
            status="succeeded",
            before=draft,
            after=rejected,
        )
        self._emit_draft_event(SKILL_DRAFT_REJECTED_EVENT, rejected)
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
                updated_at=_utc_now(),
            ),
        )
        self._record_audit(
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
        self._emit_draft_event(
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
                updated_at=_utc_now(),
            ),
        )
        self._record_audit(
            action="diff",
            status="succeeded",
            before=draft,
            after=saved,
            metadata={"summary": list(diff.summary)},
        )
        self._emit_draft_event(SKILL_DRAFT_DIFF_BUILT_EVENT, saved)
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
            self._ensure_mutable(draft)
            validation = draft.validation or self._validate(draft)
            if validation.errors:
                invalid = self._repository().save_draft(
                    replace(
                        draft,
                        status=SkillDraftStatus.INVALID,
                        validation=validation,
                        updated_at=_utc_now(),
                    ),
                )
                message = "Skill draft is invalid: " + "; ".join(validation.errors)
                draft = invalid
                raise SkillValidationError(message)
            if draft.intent is SkillDraftIntent.UPDATE:
                current = self._current_package(
                    workspace_dir=draft.workspace_dir,
                    skill_name=draft.skill_name,
                )
                if current is None:
                    raise SkillValidationError(
                        f"Skill '{draft.skill_name}' does not exist.",
                    )
                if (
                    draft.base_fingerprint
                    and current.fingerprint
                    and current.fingerprint != draft.base_fingerprint
                ):
                    raise SkillValidationError(
                        "Skill draft target changed after the draft was created. "
                        "Refresh the draft before applying it.",
                    )
            if draft.target_source_id in {"system"}:
                raise SkillValidationError(
                    "System skill source is readonly and cannot receive authored drafts.",
                )
            result = self._apply_to_owner(draft)
            applied = replace(
                draft,
                status=SkillDraftStatus.APPLIED,
                validation=validation,
                base_fingerprint=result.skill.fingerprint or draft.base_fingerprint,
                reason=reason or draft.reason,
                updated_at=_utc_now(),
            )
        except SkillValidationError as exc:
            self._record_audit(
                action="apply",
                status="failed",
                before=before,
                after=draft,
                metadata={"error_message": str(exc)},
            )
            self._emit_draft_event(
                SKILL_DRAFT_APPLY_FAILED_EVENT,
                draft,
                status="failed",
                level="error",
                extra={"error_message": str(exc)},
            )
            raise
        saved = self._repository().save_draft(applied)
        self._record_audit(
            action="apply",
            status="succeeded",
            before=before,
            after=saved,
        )
        self._emit_draft_event(SKILL_DRAFT_APPLIED_EVENT, saved)
        return saved

    def _apply_to_owner(self, draft: SkillDraft) -> SkillMutationResult:
        if draft.intent is SkillDraftIntent.CREATE:
            result = self.package_service.create(_create_request(draft))
        else:
            result = self.package_service.update(_update_request(draft))
            result = self.package_service.write_instructions(
                workspace_dir=draft.workspace_dir,
                skill_name=draft.skill_name,
                content=draft.instructions_body,
            )
        for item in draft.support_files:
            result = self.package_service.write_file(
                workspace_dir=draft.workspace_dir,
                skill_name=draft.skill_name,
                path=item.path,
                content=item.content,
            )
        return result

    def _validate(self, draft: SkillDraft) -> SkillDraftValidation:
        manifest = dict(draft.manifest or {})
        errors: list[str] = []
        warnings: list[str] = []
        skill_name = str(manifest.get("name") or draft.skill_name).strip()
        description = str(manifest.get("description") or "").strip()
        if not skill_name:
            errors.append("skill_name is required")
        if skill_name and skill_name != draft.skill_name:
            errors.append("manifest.name must match skill_name")
        if not description:
            errors.append("manifest.description is required")
        if not draft.instructions_body.strip():
            errors.append("instructions_body is required")
        if draft.target_source_id and draft.target_source_id not in {
            "workspace",
            "global",
            "system",
        }:
            warnings.append(
                "target_source_id is not directly writable by the current package service; target_scope will be used",
            )
        for item in draft.support_files:
            errors.extend(_support_file_errors(item))
        errors.extend(_requirement_errors(draft.requirements))
        if draft.intent is SkillDraftIntent.CREATE:
            existing = self._current_package(
                workspace_dir=draft.workspace_dir,
                skill_name=draft.skill_name,
            )
            if existing is not None:
                errors.append(f"skill '{draft.skill_name}' already exists")
        else:
            existing = self._current_package(
                workspace_dir=draft.workspace_dir,
                skill_name=draft.skill_name,
            )
            if existing is None:
                errors.append(f"skill '{draft.skill_name}' does not exist")
            elif (
                draft.base_fingerprint
                and existing.fingerprint
                and existing.fingerprint != draft.base_fingerprint
            ):
                warnings.append("target skill changed after this draft was created")

        requirement_readiness = self._draft_requirement_readiness(draft)
        unsupported_platform_values = requirement_readiness.unsupported_platforms
        missing_tools = requirement_readiness.missing_tools
        missing_access = requirement_readiness.missing_access
        missing_effects = requirement_readiness.missing_effects
        if errors:
            readiness_status = "invalid"
        else:
            readiness_status = requirement_readiness.status
        return SkillDraftValidation(
            errors=tuple(errors),
            warnings=tuple(warnings),
            missing_tools=missing_tools,
            missing_access=missing_access,
            missing_effects=missing_effects,
            unsupported_surfaces=requirement_readiness.unsupported_surfaces,
            unsupported_platforms=unsupported_platform_values,
            readiness_status=readiness_status,
        )

    def _draft_requirement_readiness(
        self,
        draft: SkillDraft,
    ) -> ResolvedSkillReadiness:
        if self.tool_readiness_port is None:
            unsupported_platform_values = unsupported_platforms(
                draft.requirements.supported_platforms,
            )
            missing_tools = draft.requirements.required_tools
            missing_access = draft.requirements.required_access
            missing_effects = draft.requirements.required_effects
            if unsupported_platform_values:
                status = "unsupported"
            elif missing_tools or missing_access or missing_effects:
                status = "setup_needed"
            else:
                status = "ready"
            return ResolvedSkillReadiness(
                status=status,
                missing_tools=missing_tools,
                missing_access=missing_access,
                missing_effects=missing_effects,
                unsupported_platforms=unsupported_platform_values,
            )
        resolution = self.prompt_resolver.resolve(
            (_draft_package(draft),),
            available_tool_ids=self.tool_readiness_port.list_available_tool_ids(),
            context=SkillPromptResolutionContext(
                workspace_dir=draft.workspace_dir,
            ),
        )
        return resolution.skills[0].readiness

    def _diff(self, draft: SkillDraft) -> SkillDraftDiff:
        current = (
            None
            if draft.intent is SkillDraftIntent.CREATE
            else self._current_package(
                workspace_dir=draft.workspace_dir,
                skill_name=draft.skill_name,
            )
        )
        old_manifest = _manifest_payload(current) if current is not None else {}
        new_manifest = _draft_manifest_payload(draft)
        instructions_diff = _unified(
            old=self._current_instructions(draft) if current is not None else "",
            new=draft.instructions_body,
            fromfile=f"{draft.skill_name}/SKILL.md (current)",
            tofile=f"{draft.skill_name}/SKILL.md (draft)",
        )
        file_diffs = tuple(
            SkillDraftFileDiff(
                path=item.path,
                status="added" if current is None or not self._support_file_exists(draft, item.path) else "modified",
                unified_diff=_unified(
                    old=(
                        self._current_support_file(draft, item.path)
                        if current is not None
                        else ""
                    ),
                    new=item.content,
                    fromfile=f"{draft.skill_name}/{item.path} (current)",
                    tofile=f"{draft.skill_name}/{item.path} (draft)",
                ),
            )
            for item in draft.support_files
        )
        summary = [
            (
                f"Create skill '{draft.skill_name}'"
                if draft.intent is SkillDraftIntent.CREATE
                else f"Update skill '{draft.skill_name}'"
            )
        ]
        if old_manifest != new_manifest:
            summary.append("Manifest metadata changes")
        if instructions_diff:
            summary.append("Instructions changes")
        if file_diffs:
            summary.append(f"{len(file_diffs)} support file changes")
        return SkillDraftDiff(
            manifest_diff={
                "status": "added" if current is None else "modified",
                "old": old_manifest,
                "new": new_manifest,
            },
            instructions_diff=instructions_diff,
            file_diffs=file_diffs,
            summary=tuple(summary),
        )

    def _current_package(
        self,
        *,
        workspace_dir: str | None,
        skill_name: str,
    ) -> SkillPackage | None:
        try:
            return self.package_service.catalog_service.get(
                workspace_dir=workspace_dir,
                skill_name=skill_name,
                surface="",
                include_disabled=True,
            )
        except SkillNotFoundError:
            return None

    def _current_fingerprint(
        self,
        *,
        workspace_dir: str | None,
        skill_name: str,
    ) -> str | None:
        current = self._current_package(
            workspace_dir=workspace_dir,
            skill_name=skill_name,
        )
        return current.fingerprint if current is not None else None

    def _current_instructions(self, draft: SkillDraft) -> str:
        try:
            return self.package_service.read(
                workspace_dir=draft.workspace_dir,
                skill_name=draft.skill_name,
                path=None,
                surface="",
            ).content
        except SkillNotFoundError:
            return ""

    def _current_support_file(self, draft: SkillDraft, path: str) -> str:
        try:
            return self.package_service.read(
                workspace_dir=draft.workspace_dir,
                skill_name=draft.skill_name,
                path=path,
                surface="",
            ).content
        except SkillValidationError:
            return ""
        except SkillNotFoundError:
            return ""

    def _support_file_exists(self, draft: SkillDraft, path: str) -> bool:
        return bool(self._current_support_file(draft, path))

    def _ensure_mutable(self, draft: SkillDraft) -> None:
        if draft.status in {
            SkillDraftStatus.APPLIED,
            SkillDraftStatus.REJECTED,
            SkillDraftStatus.EXPIRED,
        }:
            raise SkillValidationError(
                f"Skill draft '{draft.draft_id}' is {draft.status.value} and cannot be changed.",
            )

    def _repository(self) -> SkillAuthoringDraftRepositoryPort:
        if self.draft_repository is None:
            raise SkillCapabilityUnavailableError(
                "Skill draft persistence is not available.",
            )
        return self.draft_repository

    def _record_audit(
        self,
        *,
        action: str,
        status: str,
        draft_id: str | None = None,
        before: SkillDraft | None = None,
        after: SkillDraft | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        draft = after or before
        resolved_draft_id = draft_id or (draft.draft_id if draft is not None else "")
        if not resolved_draft_id:
            return
        self._repository().append_draft_audit(
            SkillDraftAuditRecord(
                audit_id=f"skill-draft-audit:{uuid4().hex}",
                draft_id=resolved_draft_id,
                action=action,
                status=status,
                actor=(draft.actor if draft is not None else None),
                reason=(draft.reason if draft is not None else None),
                before_payload=_draft_audit_payload(before),
                after_payload=_draft_audit_payload(after),
                metadata=dict(metadata or {}),
                created_at=_utc_now(),
            ),
        )

    def _emit_draft_event(
        self,
        event_name: str,
        draft: SkillDraft,
        *,
        status: str | None = None,
        level: str = "info",
        extra: dict[str, object] | None = None,
    ) -> None:
        emit_skill_event(
            self.event_emitter,
            event_name,
            payload=_draft_event_payload(draft, extra=extra),
            status=status or draft.status.value,
            level=level,
        )


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _skill_name(skill_name: str, manifest: dict[str, object]) -> str:
    value = str(manifest.get("name") or skill_name).strip()
    if not value:
        raise SkillValidationError("skill_name is required")
    return value


def _draft_event_payload(
    draft: SkillDraft,
    *,
    extra: dict[str, object] | None = None,
) -> dict[str, object]:
    validation = draft.validation
    diff = draft.diff
    payload: dict[str, object] = {
        "draft_id": draft.draft_id,
        "draft_status": draft.status.value,
        "intent": draft.intent.value,
        "skill": draft.skill_name,
        "skill_name": draft.skill_name,
        "source": draft.target_source_id or draft.target_scope.value,
        "target_source_id": draft.target_source_id or "",
        "target_scope": draft.target_scope.value,
        "workspace_dir": draft.workspace_dir or "",
        "actor": draft.actor or "",
        "reason": draft.reason or "",
        "run_id": draft.created_by_run_id or "",
        "created_by_run_id": draft.created_by_run_id or "",
        "created_by_turn_id": draft.created_by_turn_id or "",
        "base_fingerprint": draft.base_fingerprint or "",
        "required_tools": list(draft.requirements.required_tools),
        "required_access": list(draft.requirements.required_access),
        "required_effects": list(draft.requirements.required_effects),
    }
    if validation is not None:
        payload.update(
            {
                "readiness_status": validation.readiness_status,
                "validation_error_count": len(validation.errors),
                "validation_warning_count": len(validation.warnings),
                "validation_errors": list(validation.errors),
                "validation_warnings": list(validation.warnings),
                "missing_tools": list(validation.missing_tools),
                "missing_access": list(validation.missing_access),
                "missing_effects": list(validation.missing_effects),
                "unsupported_surfaces": list(validation.unsupported_surfaces),
                "unsupported_platforms": list(validation.unsupported_platforms),
            },
        )
    if diff is not None:
        payload["diff_summary"] = list(diff.summary)
    if extra:
        payload.update(extra)
    return payload


def _draft_audit_payload(draft: SkillDraft | None) -> dict[str, object]:
    if draft is None:
        return {}
    validation = draft.validation
    diff = draft.diff
    payload: dict[str, object] = {
        "draft_id": draft.draft_id,
        "status": draft.status.value,
        "intent": draft.intent.value,
        "skill_name": draft.skill_name,
        "target_source_id": draft.target_source_id,
        "target_scope": draft.target_scope.value,
        "workspace_dir": draft.workspace_dir,
        "base_fingerprint": draft.base_fingerprint,
        "support_file_paths": [item.path for item in draft.support_files],
        "requirements": draft.requirements.to_payload(),
        "actor": draft.actor,
        "reason": draft.reason,
        "created_by_run_id": draft.created_by_run_id,
        "created_by_turn_id": draft.created_by_turn_id,
        "created_at": draft.created_at.isoformat() if draft.created_at else None,
        "updated_at": draft.updated_at.isoformat() if draft.updated_at else None,
        "expires_at": draft.expires_at.isoformat() if draft.expires_at else None,
    }
    if validation is not None:
        payload["validation"] = {
            "valid": validation.valid,
            "readiness_status": validation.readiness_status,
            "error_count": len(validation.errors),
            "warning_count": len(validation.warnings),
            "missing_tools": list(validation.missing_tools),
            "missing_access": list(validation.missing_access),
            "missing_effects": list(validation.missing_effects),
        }
    if diff is not None:
        payload["diff"] = {
            "summary": list(diff.summary),
            "file_count": len(diff.file_diffs),
        }
    return payload


def _create_request(draft: SkillDraft) -> SkillCreateRequest:
    manifest = dict(draft.manifest or {})
    return SkillCreateRequest(
        name=draft.skill_name,
        description=str(manifest.get("description") or ""),
        instructions=draft.instructions_body,
        scope=draft.target_scope,
        workspace_dir=draft.workspace_dir,
        version=_optional_text(manifest.get("version")),
        tags=_text_tuple(manifest.get("tags")),
        required_tools=draft.requirements.required_tools,
        optional_tools=draft.requirements.optional_tools,
        suggested_tools=draft.requirements.suggested_tools,
        required_effects=draft.requirements.required_effects,
        required_access=draft.requirements.required_access,
        surfaces=draft.requirements.surfaces,
        supported_platforms=draft.requirements.supported_platforms,
        setup_hints=draft.requirements.setup_hints,
    )


def _update_request(draft: SkillDraft) -> SkillUpdateRequest:
    manifest = dict(draft.manifest or {})
    return SkillUpdateRequest(
        skill_name=draft.skill_name,
        workspace_dir=draft.workspace_dir,
        description=str(manifest.get("description") or ""),
        version=_optional_text(manifest.get("version")),
        tags=_text_tuple(manifest.get("tags")),
        required_tools=draft.requirements.required_tools,
        optional_tools=draft.requirements.optional_tools,
        suggested_tools=draft.requirements.suggested_tools,
        required_effects=draft.requirements.required_effects,
        required_access=draft.requirements.required_access,
        surfaces=draft.requirements.surfaces,
        supported_platforms=draft.requirements.supported_platforms,
        setup_hints=draft.requirements.setup_hints,
    )


def _draft_package(draft: SkillDraft) -> SkillPackage:
    manifest = dict(draft.manifest or {})
    skill_manifest = SkillManifest(
        api_version=str(
            manifest.get("apiVersion")
            or manifest.get("api_version")
            or "skills.crxzipple/v1alpha1",
        ),
        kind=str(manifest.get("kind") or "Skill"),
        name=draft.skill_name,
        description=str(manifest.get("description") or ""),
        version=_optional_text(manifest.get("version")),
        tags=_text_tuple(manifest.get("tags")),
        when_to_use=_optional_text(manifest.get("when_to_use")),
        anti_patterns=_text_tuple(manifest.get("anti_patterns")),
        instructions_path=str(manifest.get("instructions_path") or "SKILL.md"),
        required_tools=draft.requirements.required_tools,
        optional_tools=draft.requirements.optional_tools,
        suggested_tools=draft.requirements.suggested_tools,
        required_effects=draft.requirements.required_effects,
        required_access=draft.requirements.required_access,
        surfaces=draft.requirements.surfaces,
        supported_platforms=draft.requirements.supported_platforms,
        setup_hints=draft.requirements.setup_hints,
    )
    return SkillPackage(
        manifest=skill_manifest,
        root_path=f"draft://{draft.draft_id}",
        manifest_path=f"draft://{draft.draft_id}/manifest",
        instructions_path=f"draft://{draft.draft_id}/SKILL.md",
        source=draft.target_source_id or draft.target_scope.value,
        resources=(),
        fingerprint=draft.base_fingerprint or "",
    )


def _draft_manifest_payload(draft: SkillDraft) -> dict[str, object]:
    manifest = dict(draft.manifest or {})
    manifest["name"] = draft.skill_name
    requirements = draft.requirements.to_payload()
    for key, value in requirements.items():
        if value:
            manifest[key] = value
    return manifest


def _manifest_payload(package: SkillPackage) -> dict[str, object]:
    manifest = package.manifest
    payload: dict[str, object] = {
        "apiVersion": manifest.api_version,
        "kind": manifest.kind,
        "name": manifest.name,
        "description": manifest.description,
        "instructions_path": manifest.instructions_path,
    }
    for key, value in (
        ("version", manifest.version),
        ("tags", list(manifest.tags)),
        ("when_to_use", manifest.when_to_use),
        ("anti_patterns", list(manifest.anti_patterns)),
        ("required_tools", list(manifest.required_tools)),
        ("optional_tools", list(manifest.optional_tools)),
        ("suggested_tools", list(manifest.suggested_tools)),
        ("required_effects", list(manifest.required_effects)),
        ("required_access", list(manifest.required_access)),
        ("surfaces", list(manifest.surfaces)),
        ("supported_platforms", list(manifest.supported_platforms)),
        ("setup_hints", list(manifest.setup_hints)),
    ):
        if value:
            payload[key] = value
    return payload


def _merged_requirements(
    manifest: dict[str, object],
    requirements: SkillRequirements,
) -> SkillRequirements:
    manifest_requirements = SkillRequirements(
        required_tools=_text_tuple(manifest.get("required_tools")),
        optional_tools=_text_tuple(manifest.get("optional_tools")),
        suggested_tools=(
            _text_tuple(manifest.get("suggested_tools"))
            or _text_tuple(manifest.get("allowed_tools"))
        ),
        required_effects=_text_tuple(manifest.get("required_effects")),
        surfaces=_text_tuple(manifest.get("surfaces")),
        supported_platforms=_text_tuple(manifest.get("supported_platforms")),
        required_access=_text_tuple(manifest.get("required_access")),
        setup_hints=_text_tuple(manifest.get("setup_hints")),
    )
    return SkillRequirements(
        required_tools=requirements.required_tools or manifest_requirements.required_tools,
        optional_tools=requirements.optional_tools or manifest_requirements.optional_tools,
        suggested_tools=requirements.suggested_tools or manifest_requirements.suggested_tools,
        required_effects=requirements.required_effects or manifest_requirements.required_effects,
        surfaces=requirements.surfaces or manifest_requirements.surfaces,
        supported_platforms=(
            requirements.supported_platforms
            or manifest_requirements.supported_platforms
        ),
        required_access=requirements.required_access or manifest_requirements.required_access,
        setup_hints=requirements.setup_hints or manifest_requirements.setup_hints,
    )


def _support_file_errors(file: SkillDraftSupportFile) -> list[str]:
    normalized = file.path.strip().replace("\\", "/")
    if not normalized:
        return ["support file path is required"]
    if normalized.startswith("/") or normalized in {".", ".."} or ".." in normalized.split("/"):
        return [f"support file '{file.path}' must be package-relative"]
    if normalized == "SKILL.md":
        return ["support files cannot replace SKILL.md"]
    if not any(
        normalized == directory or normalized.startswith(f"{directory}/")
        for directory in _SUPPORT_FILE_DIRS
    ):
        allowed = ", ".join(_SUPPORT_FILE_DIRS)
        return [f"support file '{file.path}' must live under one of: {allowed}"]
    return []


def _requirement_errors(requirements: SkillRequirements) -> list[str]:
    errors: list[str] = []
    for tool_id in requirements.required_tools + requirements.optional_tools + requirements.suggested_tools:
        if tool_id.startswith(("env:", "file:")) or "/" in tool_id or "\\" in tool_id:
            errors.append(
                f"tool requirement '{tool_id}' must reference a ToolFunction id",
            )
    for access_id in requirements.required_access:
        if access_id.startswith(("env:", "file:", "codex_auth_json", "auth_ref")):
            errors.append(
                f"access requirement '{access_id}' must reference Access owner requirements",
            )
    return errors


def _text_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        normalized = value.strip()
        return (normalized,) if normalized else ()
    if not isinstance(value, list | tuple):
        return ()
    items: list[str] = []
    for raw in value:
        if not isinstance(raw, str):
            continue
        normalized = raw.strip()
        if normalized and normalized not in items:
            items.append(normalized)
    return tuple(items)


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _unified(
    *,
    old: str,
    new: str,
    fromfile: str,
    tofile: str,
) -> str:
    if old == new:
        return ""
    return "".join(
        unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=fromfile,
            tofile=tofile,
        ),
    )
