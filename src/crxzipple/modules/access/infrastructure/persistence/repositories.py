from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
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
from crxzipple.shared.time import coerce_optional_utc_datetime, coerce_utc_datetime


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


def _asset_model(record: AccessAssetRecord) -> AccessAssetModel:
    return AccessAssetModel(
        asset_id=_required_text(record.asset_id, "asset id"),
        asset_kind=_required_text(record.asset_kind, "asset kind"),
        display_name=_required_text(record.display_name, "display name"),
        governance_scope=_required_text(record.governance_scope, "governance scope"),
        status=_required_text(record.status, "status"),
        secret_policy=dict(record.secret_policy),
        storage_key=_optional_text(record.storage_key),
        consumer_modules=list(record.consumer_modules),
        readiness_policy=dict(record.readiness_policy),
        rotation_policy=dict(record.rotation_policy),
        audit_required=bool(record.audit_required),
        export_policy=dict(record.export_policy),
        degraded_reason=_optional_text(record.degraded_reason),
        redaction_policy=dict(record.redaction_policy),
        metadata_=dict(record.metadata),
        created_at=_record_created_at(record),
        updated_at=_record_updated_at(record),
    )


def _asset_record(model: AccessAssetModel) -> AccessAssetRecord:
    return AccessAssetRecord(
        asset_id=model.asset_id,
        asset_kind=model.asset_kind,
        display_name=model.display_name,
        governance_scope=model.governance_scope,
        status=model.status,
        secret_policy=dict(model.secret_policy),
        storage_key=model.storage_key,
        consumer_modules=tuple(model.consumer_modules),
        readiness_policy=dict(model.readiness_policy),
        rotation_policy=dict(model.rotation_policy),
        audit_required=model.audit_required,
        export_policy=dict(model.export_policy),
        degraded_reason=model.degraded_reason,
        redaction_policy=dict(model.redaction_policy),
        metadata=dict(model.metadata_),
        created_at=coerce_utc_datetime(model.created_at),
        updated_at=coerce_utc_datetime(model.updated_at),
    )


def _credential_binding_model(
    record: AccessCredentialBindingRecord,
) -> AccessCredentialBindingModel:
    return AccessCredentialBindingModel(
        binding_id=_required_text(record.binding_id, "binding id"),
        asset_id=_optional_text(record.asset_id),
        binding_kind=_required_text(record.binding_kind, "binding kind"),
        source_kind=_required_text(record.source_kind, "source kind"),
        source_ref=_required_text(record.source_ref, "source ref"),
        masked_preview=_optional_text(record.masked_preview),
        status=_required_text(record.status, "status"),
        redaction_policy=dict(record.redaction_policy),
        metadata_=dict(record.metadata),
        created_at=_record_created_at(record),
        updated_at=_record_updated_at(record),
    )


def _credential_binding_record(
    model: AccessCredentialBindingModel,
) -> AccessCredentialBindingRecord:
    return AccessCredentialBindingRecord(
        binding_id=model.binding_id,
        asset_id=model.asset_id,
        binding_kind=model.binding_kind,
        source_kind=model.source_kind,
        source_ref=model.source_ref,
        masked_preview=model.masked_preview,
        status=model.status,
        redaction_policy=dict(model.redaction_policy),
        metadata=dict(model.metadata_),
        created_at=coerce_utc_datetime(model.created_at),
        updated_at=coerce_utc_datetime(model.updated_at),
    )


def _consumer_binding_model(
    record: AccessConsumerBindingRecord,
) -> AccessConsumerBindingModel:
    return AccessConsumerBindingModel(
        binding_id=_required_text(record.binding_id, "consumer binding id"),
        consumer_module=_required_text(record.consumer_module, "consumer module"),
        consumer_kind=_required_text(record.consumer_kind, "consumer kind"),
        consumer_id=_required_text(record.consumer_id, "consumer id"),
        display_name=_optional_text(record.display_name),
        enabled=bool(record.enabled),
        asset_id=_optional_text(record.asset_id),
        credential_binding_id=_optional_text(record.credential_binding_id),
        credential_bindings={
            str(slot): str(binding_id)
            for slot, binding_id in record.credential_bindings.items()
            if str(slot).strip() and str(binding_id).strip()
        },
        requirement_sets=[list(items) for items in record.requirement_sets],
        status=_required_text(record.status, "status"),
        redaction_policy=dict(record.redaction_policy),
        metadata_=dict(record.metadata),
        created_at=_record_created_at(record),
        updated_at=_record_updated_at(record),
    )


