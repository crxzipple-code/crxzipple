from __future__ import annotations

from crxzipple.modules.skills.application.models import (
    InstalledSkill,
    SkillDraft,
    SkillDraftAuditRecord,
    SkillDraftDiff,
    SkillDraftFileDiff,
    SkillDraftValidation,
    SkillMutationResult,
    SkillPackage,
    SkillReadResult,
    SkillReadiness,
    SkillSource,
    SkillSourceMutationResult,
    SkillSyncResult,
)


def _skill_payload(
    package: SkillPackage,
    *,
    instructions: str | None = None,
) -> dict[str, object]:
    requirements = package.requirements
    payload: dict[str, object] = {
        "name": package.name,
        "description": package.description,
        "version": package.version,
        "tags": list(package.tags),
        "source": package.source,
        "root_path": package.root_path,
        "manifest_path": package.manifest_path,
        "instructions_path": package.instructions_path,
        "resources": [
            {
                "path": resource.path,
                "kind": resource.kind,
                "size_bytes": resource.size_bytes,
            }
            for resource in package.resources
        ],
        "requirements": requirements.to_payload(),
        "manifest": {
            "api_version": package.manifest.api_version,
            "kind": package.manifest.kind,
            "name": package.manifest.name,
            "description": package.manifest.description,
            "version": package.manifest.version,
            "tags": list(package.manifest.tags),
            "when_to_use": package.manifest.when_to_use,
            "anti_patterns": list(package.manifest.anti_patterns),
            "instructions_path": package.manifest.instructions_path,
            "required_tools": list(package.manifest.required_tools),
            "optional_tools": list(package.manifest.optional_tools),
            "suggested_tools": list(package.manifest.suggested_tools),
            "required_effects": list(package.manifest.required_effects),
            "required_access": list(package.manifest.required_access),
            "surfaces": list(package.manifest.surfaces),
            "supported_platforms": list(package.manifest.supported_platforms),
            "setup_hints": list(package.manifest.setup_hints),
        },
    }
    if instructions is not None:
        payload["instructions"] = instructions
    return payload


def _read_payload(result: SkillReadResult) -> dict[str, object]:
    return {
        "skill": _skill_payload(result.package),
        "requested_path": result.requested_path,
        "resolved_path": result.resolved_path,
        "content": result.content,
    }


def _install_payload(result: InstalledSkill) -> dict[str, object]:
    payload = _skill_payload(result.package)
    payload.update(
        {
            "scope": result.scope.value,
            "target_root": result.target_root,
            "target_path": result.target_path,
        },
    )
    return payload


def _source_payload(source: SkillSource) -> dict[str, object]:
    return {
        "source_id": source.source_id,
        "source_kind": source.source_kind.value,
        "root_path": source.root_path,
        "enabled": source.enabled,
        "readonly": source.readonly,
        "package_count": source.package_count,
        "metadata": source.metadata,
        "status": source.status,
        "sync_status": source.sync_status,
        "priority": source.priority,
    }


def _readiness_payload(readiness: SkillReadiness) -> dict[str, object]:
    return {
        "status": readiness.status.value,
        "ready": readiness.ready,
        "missing_tools": list(readiness.missing_tools),
        "missing_access": list(readiness.missing_access),
        "missing_effects": list(readiness.missing_effects),
        "unsupported_surfaces": list(readiness.unsupported_surfaces),
        "unsupported_platforms": list(readiness.unsupported_platforms),
        "validation_errors": list(readiness.validation_errors),
        "setup_hints": list(readiness.setup_hints),
    }


def _sync_payload(result: SkillSyncResult) -> dict[str, object]:
    return {
        "source_id": result.source_id,
        "synced_count": result.synced_count,
        "skills": [_skill_payload(package) for package in result.packages],
    }


def _mutation_payload(result: SkillMutationResult) -> dict[str, object]:
    return {
        "action": result.action,
        "changed": result.changed,
        "message": result.message,
        "skill": _skill_payload(result.skill),
    }


def _source_mutation_payload(
    result: SkillSourceMutationResult,
) -> dict[str, object]:
    return {
        "action": result.action,
        "changed": result.changed,
        "message": result.message,
        "source": _source_payload(result.source),
    }


def _validation_payload(validation: SkillDraftValidation | None) -> dict[str, object] | None:
    if validation is None:
        return None
    return {
        "valid": validation.valid,
        "errors": list(validation.errors),
        "warnings": list(validation.warnings),
        "missing_tools": list(validation.missing_tools),
        "missing_access": list(validation.missing_access),
        "missing_effects": list(validation.missing_effects),
        "unsupported_surfaces": list(validation.unsupported_surfaces),
        "unsupported_platforms": list(validation.unsupported_platforms),
        "readiness_status": validation.readiness_status,
    }


def _file_diff_payload(diff: SkillDraftFileDiff) -> dict[str, object]:
    return {
        "path": diff.path,
        "status": diff.status,
        "unified_diff": diff.unified_diff,
    }


def _diff_payload(diff: SkillDraftDiff | None) -> dict[str, object] | None:
    if diff is None:
        return None
    return {
        "manifest_diff": dict(diff.manifest_diff),
        "instructions_diff": diff.instructions_diff,
        "file_diffs": [_file_diff_payload(item) for item in diff.file_diffs],
        "summary": list(diff.summary),
    }


def _draft_payload(draft: SkillDraft) -> dict[str, object]:
    return {
        "draft_id": draft.draft_id,
        "status": draft.status.value,
        "intent": draft.intent.value,
        "skill_name": draft.skill_name,
        "target_source_id": draft.target_source_id,
        "target_scope": draft.target_scope.value,
        "workspace_dir": draft.workspace_dir,
        "base_fingerprint": draft.base_fingerprint,
        "manifest": dict(draft.manifest or {}),
        "instructions_body": draft.instructions_body,
        "support_files": [
            {"path": item.path, "content": item.content}
            for item in draft.support_files
        ],
        "requirements": draft.requirements.to_payload(),
        "validation": _validation_payload(draft.validation),
        "diff": _diff_payload(draft.diff),
        "created_by_run_id": draft.created_by_run_id,
        "created_by_turn_id": draft.created_by_turn_id,
        "actor": draft.actor,
        "reason": draft.reason,
        "created_at": draft.created_at,
        "updated_at": draft.updated_at,
        "expires_at": draft.expires_at,
    }


def _draft_audit_payload(record: SkillDraftAuditRecord) -> dict[str, object]:
    return {
        "audit_id": record.audit_id,
        "draft_id": record.draft_id,
        "action": record.action,
        "status": record.status,
        "actor": record.actor,
        "reason": record.reason,
        "before_payload": dict(record.before_payload or {}),
        "after_payload": dict(record.after_payload or {}),
        "metadata": dict(record.metadata or {}),
        "created_at": record.created_at,
    }
