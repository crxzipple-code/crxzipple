from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from sqlalchemy import delete, or_, select
from sqlalchemy.exc import IntegrityError

from crxzipple.core.db import SessionFactory
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


class SqlAlchemySkillOwnerCatalogRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def upsert_source(self, source: SkillSource) -> SkillSource:
        with self._session_factory() as session:
            existing = session.get(SkillSourceModel, source.source_id)
            stored = replace(
                source,
                created_at=(
                    coerce_utc_datetime(existing.created_at)
                    if existing is not None
                    else coerce_utc_datetime(source.created_at)
                ),
                updated_at=coerce_utc_datetime(source.updated_at),
            )
            if existing is None:
                session.add(_source_model(stored))
            else:
                _apply_source(existing, stored)
            session.commit()
            return stored

    def get_source(self, source_id: str) -> SkillSource | None:
        with self._session_factory() as session:
            model = session.get(SkillSourceModel, source_id)
            return _source_record(model) if model is not None else None

    def list_sources(self) -> tuple[SkillSource, ...]:
        with self._session_factory() as session:
            models = session.scalars(
                select(SkillSourceModel).order_by(
                    SkillSourceModel.priority.asc(),
                    SkillSourceModel.source_id.asc(),
                ),
            ).all()
            return tuple(_source_record(model) for model in models)

    def upsert_package(self, package: SkillPackageIndex) -> SkillPackageIndex:
        with self._session_factory() as session:
            existing = session.get(SkillPackageIndexModel, package.package_id)
            stored = replace(
                package,
                indexed_at=(
                    coerce_utc_datetime(existing.indexed_at)
                    if existing is not None
                    else coerce_utc_datetime(package.indexed_at)
                ),
                updated_at=coerce_utc_datetime(package.updated_at),
            )
            if existing is None:
                session.add(_package_model(stored))
            else:
                _apply_package(existing, stored)
            session.commit()
            return stored

    def get_package(self, package_id: str) -> SkillPackageIndex | None:
        with self._session_factory() as session:
            model = session.get(SkillPackageIndexModel, package_id)
            return _package_record(model) if model is not None else None

    def get_package_by_skill(
        self,
        *,
        source_id: str,
        skill_id: str,
    ) -> SkillPackageIndex | None:
        with self._session_factory() as session:
            model = session.scalars(
                select(SkillPackageIndexModel)
                .where(SkillPackageIndexModel.source_id == source_id)
                .where(SkillPackageIndexModel.skill_id == skill_id)
                .limit(1),
            ).first()
            return _package_record(model) if model is not None else None

    def list_packages(
        self,
        *,
        source_id: str | None = None,
        include_removed: bool = False,
    ) -> tuple[SkillPackageIndex, ...]:
        with self._session_factory() as session:
            statement = select(SkillPackageIndexModel)
            if source_id is not None:
                statement = statement.where(
                    SkillPackageIndexModel.source_id == source_id
                )
            if not include_removed:
                statement = statement.where(
                    SkillPackageIndexModel.status != SkillPackageStatus.REMOVED.value,
                )
            models = session.scalars(
                statement.order_by(
                    SkillPackageIndexModel.source_id.asc(),
                    SkillPackageIndexModel.name.asc(),
                ),
            ).all()
            return tuple(_package_record(model) for model in models)

    def upsert_enablement_policy(
        self,
        policy: SkillEnablementPolicy,
    ) -> SkillEnablementPolicy:
        with self._session_factory() as session:
            existing = session.get(SkillEnablementPolicyModel, policy.policy_id)
            stored = replace(
                policy,
                created_at=(
                    coerce_utc_datetime(existing.created_at)
                    if existing is not None
                    else coerce_utc_datetime(policy.created_at)
                ),
                updated_at=coerce_utc_datetime(policy.updated_at),
            )
            if existing is None:
                session.add(_policy_model(stored))
            else:
                _apply_policy(existing, stored)
            session.commit()
            return stored

    def get_enablement_policy(
        self,
        policy_id: str,
    ) -> SkillEnablementPolicy | None:
        with self._session_factory() as session:
            model = session.get(SkillEnablementPolicyModel, policy_id)
            return _policy_record(model) if model is not None else None

    def list_enablement_policies(
        self,
        *,
        target_kind: str | None = None,
        target_id: str | None = None,
    ) -> tuple[SkillEnablementPolicy, ...]:
        with self._session_factory() as session:
            statement = select(SkillEnablementPolicyModel)
            if target_kind is not None:
                statement = statement.where(
                    SkillEnablementPolicyModel.target_kind == target_kind,
                )
            if target_id is not None:
                statement = statement.where(
                    SkillEnablementPolicyModel.target_id == target_id
                )
            models = session.scalars(
                statement.order_by(
                    SkillEnablementPolicyModel.priority.asc(),
                    SkillEnablementPolicyModel.policy_id.asc(),
                ),
            ).all()
            return tuple(_policy_record(model) for model in models)

    def upsert_readiness(
        self,
        snapshot: SkillReadinessSnapshot,
    ) -> SkillReadinessSnapshot:
        with self._session_factory() as session:
            existing = session.get(SkillReadinessSnapshotModel, snapshot.skill_id)
            if existing is None:
                session.add(_readiness_model(snapshot))
            else:
                _apply_readiness(existing, snapshot)
            try:
                session.commit()
                return snapshot
            except IntegrityError:
                session.rollback()
                if existing is not None:
                    raise

        with self._session_factory() as session:
            existing = session.get(SkillReadinessSnapshotModel, snapshot.skill_id)
            if existing is None:
                raise RuntimeError(
                    f"Skill readiness '{snapshot.skill_id}' conflicted during upsert but could not be reloaded.",
                )
            _apply_readiness(existing, snapshot)
            session.commit()
            return snapshot

    def get_readiness(self, skill_id: str) -> SkillReadinessSnapshot | None:
        with self._session_factory() as session:
            model = session.get(SkillReadinessSnapshotModel, skill_id)
            return _readiness_record(model) if model is not None else None

    def list_readiness(
        self,
        *,
        source_id: str | None = None,
    ) -> tuple[SkillReadinessSnapshot, ...]:
        with self._session_factory() as session:
            statement = select(SkillReadinessSnapshotModel)
            if source_id is not None:
                statement = statement.where(
                    SkillReadinessSnapshotModel.source_id == source_id
                )
            models = session.scalars(
                statement.order_by(SkillReadinessSnapshotModel.skill_id.asc()),
            ).all()
            return tuple(_readiness_record(model) for model in models)

    def record_installation(
        self,
        installation: SkillInstallation,
    ) -> SkillInstallation:
        with self._session_factory() as session:
            stored = replace(
                installation,
                created_at=coerce_utc_datetime(installation.created_at),
            )
            session.merge(_installation_model(stored))
            session.commit()
            return stored

    def list_installations(
        self,
        *,
        skill_id: str | None = None,
        source_id: str | None = None,
        limit: int = 100,
    ) -> tuple[SkillInstallation, ...]:
        with self._session_factory() as session:
            statement = select(SkillInstallationModel)
            if skill_id is not None:
                statement = statement.where(SkillInstallationModel.skill_id == skill_id)
            if source_id is not None:
                statement = statement.where(
                    SkillInstallationModel.source_id == source_id,
                )
            models = session.scalars(
                statement.order_by(
                    SkillInstallationModel.created_at.desc(),
                    SkillInstallationModel.installation_id.desc(),
                ).limit(max(1, limit)),
            ).all()
            return tuple(_installation_record(model) for model in models)

    def save_draft(self, draft: SkillDraft) -> SkillDraft:
        with self._session_factory() as session:
            existing = session.get(SkillAuthoringDraftModel, draft.draft_id)
            stored = replace(
                draft,
                created_at=(
                    coerce_utc_datetime(existing.created_at)
                    if existing is not None
                    else coerce_utc_datetime(draft.created_at)
                ),
                updated_at=coerce_utc_datetime(draft.updated_at),
                expires_at=coerce_optional_utc_datetime(draft.expires_at),
            )
            if existing is None:
                session.add(_draft_model(stored))
            else:
                _apply_draft(existing, stored)
            session.commit()
            return stored

    def get_draft(self, draft_id: str) -> SkillDraft | None:
        with self._session_factory() as session:
            model = session.get(SkillAuthoringDraftModel, draft_id)
            return _draft_record(model) if model is not None else None

    def list_drafts(
        self,
        *,
        status: str | None = None,
        skill_name: str | None = None,
        run_id: str | None = None,
        workspace_dir: str | None = None,
        limit: int = 100,
    ) -> tuple[SkillDraft, ...]:
        with self._session_factory() as session:
            statement = select(SkillAuthoringDraftModel)
            if status is not None:
                statement = statement.where(SkillAuthoringDraftModel.status == status)
            else:
                now = datetime.now(timezone.utc)
                statement = statement.where(
                    or_(
                        SkillAuthoringDraftModel.expires_at.is_(None),
                        SkillAuthoringDraftModel.expires_at > now,
                    ),
                )
            if skill_name is not None:
                statement = statement.where(
                    SkillAuthoringDraftModel.skill_name == skill_name,
                )
            if run_id is not None:
                statement = statement.where(
                    SkillAuthoringDraftModel.created_by_run_id == run_id,
                )
            if workspace_dir is not None:
                statement = statement.where(
                    SkillAuthoringDraftModel.workspace_dir == workspace_dir,
                )
            models = session.scalars(
                statement.order_by(
                    SkillAuthoringDraftModel.updated_at.desc(),
                    SkillAuthoringDraftModel.draft_id.desc(),
                ).limit(max(1, limit)),
            ).all()
            return tuple(_draft_record(model) for model in models)

    def delete_draft(self, draft_id: str) -> bool:
        with self._session_factory() as session:
            result = session.execute(
                delete(SkillAuthoringDraftModel).where(
                    SkillAuthoringDraftModel.draft_id == draft_id,
                ),
            )
            session.commit()
            return bool(result.rowcount)

    def append_draft_audit(
        self,
        record: SkillDraftAuditRecord,
    ) -> SkillDraftAuditRecord:
        stored = replace(
            record,
            created_at=coerce_utc_datetime(record.created_at),
            before_payload=dict(record.before_payload or {}),
            after_payload=dict(record.after_payload or {}),
            metadata=dict(record.metadata or {}),
        )
        with self._session_factory() as session:
            session.add(_draft_audit_model(stored))
            session.commit()
        return stored

    def list_draft_audit(
        self,
        *,
        draft_id: str,
        limit: int = 100,
    ) -> tuple[SkillDraftAuditRecord, ...]:
        with self._session_factory() as session:
            models = session.scalars(
                select(SkillAuthoringAuditModel)
                .where(SkillAuthoringAuditModel.draft_id == draft_id)
                .order_by(
                    SkillAuthoringAuditModel.created_at.desc(),
                    SkillAuthoringAuditModel.audit_id.desc(),
                )
                .limit(max(1, limit)),
            ).all()
            return tuple(_draft_audit_record(model) for model in models)


