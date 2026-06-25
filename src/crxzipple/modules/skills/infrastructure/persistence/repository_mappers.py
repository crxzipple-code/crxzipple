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
from crxzipple.modules.skills.domain import (
    SkillEnablementPolicy,
    SkillEnablementTargetKind,
    SkillInstallation,
    SkillInstallationStatus,
    SkillInstallScope,
    SkillPackageIndex,
    SkillPackageStatus,
    SkillReadinessSnapshot,
    SkillRequirements,
    SkillRuntimeVisibility,
    SkillSource,
    SkillSourceStatus,
    SkillSourceSyncStatus,
    SkillSourceType,
)
from crxzipple.modules.skills.infrastructure.persistence.models import (
    SkillAuthoringAuditModel,
    SkillAuthoringDraftModel,
    SkillEnablementPolicyModel,
    SkillInstallationModel,
    SkillPackageIndexModel,
    SkillReadinessSnapshotModel,
    SkillSourceModel,
)
from crxzipple.shared.time import coerce_optional_utc_datetime, coerce_utc_datetime


def source_model(source: SkillSource) -> SkillSourceModel:
    return SkillSourceModel(**source_mapping(source))


def source_mapping(source: SkillSource) -> dict[str, object]:
    return {
        "source_id": source.source_id,
        "source_type": source.source_type.value,
        "root_uri": source.root_uri,
        "status": source.status.value,
        "sync_status": source.sync_status.value,
        "scope": source.scope,
        "priority": source.priority,
        "enabled": source.enabled,
        "readonly": source.readonly,
        "metadata_payload": dict(source.metadata),
        "last_synced_at": source.last_synced_at,
        "created_at": source.created_at,
        "updated_at": source.updated_at,
    }


def apply_source(model: SkillSourceModel, source: SkillSource) -> None:
    for key, value in source_mapping(source).items():
        setattr(model, key, value)


def source_record(model: SkillSourceModel) -> SkillSource:
    return SkillSource(
        source_id=model.source_id,
        source_type=SkillSourceType(model.source_type),
        root_uri=model.root_uri,
        status=SkillSourceStatus(model.status),
        sync_status=SkillSourceSyncStatus(model.sync_status),
        scope=model.scope,
        priority=model.priority,
        enabled=model.enabled,
        readonly=model.readonly,
        metadata=dict(model.metadata_payload or {}),
        last_synced_at=coerce_optional_utc_datetime(model.last_synced_at),
        created_at=coerce_utc_datetime(model.created_at),
        updated_at=coerce_utc_datetime(model.updated_at),
    )


def package_model(package: SkillPackageIndex) -> SkillPackageIndexModel:
    return SkillPackageIndexModel(**package_mapping(package))


def package_mapping(package: SkillPackageIndex) -> dict[str, object]:
    return {
        "package_id": package.package_id,
        "skill_id": package.skill_id,
        "name": package.name,
        "source_id": package.source_id,
        "root_uri": package.root_uri,
        "manifest_uri": package.manifest_uri,
        "instructions_uri": package.instructions_uri,
        "version": package.version,
        "fingerprint": package.fingerprint,
        "status": package.status.value,
        "requirements_payload": package.requirements.to_payload(),
        "capability_requirements_payload": dict(package.capability_requirements),
        "metadata_payload": dict(package.metadata),
        "indexed_at": package.indexed_at,
        "updated_at": package.updated_at,
    }


def apply_package(model: SkillPackageIndexModel, package: SkillPackageIndex) -> None:
    for key, value in package_mapping(package).items():
        setattr(model, key, value)


def package_record(model: SkillPackageIndexModel) -> SkillPackageIndex:
    return SkillPackageIndex(
        package_id=model.package_id,
        skill_id=model.skill_id,
        name=model.name,
        source_id=model.source_id,
        root_uri=model.root_uri,
        manifest_uri=model.manifest_uri,
        instructions_uri=model.instructions_uri,
        version=model.version,
        fingerprint=model.fingerprint,
        status=SkillPackageStatus(model.status),
        requirements=requirements_from_payload(model.requirements_payload),
        capability_requirements=dict(model.capability_requirements_payload or {}),
        metadata=dict(model.metadata_payload or {}),
        indexed_at=coerce_utc_datetime(model.indexed_at),
        updated_at=coerce_utc_datetime(model.updated_at),
    )


def policy_model(policy: SkillEnablementPolicy) -> SkillEnablementPolicyModel:
    return SkillEnablementPolicyModel(**policy_mapping(policy))


