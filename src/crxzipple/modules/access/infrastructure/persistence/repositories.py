from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from typing import Any
from uuid import uuid4

from sqlalchemy import select

from crxzipple.core.db import SessionFactory
from crxzipple.modules.access.application.repositories import (
    AccessActionAuditRecord,
    AccessAssetRecord,
    AccessConnectionProfileRecord,
    AccessConsumerBindingRecord,
    AccessCredentialBindingRecord,
    AccessOAuthAccountRecord,
    AccessOAuthProviderRecord,
    AccessReadinessSnapshotRecord,
    AccessSecretBindingRecord,
    AccessSetupSessionRecord,
)
from crxzipple.modules.access.infrastructure.persistence.models import (
    AccessActionAuditModel,
    AccessAssetModel,
    AccessConnectionProfileModel,
    AccessConsumerBindingModel,
    AccessCredentialBindingModel,
    AccessOAuthAccountModel,
    AccessOAuthProviderModel,
    AccessReadinessSnapshotModel,
    AccessSecretBindingModel,
    AccessSetupSessionModel,
)
from crxzipple.modules.access.infrastructure.persistence.repository_mappers import (
    _action_audit_record,
    _apply_oauth_account,
    _apply_oauth_provider,
    _asset_model,
    _asset_record,
    _coerce_or_now,
    _connection_profile_model,
    _connection_profile_record,
    _consumer_binding_model,
    _consumer_binding_record,
    _credential_binding_model,
    _credential_binding_record,
    _oauth_account_model,
    _oauth_account_record,
    _oauth_provider_model,
    _oauth_provider_record,
    _optional_text,
    _readiness_snapshot_model,
    _readiness_snapshot_record,
    _record_created_at,
    _required_text,
    _secret_binding_model,
    _secret_binding_record,
    _setup_session_model,
    _setup_session_record,
    _with_create_timestamps,
)
from crxzipple.shared.time import coerce_utc_datetime


class SqlAlchemyAccessGovernanceRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def create_asset(self, record: AccessAssetRecord) -> AccessAssetRecord:
        stored = replace(record, **_with_create_timestamps(record))
        with self._session_factory() as session:
            session.add(_asset_model(stored))
            session.commit()
        return stored

    def get_asset(self, asset_id: str) -> AccessAssetRecord | None:
        with self._session_factory() as session:
            model = session.get(AccessAssetModel, _required_text(asset_id, "asset id"))
            return _asset_record(model) if model is not None else None

    def list_assets(self) -> tuple[AccessAssetRecord, ...]:
        with self._session_factory() as session:
            models = session.scalars(
                select(AccessAssetModel).order_by(AccessAssetModel.asset_id.asc()),
            ).all()
            return tuple(_asset_record(model) for model in models)

    def create_credential_binding(
        self,
        record: AccessCredentialBindingRecord,
    ) -> AccessCredentialBindingRecord:
        stored = replace(record, **_with_create_timestamps(record))
        with self._session_factory() as session:
            session.add(_credential_binding_model(stored))
            session.commit()
        return stored

    def get_credential_binding(
        self,
        binding_id: str,
    ) -> AccessCredentialBindingRecord | None:
        with self._session_factory() as session:
            model = session.get(
                AccessCredentialBindingModel,
                _required_text(binding_id, "binding id"),
            )
            return _credential_binding_record(model) if model is not None else None

    def list_credential_bindings(self) -> tuple[AccessCredentialBindingRecord, ...]:
        with self._session_factory() as session:
            models = session.scalars(
                select(AccessCredentialBindingModel).order_by(
                    AccessCredentialBindingModel.binding_id.asc(),
                ),
            ).all()
            return tuple(_credential_binding_record(model) for model in models)

    def create_consumer_binding(
        self,
        record: AccessConsumerBindingRecord,
    ) -> AccessConsumerBindingRecord:
        stored = replace(record, **_with_create_timestamps(record))
        with self._session_factory() as session:
            session.add(_consumer_binding_model(stored))
            session.commit()
        return stored

    def get_consumer_binding(
        self,
        binding_id: str,
    ) -> AccessConsumerBindingRecord | None:
        with self._session_factory() as session:
            model = session.get(
                AccessConsumerBindingModel,
                _required_text(binding_id, "consumer binding id"),
            )
            return _consumer_binding_record(model) if model is not None else None

    def list_consumer_bindings(self) -> tuple[AccessConsumerBindingRecord, ...]:
        with self._session_factory() as session:
            models = session.scalars(
                select(AccessConsumerBindingModel).order_by(
                    AccessConsumerBindingModel.consumer_module.asc(),
                    AccessConsumerBindingModel.consumer_kind.asc(),
                    AccessConsumerBindingModel.consumer_id.asc(),
                    AccessConsumerBindingModel.binding_id.asc(),
                ),
            ).all()
            return tuple(_consumer_binding_record(model) for model in models)

    def create_secret_binding(
        self,
        record: AccessSecretBindingRecord,
    ) -> AccessSecretBindingRecord:
        stored = replace(record, **_with_create_timestamps(record))
        with self._session_factory() as session:
            session.add(_secret_binding_model(stored))
            session.commit()
        return stored

    def list_secret_bindings(self) -> tuple[AccessSecretBindingRecord, ...]:
        with self._session_factory() as session:
            models = session.scalars(
                select(AccessSecretBindingModel).order_by(
                    AccessSecretBindingModel.binding_id.asc(),
                ),
            ).all()
            return tuple(_secret_binding_record(model) for model in models)

    def create_connection_profile(
        self,
        record: AccessConnectionProfileRecord,
    ) -> AccessConnectionProfileRecord:
        stored = replace(record, **_with_create_timestamps(record))
        with self._session_factory() as session:
            session.add(_connection_profile_model(stored))
            session.commit()
        return stored

    def list_connection_profiles(self) -> tuple[AccessConnectionProfileRecord, ...]:
        with self._session_factory() as session:
            models = session.scalars(
                select(AccessConnectionProfileModel).order_by(
                    AccessConnectionProfileModel.profile_id.asc(),
                ),
            ).all()
            return tuple(_connection_profile_record(model) for model in models)

    def upsert_oauth_provider(
        self,
        record: AccessOAuthProviderRecord,
    ) -> AccessOAuthProviderRecord:
        with self._session_factory() as session:
            existing = session.get(
                AccessOAuthProviderModel,
                _required_text(record.provider_id, "OAuth provider id"),
            )
            stored = replace(
                record,
                created_at=(
                    coerce_utc_datetime(existing.created_at)
                    if existing is not None
                    else _record_created_at(record)
                ),
                updated_at=_coerce_or_now(record.updated_at),
            )
            if existing is None:
                session.add(_oauth_provider_model(stored))
            else:
                _apply_oauth_provider(existing, stored)
            session.commit()
        return stored

    def get_oauth_provider(self, provider_id: str) -> AccessOAuthProviderRecord | None:
        with self._session_factory() as session:
            model = session.get(
                AccessOAuthProviderModel,
                _required_text(provider_id, "OAuth provider id"),
            )
            return _oauth_provider_record(model) if model is not None else None

    def list_oauth_providers(self) -> tuple[AccessOAuthProviderRecord, ...]:
        with self._session_factory() as session:
            models = session.scalars(
                select(AccessOAuthProviderModel).order_by(
                    AccessOAuthProviderModel.provider_id.asc(),
                ),
            ).all()
            return tuple(_oauth_provider_record(model) for model in models)

    def upsert_oauth_account(
        self,
        record: AccessOAuthAccountRecord,
    ) -> AccessOAuthAccountRecord:
        with self._session_factory() as session:
            existing = session.get(
                AccessOAuthAccountModel,
                _required_text(record.account_id, "OAuth account id"),
            )
            stored = replace(
                record,
                created_at=(
                    coerce_utc_datetime(existing.created_at)
                    if existing is not None
                    else _record_created_at(record)
                ),
                updated_at=_coerce_or_now(record.updated_at),
            )
            if existing is None:
                session.add(_oauth_account_model(stored))
            else:
                _apply_oauth_account(existing, stored)
            session.commit()
        return stored

    def get_oauth_account(self, account_id: str) -> AccessOAuthAccountRecord | None:
        with self._session_factory() as session:
            model = session.get(
                AccessOAuthAccountModel,
                _required_text(account_id, "OAuth account id"),
            )
            return _oauth_account_record(model) if model is not None else None

    def list_oauth_accounts(self) -> tuple[AccessOAuthAccountRecord, ...]:
        with self._session_factory() as session:
            models = session.scalars(
                select(AccessOAuthAccountModel).order_by(
                    AccessOAuthAccountModel.provider_id.asc(),
                    AccessOAuthAccountModel.account_id.asc(),
                ),
            ).all()
            return tuple(_oauth_account_record(model) for model in models)

    def create_setup_session(
        self,
        record: AccessSetupSessionRecord,
    ) -> AccessSetupSessionRecord:
        stored = replace(record, **_with_create_timestamps(record))
        with self._session_factory() as session:
            session.add(_setup_session_model(stored))
            session.commit()
        return stored

    def get_setup_session(self, session_id: str) -> AccessSetupSessionRecord | None:
        with self._session_factory() as session:
            model = session.get(
                AccessSetupSessionModel,
                _required_text(session_id, "session id"),
            )
            return _setup_session_record(model) if model is not None else None

    def complete_setup_session(
        self,
        session_id: str,
        *,
        status: str,
        metadata: dict[str, Any] | None = None,
        completed_at: datetime | None = None,
    ) -> AccessSetupSessionRecord:
        with self._session_factory() as session:
            model = session.get(
                AccessSetupSessionModel,
                _required_text(session_id, "session id"),
            )
            if model is None:
                raise LookupError(f"Access setup session '{session_id}' does not exist.")
            now = _coerce_or_now(completed_at)
            model.status = _required_text(status, "setup session status")
            model.completed_at = now
            model.updated_at = now
            if metadata is not None:
                merged = dict(model.metadata_ or {})
                merged.update(dict(metadata))
                model.metadata_ = merged
            session.commit()
            return _setup_session_record(model)

    def list_setup_sessions(self) -> tuple[AccessSetupSessionRecord, ...]:
        with self._session_factory() as session:
            models = session.scalars(
                select(AccessSetupSessionModel).order_by(
                    AccessSetupSessionModel.created_at.desc(),
                    AccessSetupSessionModel.session_id.asc(),
                ),
            ).all()
            return tuple(_setup_session_record(model) for model in models)

    def create_readiness_snapshot(
        self,
        record: AccessReadinessSnapshotRecord,
    ) -> AccessReadinessSnapshotRecord:
        stored = replace(record, created_at=_record_created_at(record))
        with self._session_factory() as session:
            session.add(_readiness_snapshot_model(stored))
            session.commit()
        return stored

    def list_readiness_snapshots(
        self,
        *,
        target_kind: str | None = None,
        target_id: str | None = None,
    ) -> tuple[AccessReadinessSnapshotRecord, ...]:
        with self._session_factory() as session:
            statement = select(AccessReadinessSnapshotModel).order_by(
                AccessReadinessSnapshotModel.created_at.desc(),
                AccessReadinessSnapshotModel.snapshot_id.asc(),
            )
            if target_kind is not None:
                statement = statement.where(
                    AccessReadinessSnapshotModel.target_kind
                    == _required_text(target_kind, "target kind"),
                )
            if target_id is not None:
                statement = statement.where(
                    AccessReadinessSnapshotModel.target_id
                    == _required_text(target_id, "target id"),
                )
            models = session.scalars(statement).all()
            return tuple(_readiness_snapshot_record(model) for model in models)