def _source_model(source: SkillSource) -> SkillSourceModel:
    return SkillSourceModel(**_source_mapping(source))


def _source_mapping(source: SkillSource) -> dict[str, object]:
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


def _apply_source(model: SkillSourceModel, source: SkillSource) -> None:
    for key, value in _source_mapping(source).items():
        setattr(model, key, value)


def _source_record(model: SkillSourceModel) -> SkillSource:
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


def _package_model(package: SkillPackageIndex) -> SkillPackageIndexModel:
    return SkillPackageIndexModel(**_package_mapping(package))


def _package_mapping(package: SkillPackageIndex) -> dict[str, object]:
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


def _apply_package(model: SkillPackageIndexModel, package: SkillPackageIndex) -> None:
    for key, value in _package_mapping(package).items():
        setattr(model, key, value)


def _package_record(model: SkillPackageIndexModel) -> SkillPackageIndex:
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
        requirements=_requirements_from_payload(model.requirements_payload),
        capability_requirements=dict(model.capability_requirements_payload or {}),
        metadata=dict(model.metadata_payload or {}),
        indexed_at=coerce_utc_datetime(model.indexed_at),
        updated_at=coerce_utc_datetime(model.updated_at),
    )


def _policy_model(policy: SkillEnablementPolicy) -> SkillEnablementPolicyModel:
    return SkillEnablementPolicyModel(**_policy_mapping(policy))