def policy_mapping(policy: SkillEnablementPolicy) -> dict[str, object]:
    return {
        "policy_id": policy.policy_id,
        "target_kind": policy.target_kind.value,
        "target_id": policy.target_id,
        "enabled": policy.enabled,
        "trusted": policy.trusted,
        "runtime_visibility": policy.runtime_visibility.value,
        "priority": policy.priority,
        "reason": policy.reason,
        "metadata_payload": dict(policy.metadata),
        "created_at": policy.created_at,
        "updated_at": policy.updated_at,
    }


def apply_policy(
    model: SkillEnablementPolicyModel,
    policy: SkillEnablementPolicy,
) -> None:
    for key, value in policy_mapping(policy).items():
        setattr(model, key, value)


def policy_record(model: SkillEnablementPolicyModel) -> SkillEnablementPolicy:
    return SkillEnablementPolicy(
        policy_id=model.policy_id,
        target_kind=SkillEnablementTargetKind(model.target_kind),
        target_id=model.target_id,
        enabled=model.enabled,
        trusted=model.trusted,
        runtime_visibility=SkillRuntimeVisibility(model.runtime_visibility),
        priority=model.priority,
        reason=model.reason,
        metadata=dict(model.metadata_payload or {}),
        created_at=coerce_utc_datetime(model.created_at),
        updated_at=coerce_utc_datetime(model.updated_at),
    )


def readiness_model(snapshot: SkillReadinessSnapshot) -> SkillReadinessSnapshotModel:
    return SkillReadinessSnapshotModel(
        skill_id=snapshot.skill_id,
        source_id=snapshot.source_id,
        status=snapshot.status.value,
        checks_payload=[dict(check) for check in snapshot.checks],
        reason=snapshot.reason,
        metadata_payload=dict(snapshot.metadata),
        updated_at=snapshot.updated_at,
    )


def apply_readiness(
    model: SkillReadinessSnapshotModel,
    snapshot: SkillReadinessSnapshot,
) -> None:
    replacement = readiness_model(snapshot)
    for key in (
        "source_id",
        "status",
        "checks_payload",
        "reason",
        "metadata_payload",
        "updated_at",
    ):
        setattr(model, key, getattr(replacement, key))


def readiness_record(model: SkillReadinessSnapshotModel) -> SkillReadinessSnapshot:
    return SkillReadinessSnapshot(
        skill_id=model.skill_id,
        source_id=model.source_id,
        status=model.status,
        checks=tuple(dict(check) for check in (model.checks_payload or [])),
        reason=model.reason,
        metadata=dict(model.metadata_payload or {}),
        updated_at=coerce_utc_datetime(model.updated_at),
    )


def installation_model(installation: SkillInstallation) -> SkillInstallationModel:
    return SkillInstallationModel(**installation_mapping(installation))


def installation_mapping(installation: SkillInstallation) -> dict[str, object]:
    return {
        "installation_id": installation.installation_id,
        "action": installation.action,
        "status": installation.status.value,
        "source_id": installation.source_id,
        "skill_id": installation.skill_id,
        "skill_name": installation.skill_name,
        "source_uri": installation.source_uri,
        "target_uri": installation.target_uri,
        "actor_id": installation.actor_id,
        "reason": installation.reason,
        "message": installation.message,
        "metadata_payload": dict(installation.metadata),
        "created_at": installation.created_at,
    }


def installation_record(model: SkillInstallationModel) -> SkillInstallation:
    return SkillInstallation(
        installation_id=model.installation_id,
        action=model.action,
        status=SkillInstallationStatus(model.status),
        source_id=model.source_id,
        skill_id=model.skill_id,
        skill_name=model.skill_name,
        source_uri=model.source_uri,
        target_uri=model.target_uri,
        actor_id=model.actor_id,
        reason=model.reason,
        message=model.message,
        metadata=dict(model.metadata_payload or {}),
        created_at=coerce_utc_datetime(model.created_at),
    )


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


def requirements_from_payload(payload: dict[str, object] | None) -> SkillRequirements:
    raw = dict(payload or {})
    return SkillRequirements(
        required_tools=tuple_of_text(raw.get("required_tools")),
        optional_tools=tuple_of_text(raw.get("optional_tools")),
        suggested_tools=tuple_of_text(raw.get("suggested_tools")),
        required_effects=tuple_of_text(raw.get("required_effects")),
        surfaces=tuple_of_text(raw.get("surfaces")),
        supported_platforms=tuple_of_text(raw.get("supported_platforms")),
        required_access=tuple_of_text(raw.get("required_access")),
        setup_hints=tuple_of_text(raw.get("setup_hints")),
    )


def tuple_of_text(value: object) -> tuple[str, ...]:
    if not isinstance(value, list | tuple):
        return ()
    return tuple(str(item) for item in value if isinstance(item, str) and item.strip())