class SqlAlchemyAccessActionAuditRepository:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def record_attempt(
        self,
        *,
        action_type: str,
        target_type: str,
        target_id: str | None,
        reason: str,
        operator: str | None = None,
        source: str = "access",
        request_metadata: dict[str, Any] | None = None,
        redaction_policy: dict[str, Any] | None = None,
        created_at: datetime | None = None,
    ) -> AccessActionAuditRecord:
        now = _coerce_or_now(created_at)
        model = AccessActionAuditModel(
            audit_id=f"accessact_{uuid4().hex}",
            action_type=_required_text(action_type, "action type"),
            target_type=_required_text(target_type, "target type"),
            target_id=_optional_text(target_id),
            status="attempted",
            operator=_optional_text(operator),
            source=_required_text(source, "source"),
            reason=_required_text(reason, "reason"),
            request_metadata=dict(request_metadata or {}),
            result=None,
            error=None,
            redaction_policy=dict(redaction_policy or {}),
            created_at=now,
            updated_at=now,
        )
        with self._session_factory() as session:
            session.add(model)
            session.commit()
            return _action_audit_record(model)

    def mark_succeeded(
        self,
        audit_id: str,
        *,
        result: dict[str, Any] | None = None,
        updated_at: datetime | None = None,
    ) -> AccessActionAuditRecord:
        return self._mark_terminal(
            audit_id,
            status="succeeded",
            result=dict(result) if result is not None else None,
            error=None,
            updated_at=updated_at,
        )

    def mark_failed(
        self,
        audit_id: str,
        *,
        error: dict[str, Any],
        updated_at: datetime | None = None,
    ) -> AccessActionAuditRecord:
        return self._mark_terminal(
            audit_id,
            status="failed",
            result=None,
            error=dict(error),
            updated_at=updated_at,
        )

    def list_recent(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[AccessActionAuditRecord, ...]:
        safe_limit = min(max(int(limit), 1), 200)
        safe_offset = max(int(offset), 0)
        with self._session_factory() as session:
            models = session.scalars(
                select(AccessActionAuditModel)
                .order_by(
                    AccessActionAuditModel.created_at.desc(),
                    AccessActionAuditModel.audit_id.desc(),
                )
                .limit(safe_limit)
                .offset(safe_offset),
            ).all()
            return tuple(_action_audit_record(model) for model in models)

    def _mark_terminal(
        self,
        audit_id: str,
        *,
        status: str,
        result: dict[str, Any] | None,
        error: dict[str, Any] | None,
        updated_at: datetime | None,
    ) -> AccessActionAuditRecord:
        with self._session_factory() as session:
            model = session.get(AccessActionAuditModel, audit_id)
            if model is None:
                raise LookupError(f"Access action audit '{audit_id}' does not exist.")
            model.status = status
            model.result = result
            model.error = error
            model.updated_at = _coerce_or_now(updated_at)
            session.commit()
            return _action_audit_record(model)
