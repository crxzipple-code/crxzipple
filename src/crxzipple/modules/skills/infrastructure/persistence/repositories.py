from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from sqlalchemy import delete, or_, select
from sqlalchemy.exc import IntegrityError

from crxzipple.core.db import SessionFactory
from crxzipple.modules.skills.application.models import (
    SkillDraft,
    SkillDraftAuditRecord,
)
from crxzipple.modules.skills.domain import (
    SkillEnablementPolicy,
    SkillInstallation,
    SkillPackageIndex,
    SkillPackageStatus,
    SkillReadinessSnapshot,
    SkillSource,
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
from crxzipple.modules.skills.infrastructure.persistence.repository_catalog_mappers import (
    apply_package as _apply_package,
    apply_policy as _apply_policy,
    apply_readiness as _apply_readiness,
    apply_source as _apply_source,
    installation_model as _installation_model,
    installation_record as _installation_record,
    package_model as _package_model,
    package_record as _package_record,
    policy_model as _policy_model,
    policy_record as _policy_record,
    readiness_model as _readiness_model,
    readiness_record as _readiness_record,
    source_model as _source_model,
    source_record as _source_record,
)
from crxzipple.modules.skills.infrastructure.persistence.repository_draft_mappers import (
    apply_draft as _apply_draft,
    draft_audit_model as _draft_audit_model,
    draft_audit_record as _draft_audit_record,
    draft_model as _draft_model,
    draft_record as _draft_record,
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