def _consumer_binding_record(
    model: AccessConsumerBindingModel,
) -> AccessConsumerBindingRecord:
    return AccessConsumerBindingRecord(
        binding_id=model.binding_id,
        consumer_module=model.consumer_module,
        consumer_kind=model.consumer_kind,
        consumer_id=model.consumer_id,
        display_name=model.display_name,
        enabled=model.enabled,
        asset_id=model.asset_id,
        credential_binding_id=model.credential_binding_id,
        credential_bindings=dict(model.credential_bindings or {}),
        requirement_sets=tuple(tuple(item) for item in model.requirement_sets),
        status=model.status,
        redaction_policy=dict(model.redaction_policy),
        metadata=dict(model.metadata_),
        created_at=coerce_utc_datetime(model.created_at),
        updated_at=coerce_utc_datetime(model.updated_at),
    )


def _secret_binding_model(record: AccessSecretBindingRecord) -> AccessSecretBindingModel:
    return AccessSecretBindingModel(
        binding_id=_required_text(record.binding_id, "binding id"),
        credential_binding_id=_optional_text(record.credential_binding_id),
        storage_key=_required_text(record.storage_key, "storage key"),
        source_kind=_required_text(record.source_kind, "source kind"),
        source_ref=_optional_text(record.source_ref),
        masked_preview=_optional_text(record.masked_preview),
        status=_required_text(record.status, "status"),
        redaction_policy=dict(record.redaction_policy),
        metadata_=dict(record.metadata),
        created_at=_record_created_at(record),
        updated_at=_record_updated_at(record),
    )


def _secret_binding_record(model: AccessSecretBindingModel) -> AccessSecretBindingRecord:
    return AccessSecretBindingRecord(
        binding_id=model.binding_id,
        credential_binding_id=model.credential_binding_id,
        storage_key=model.storage_key,
        source_kind=model.source_kind,
        source_ref=model.source_ref,
        masked_preview=model.masked_preview,
        status=model.status,
        redaction_policy=dict(model.redaction_policy),
        metadata=dict(model.metadata_),
        created_at=coerce_utc_datetime(model.created_at),
        updated_at=coerce_utc_datetime(model.updated_at),
    )


def _connection_profile_model(
    record: AccessConnectionProfileRecord,
) -> AccessConnectionProfileModel:
    return AccessConnectionProfileModel(
        profile_id=_required_text(record.profile_id, "profile id"),
        asset_id=_optional_text(record.asset_id),
        provider=_required_text(record.provider, "provider"),
        profile_kind=_required_text(record.profile_kind, "profile kind"),
        endpoint_ref=_optional_text(record.endpoint_ref),
        credential_binding_id=_optional_text(record.credential_binding_id),
        status=_required_text(record.status, "status"),
        redaction_policy=dict(record.redaction_policy),
        metadata_=dict(record.metadata),
        created_at=_record_created_at(record),
        updated_at=_record_updated_at(record),
    )


def _connection_profile_record(
    model: AccessConnectionProfileModel,
) -> AccessConnectionProfileRecord:
    return AccessConnectionProfileRecord(
        profile_id=model.profile_id,
        asset_id=model.asset_id,
        provider=model.provider,
        profile_kind=model.profile_kind,
        endpoint_ref=model.endpoint_ref,
        credential_binding_id=model.credential_binding_id,
        status=model.status,
        redaction_policy=dict(model.redaction_policy),
        metadata=dict(model.metadata_),
        created_at=coerce_utc_datetime(model.created_at),
        updated_at=coerce_utc_datetime(model.updated_at),
    )


def _oauth_provider_model(record: AccessOAuthProviderRecord) -> AccessOAuthProviderModel:
    return AccessOAuthProviderModel(
        provider_id=_required_text(record.provider_id, "OAuth provider id"),
        display_name=_required_text(record.display_name, "OAuth provider display name"),
        provider_kind=_required_text(record.provider_kind, "OAuth provider kind"),
        authorization_url=_optional_text(record.authorization_url),
        token_url=_optional_text(record.token_url),
        revocation_url=_optional_text(record.revocation_url),
        device_code_url=_optional_text(record.device_code_url),
        default_scopes=list(record.default_scopes),
        client_id=_optional_text(record.client_id),
        client_credential_binding_id=_optional_text(record.client_credential_binding_id),
        callback_url=_optional_text(record.callback_url),
        callback_mode=_required_text(record.callback_mode, "OAuth callback mode"),
        status=_required_text(record.status, "OAuth provider status"),
        redaction_policy=dict(record.redaction_policy),
        metadata_=dict(record.metadata),
        created_at=_record_created_at(record),
        updated_at=_record_updated_at(record),
    )


