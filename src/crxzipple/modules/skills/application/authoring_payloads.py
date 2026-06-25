from __future__ import annotations

from crxzipple.modules.skills.application.models import SkillDraft


def draft_event_payload(
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


def draft_audit_payload(draft: SkillDraft | None) -> dict[str, object]:
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