def _policy_mapping(policy: SkillEnablementPolicy) -> dict[str, object]:
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


def _apply_policy(
    model: SkillEnablementPolicyModel,
    policy: SkillEnablementPolicy,
) -> None:
    for key, value in _policy_mapping(policy).items():
        setattr(model, key, value)


def _policy_record(model: SkillEnablementPolicyModel) -> SkillEnablementPolicy:
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


def _readiness_model(snapshot: SkillReadinessSnapshot) -> SkillReadinessSnapshotModel:
    return SkillReadinessSnapshotModel(
        skill_id=snapshot.skill_id,
        source_id=snapshot.source_id,
        status=snapshot.status.value,
        checks_payload=[dict(check) for check in snapshot.checks],
        reason=snapshot.reason,
        metadata_payload=dict(snapshot.metadata),
        updated_at=snapshot.updated_at,
    )


def _apply_readiness(
    model: SkillReadinessSnapshotModel,
    snapshot: SkillReadinessSnapshot,
) -> None:
    replacement = _readiness_model(snapshot)
    for key in (
        "source_id",
        "status",
        "checks_payload",
        "reason",
        "metadata_payload",
        "updated_at",
    ):
        setattr(model, key, getattr(replacement, key))


def _readiness_record(model: SkillReadinessSnapshotModel) -> SkillReadinessSnapshot:
    return SkillReadinessSnapshot(
        skill_id=model.skill_id,
        source_id=model.source_id,
        status=model.status,
        checks=tuple(dict(check) for check in (model.checks_payload or [])),
        reason=model.reason,
        metadata=dict(model.metadata_payload or {}),
        updated_at=coerce_utc_datetime(model.updated_at),
    )