def _apply_oauth_provider(
    model: AccessOAuthProviderModel,
    record: AccessOAuthProviderRecord,
) -> None:
    model.display_name = _required_text(record.display_name, "OAuth provider display name")
    model.provider_kind = _required_text(record.provider_kind, "OAuth provider kind")
    model.authorization_url = _optional_text(record.authorization_url)
    model.token_url = _optional_text(record.token_url)
    model.revocation_url = _optional_text(record.revocation_url)
    model.device_code_url = _optional_text(record.device_code_url)
    model.default_scopes = list(record.default_scopes)
    model.client_id = _optional_text(record.client_id)
    model.client_credential_binding_id = _optional_text(
        record.client_credential_binding_id,
    )
    model.callback_url = _optional_text(record.callback_url)
    model.callback_mode = _required_text(record.callback_mode, "OAuth callback mode")
    model.status = _required_text(record.status, "OAuth provider status")
    model.redaction_policy = dict(record.redaction_policy)
    model.metadata_ = dict(record.metadata)
    model.updated_at = _record_updated_at(record)


def _oauth_provider_record(
    model: AccessOAuthProviderModel,
) -> AccessOAuthProviderRecord:
    return AccessOAuthProviderRecord(
        provider_id=model.provider_id,
        display_name=model.display_name,
        provider_kind=model.provider_kind,
        authorization_url=model.authorization_url,
        token_url=model.token_url,
        revocation_url=model.revocation_url,
        device_code_url=model.device_code_url,
        default_scopes=tuple(str(item) for item in model.default_scopes),
        client_id=model.client_id,
        client_credential_binding_id=model.client_credential_binding_id,
        callback_url=model.callback_url,
        callback_mode=model.callback_mode,
        status=model.status,
        redaction_policy=dict(model.redaction_policy),
        metadata=dict(model.metadata_),
        created_at=coerce_utc_datetime(model.created_at),
        updated_at=coerce_utc_datetime(model.updated_at),
    )


def _oauth_account_model(record: AccessOAuthAccountRecord) -> AccessOAuthAccountModel:
    return AccessOAuthAccountModel(
        account_id=_required_text(record.account_id, "OAuth account id"),
        provider_id=_required_text(record.provider_id, "OAuth account provider id"),
        credential_binding_id=_optional_text(record.credential_binding_id),
        display_name=_optional_text(record.display_name),
        subject=_optional_text(record.subject),
        granted_scopes=list(record.granted_scopes),
        expires_at=coerce_optional_utc_datetime(record.expires_at),
        refresh_ready=bool(record.refresh_ready),
        status=_required_text(record.status, "OAuth account status"),
        storage_key=_optional_text(record.storage_key),
        masked_preview=_optional_text(record.masked_preview),
        redaction_policy=dict(record.redaction_policy),
        metadata_=dict(record.metadata),
        created_at=_record_created_at(record),
        updated_at=_record_updated_at(record),
    )


def _apply_oauth_account(
    model: AccessOAuthAccountModel,
    record: AccessOAuthAccountRecord,
) -> None:
    model.provider_id = _required_text(record.provider_id, "OAuth account provider id")
    model.credential_binding_id = _optional_text(record.credential_binding_id)
    model.display_name = _optional_text(record.display_name)
    model.subject = _optional_text(record.subject)
    model.granted_scopes = list(record.granted_scopes)
    model.expires_at = coerce_optional_utc_datetime(record.expires_at)
    model.refresh_ready = bool(record.refresh_ready)
    model.status = _required_text(record.status, "OAuth account status")
    model.storage_key = _optional_text(record.storage_key)
    model.masked_preview = _optional_text(record.masked_preview)
    model.redaction_policy = dict(record.redaction_policy)
    model.metadata_ = dict(record.metadata)
    model.updated_at = _record_updated_at(record)


def _oauth_account_record(model: AccessOAuthAccountModel) -> AccessOAuthAccountRecord:
    return AccessOAuthAccountRecord(
        account_id=model.account_id,
        provider_id=model.provider_id,
        credential_binding_id=model.credential_binding_id,
        display_name=model.display_name,
        subject=model.subject,
        granted_scopes=tuple(str(item) for item in model.granted_scopes),
        expires_at=coerce_optional_utc_datetime(model.expires_at),
        refresh_ready=model.refresh_ready,
        status=model.status,
        storage_key=model.storage_key,
        masked_preview=model.masked_preview,
        redaction_policy=dict(model.redaction_policy),
        metadata=dict(model.metadata_),
        created_at=coerce_utc_datetime(model.created_at),
        updated_at=coerce_utc_datetime(model.updated_at),
    )


