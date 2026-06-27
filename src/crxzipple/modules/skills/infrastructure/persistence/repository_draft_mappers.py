from __future__ import annotations

from crxzipple.modules.skills.application.models import (
    SkillDraft,
    SkillDraftAuditRecord,
    SkillDraftDiff,
    SkillDraftFileDiff,
    SkillDraftIntent,
    SkillDraftStatus,
    SkillDraftSupportFile,
    SkillDraftValidation,
)
from crxzipple.modules.skills.domain import SkillInstallScope
from crxzipple.modules.skills.infrastructure.persistence.models import (
    SkillAuthoringAuditModel,
    SkillAuthoringDraftModel,
)
from crxzipple.modules.skills.infrastructure.persistence.repository_payloads import (
    requirements_from_payload,
    tuple_of_text,
)
from crxzipple.shared.time import coerce_optional_utc_datetime, coerce_utc_datetime


def draft_model(draft: SkillDraft) -> SkillAuthoringDraftModel:
    return SkillAuthoringDraftModel(**draft_mapping(draft))


def draft_mapping(draft: SkillDraft) -> dict[str, object]:
    return {
        "draft_id": draft.draft_id,
        "status": draft.status.value,
        "intent": draft.intent.value,
        "skill_name": draft.skill_name,
        "target_source_id": draft.target_source_id,
        "target_scope": draft.target_scope.value,
        "workspace_dir": draft.workspace_dir,
        "base_fingerprint": draft.base_fingerprint,
        "manifest_payload": dict(draft.manifest or {}),
        "instructions_body": draft.instructions_body,
        "support_files_payload": [
            {"path": item.path, "content": item.content}
            for item in draft.support_files
        ],
        "requirements_payload": draft.requirements.to_payload(),
        "validation_payload": validation_payload(draft.validation),
        "diff_payload": diff_payload(draft.diff),
        "created_by_run_id": draft.created_by_run_id,
        "created_by_turn_id": draft.created_by_turn_id,
        "actor": draft.actor,
        "reason": draft.reason,
        "created_at": draft.created_at,
        "updated_at": draft.updated_at,
        "expires_at": draft.expires_at,
    }


def apply_draft(model: SkillAuthoringDraftModel, draft: SkillDraft) -> None:
    for key, value in draft_mapping(draft).items():
        setattr(model, key, value)


def draft_record(model: SkillAuthoringDraftModel) -> SkillDraft:
    return SkillDraft(
        draft_id=model.draft_id,
        status=SkillDraftStatus(model.status),
        intent=SkillDraftIntent(model.intent),
        skill_name=model.skill_name,
        target_source_id=model.target_source_id,
        target_scope=SkillInstallScope(model.target_scope),
        workspace_dir=model.workspace_dir,
        base_fingerprint=model.base_fingerprint,
        manifest=dict(model.manifest_payload or {}),
        instructions_body=model.instructions_body,
        support_files=support_files_from_payload(model.support_files_payload),
        requirements=requirements_from_payload(model.requirements_payload),
        validation=validation_from_payload(model.validation_payload),
        diff=diff_from_payload(model.diff_payload),
        created_by_run_id=model.created_by_run_id,
        created_by_turn_id=model.created_by_turn_id,
        actor=model.actor,
        reason=model.reason,
        created_at=coerce_utc_datetime(model.created_at),
        updated_at=coerce_utc_datetime(model.updated_at),
        expires_at=coerce_optional_utc_datetime(model.expires_at),
    )


def draft_audit_model(record: SkillDraftAuditRecord) -> SkillAuthoringAuditModel:
    return SkillAuthoringAuditModel(
        audit_id=record.audit_id,
        draft_id=record.draft_id,
        action=record.action,
        status=record.status,
        actor=record.actor,
        reason=record.reason,
        before_payload=dict(record.before_payload or {}),
        after_payload=dict(record.after_payload or {}),
        metadata_payload=dict(record.metadata or {}),
        created_at=record.created_at,
    )


def draft_audit_record(model: SkillAuthoringAuditModel) -> SkillDraftAuditRecord:
    return SkillDraftAuditRecord(
        audit_id=model.audit_id,
        draft_id=model.draft_id,
        action=model.action,
        status=model.status,
        actor=model.actor,
        reason=model.reason,
        before_payload=dict(model.before_payload or {}),
        after_payload=dict(model.after_payload or {}),
        metadata=dict(model.metadata_payload or {}),
        created_at=coerce_utc_datetime(model.created_at),
    )


def support_files_from_payload(
    payload: list[dict[str, object]] | None,
) -> tuple[SkillDraftSupportFile, ...]:
    return tuple(
        SkillDraftSupportFile(
            path=str(item.get("path") or ""),
            content=str(item.get("content") or ""),
        )
        for item in (payload or [])
        if isinstance(item, dict)
    )


def validation_payload(
    validation: SkillDraftValidation | None,
) -> dict[str, object] | None:
    if validation is None:
        return None
    return {
        "errors": list(validation.errors),
        "warnings": list(validation.warnings),
        "missing_tools": list(validation.missing_tools),
        "missing_access": list(validation.missing_access),
        "missing_effects": list(validation.missing_effects),
        "unsupported_surfaces": list(validation.unsupported_surfaces),
        "unsupported_platforms": list(validation.unsupported_platforms),
        "readiness_status": validation.readiness_status,
    }


def validation_from_payload(
    payload: dict[str, object] | None,
) -> SkillDraftValidation | None:
    if not isinstance(payload, dict):
        return None
    return SkillDraftValidation(
        errors=tuple_of_text(payload.get("errors")),
        warnings=tuple_of_text(payload.get("warnings")),
        missing_tools=tuple_of_text(payload.get("missing_tools")),
        missing_access=tuple_of_text(payload.get("missing_access")),
        missing_effects=tuple_of_text(payload.get("missing_effects")),
        unsupported_surfaces=tuple_of_text(payload.get("unsupported_surfaces")),
        unsupported_platforms=tuple_of_text(payload.get("unsupported_platforms")),
        readiness_status=str(payload.get("readiness_status") or "ready"),
    )


def diff_payload(diff: SkillDraftDiff | None) -> dict[str, object] | None:
    if diff is None:
        return None
    return {
        "manifest_diff": dict(diff.manifest_diff),
        "instructions_diff": diff.instructions_diff,
        "file_diffs": [
            {
                "path": item.path,
                "status": item.status,
                "unified_diff": item.unified_diff,
            }
            for item in diff.file_diffs
        ],
        "summary": list(diff.summary),
    }


def diff_from_payload(payload: dict[str, object] | None) -> SkillDraftDiff | None:
    if not isinstance(payload, dict):
        return None
    file_diffs = payload.get("file_diffs")
    return SkillDraftDiff(
        manifest_diff=(
            dict(payload.get("manifest_diff"))
            if isinstance(payload.get("manifest_diff"), dict)
            else {}
        ),
        instructions_diff=str(payload.get("instructions_diff") or ""),
        file_diffs=tuple(
            SkillDraftFileDiff(
                path=str(item.get("path") or ""),
                status=str(item.get("status") or "modified"),
                unified_diff=str(item.get("unified_diff") or ""),
            )
            for item in (file_diffs if isinstance(file_diffs, list) else [])
            if isinstance(item, dict)
        ),
        summary=tuple_of_text(payload.get("summary")),
    )