def _installation_model(installation: SkillInstallation) -> SkillInstallationModel:
    return SkillInstallationModel(**_installation_mapping(installation))


def _installation_mapping(installation: SkillInstallation) -> dict[str, object]:
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


def _installation_record(model: SkillInstallationModel) -> SkillInstallation:
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


def _draft_model(draft: SkillDraft) -> SkillAuthoringDraftModel:
    return SkillAuthoringDraftModel(**_draft_mapping(draft))


def _draft_mapping(draft: SkillDraft) -> dict[str, object]:
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
        "validation_payload": _validation_payload(draft.validation),
        "diff_payload": _diff_payload(draft.diff),
        "created_by_run_id": draft.created_by_run_id,
        "created_by_turn_id": draft.created_by_turn_id,
        "actor": draft.actor,
        "reason": draft.reason,
        "created_at": draft.created_at,
        "updated_at": draft.updated_at,
        "expires_at": draft.expires_at,
    }


def _apply_draft(model: SkillAuthoringDraftModel, draft: SkillDraft) -> None:
    for key, value in _draft_mapping(draft).items():
        setattr(model, key, value)


def _draft_record(model: SkillAuthoringDraftModel) -> SkillDraft:
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
        support_files=_support_files_from_payload(model.support_files_payload),
        requirements=_requirements_from_payload(model.requirements_payload),
        validation=_validation_from_payload(model.validation_payload),
        diff=_diff_from_payload(model.diff_payload),
        created_by_run_id=model.created_by_run_id,
        created_by_turn_id=model.created_by_turn_id,
        actor=model.actor,
        reason=model.reason,
        created_at=coerce_utc_datetime(model.created_at),
        updated_at=coerce_utc_datetime(model.updated_at),
        expires_at=coerce_optional_utc_datetime(model.expires_at),
    )


def _draft_audit_model(record: SkillDraftAuditRecord) -> SkillAuthoringAuditModel:
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


def _draft_audit_record(model: SkillAuthoringAuditModel) -> SkillDraftAuditRecord:
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


def _support_files_from_payload(
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


def _validation_payload(
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


def _validation_from_payload(
    payload: dict[str, object] | None,
) -> SkillDraftValidation | None:
    if not isinstance(payload, dict):
        return None
    return SkillDraftValidation(
        errors=_tuple_of_text(payload.get("errors")),
        warnings=_tuple_of_text(payload.get("warnings")),
        missing_tools=_tuple_of_text(payload.get("missing_tools")),
        missing_access=_tuple_of_text(payload.get("missing_access")),
        missing_effects=_tuple_of_text(payload.get("missing_effects")),
        unsupported_surfaces=_tuple_of_text(payload.get("unsupported_surfaces")),
        unsupported_platforms=_tuple_of_text(payload.get("unsupported_platforms")),
        readiness_status=str(payload.get("readiness_status") or "ready"),
    )


def _diff_payload(diff: SkillDraftDiff | None) -> dict[str, object] | None:
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


def _diff_from_payload(payload: dict[str, object] | None) -> SkillDraftDiff | None:
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
        summary=_tuple_of_text(payload.get("summary")),
    )


def _requirements_from_payload(payload: dict[str, object] | None) -> SkillRequirements:
    raw = dict(payload or {})
    return SkillRequirements(
        required_tools=_tuple_of_text(raw.get("required_tools")),
        optional_tools=_tuple_of_text(raw.get("optional_tools")),
        suggested_tools=_tuple_of_text(raw.get("suggested_tools")),
        required_effects=_tuple_of_text(raw.get("required_effects")),
        surfaces=_tuple_of_text(raw.get("surfaces")),
        supported_platforms=_tuple_of_text(raw.get("supported_platforms")),
        required_access=_tuple_of_text(raw.get("required_access")),
        setup_hints=_tuple_of_text(raw.get("setup_hints")),
    )


def _tuple_of_text(value: object) -> tuple[str, ...]:
    if not isinstance(value, list | tuple):
        return ()
    return tuple(str(item) for item in value if isinstance(item, str) and item.strip())