def _setup_session_model(record: AccessSetupSessionRecord) -> AccessSetupSessionModel:
    return AccessSetupSessionModel(
        session_id=_required_text(record.session_id, "session id"),
        target_kind=_required_text(record.target_kind, "target kind"),
        target_id=_required_text(record.target_id, "target id"),
        status=_required_text(record.status, "status"),
        flow_kind=_required_text(record.flow_kind, "flow kind"),
        requested_by=_optional_text(record.requested_by),
        expires_at=coerce_optional_utc_datetime(record.expires_at),
        completed_at=coerce_optional_utc_datetime(record.completed_at),
        redaction_policy=dict(record.redaction_policy),
        metadata_=dict(record.metadata),
        created_at=_record_created_at(record),
        updated_at=_record_updated_at(record),
    )


def _setup_session_record(model: AccessSetupSessionModel) -> AccessSetupSessionRecord:
    return AccessSetupSessionRecord(
        session_id=model.session_id,
        target_kind=model.target_kind,
        target_id=model.target_id,
        status=model.status,
        flow_kind=model.flow_kind,
        requested_by=model.requested_by,
        expires_at=coerce_optional_utc_datetime(model.expires_at),
        completed_at=coerce_optional_utc_datetime(model.completed_at),
        redaction_policy=dict(model.redaction_policy),
        metadata=dict(model.metadata_),
        created_at=coerce_utc_datetime(model.created_at),
        updated_at=coerce_utc_datetime(model.updated_at),
    )


def _readiness_snapshot_model(
    record: AccessReadinessSnapshotRecord,
) -> AccessReadinessSnapshotModel:
    return AccessReadinessSnapshotModel(
        snapshot_id=_required_text(record.snapshot_id, "snapshot id"),
        target_kind=_required_text(record.target_kind, "target kind"),
        target_id=_required_text(record.target_id, "target id"),
        status=_required_text(record.status, "status"),
        ready=bool(record.ready),
        reason=_optional_text(record.reason),
        checks=[dict(check) for check in record.checks],
        redaction_policy=dict(record.redaction_policy),
        metadata_=dict(record.metadata),
        created_at=_record_created_at(record),
    )


def _readiness_snapshot_record(
    model: AccessReadinessSnapshotModel,
) -> AccessReadinessSnapshotRecord:
    return AccessReadinessSnapshotRecord(
        snapshot_id=model.snapshot_id,
        target_kind=model.target_kind,
        target_id=model.target_id,
        status=model.status,
        ready=model.ready,
        reason=model.reason,
        checks=tuple(dict(check) for check in model.checks),
        redaction_policy=dict(model.redaction_policy),
        metadata=dict(model.metadata_),
        created_at=coerce_utc_datetime(model.created_at),
    )


def _action_audit_record(model: AccessActionAuditModel) -> AccessActionAuditRecord:
    return AccessActionAuditRecord(
        audit_id=model.audit_id,
        action_type=model.action_type,
        target_type=model.target_type,
        target_id=model.target_id,
        status=model.status,
        operator=model.operator,
        source=model.source,
        reason=model.reason,
        request_metadata=dict(model.request_metadata),
        result=dict(model.result) if model.result is not None else None,
        error=dict(model.error) if model.error is not None else None,
        redaction_policy=dict(model.redaction_policy),
        created_at=coerce_utc_datetime(model.created_at),
        updated_at=coerce_utc_datetime(model.updated_at),
    )


def _with_create_timestamps(record: object) -> dict[str, datetime]:
    created_at = _record_created_at(record)
    updated_at = getattr(record, "updated_at", None)
    return {
        "created_at": created_at,
        "updated_at": coerce_utc_datetime(updated_at) if updated_at else created_at,
    }


def _record_created_at(record: object) -> datetime:
    created_at = getattr(record, "created_at", None)
    return _coerce_or_now(created_at)


def _record_updated_at(record: object) -> datetime:
    updated_at = getattr(record, "updated_at", None)
    if updated_at is not None:
        return coerce_utc_datetime(updated_at)
    return _record_created_at(record)


def _coerce_or_now(value: datetime | None) -> datetime:
    return coerce_utc_datetime(value or datetime.now(timezone.utc))


def _required_text(value: str, label: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"access {label} cannot be blank")
    return normalized


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None
