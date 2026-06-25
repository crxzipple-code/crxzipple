from __future__ import annotations

from datetime import datetime

from crxzipple.modules.access.application.read_models import (
    AccessAuditReadModel,
    AccessConsumerBindingReadModel,
    AccessOAuthAccountReadModel,
    AccessOAuthProviderReadModel,
    AccessReadinessReadModel,
    AccessSetupSessionReadModel,
    CredentialBindingReadModel,
)
from crxzipple.modules.access.application.repositories import (
    AccessActionAuditRecord,
    AccessConsumerBindingRecord,
    AccessCredentialBindingRecord,
    AccessOAuthAccountRecord,
    AccessOAuthProviderRecord,
    AccessReadinessSnapshotRecord,
    AccessSetupSessionRecord,
)


def credential_binding_model(
    record: AccessCredentialBindingRecord,
) -> CredentialBindingReadModel:
    return CredentialBindingReadModel(
        binding_id=record.binding_id,
        binding_kind=record.binding_kind,
        source_kind=record.source_kind,
        source_ref=record.source_ref,
        asset_id=record.asset_id,
        masked_preview=record.masked_preview,
        status=record.status,
        metadata=record.metadata,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def consumer_binding_model(
    record: AccessConsumerBindingRecord,
) -> AccessConsumerBindingReadModel:
    return AccessConsumerBindingReadModel(
        binding_id=record.binding_id,
        consumer_module=record.consumer_module,
        consumer_kind=record.consumer_kind,
        consumer_id=record.consumer_id,
        display_name=record.display_name,
        enabled=record.enabled,
        asset_id=record.asset_id,
        credential_binding_id=record.credential_binding_id,
        credential_bindings=record.credential_bindings,
        requirement_sets=record.requirement_sets,
        status=record.status,
        metadata=record.metadata,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def merge_consumer_binding_models(
    settings_consumers: tuple[AccessConsumerBindingReadModel, ...],
    external_consumers: tuple[AccessConsumerBindingReadModel, ...],
) -> tuple[AccessConsumerBindingReadModel, ...]:
    merged: dict[tuple[str, str], AccessConsumerBindingReadModel] = {}
    order: list[tuple[str, str]] = []
    for consumer in external_consumers:
        key = _consumer_merge_key(consumer)
        if key not in merged:
            order.append(key)
        merged[key] = consumer
    for consumer in settings_consumers:
        key = _consumer_merge_key(consumer)
        if key not in merged:
            order.append(key)
            merged[key] = consumer
            continue
        merged[key] = _overlay_settings_consumer_binding(
            owner=merged[key],
            settings=consumer,
        )
    return tuple(merged[key] for key in order)


def readiness_model(record: AccessReadinessSnapshotRecord) -> AccessReadinessReadModel:
    return AccessReadinessReadModel(
        target_kind=record.target_kind,
        target_id=record.target_id,
        status=record.status,
        ready=record.ready,
        reason=record.reason,
        checks=record.checks,
        setup_available=record.status != "ready",
        metadata=record.metadata,
        observed_at=record.created_at,
    )


def setup_session_model(
    record: AccessSetupSessionRecord,
    *,
    now: datetime | None = None,
) -> AccessSetupSessionReadModel:
    status = record.status
    if (
        status == "waiting_for_user"
        and record.expires_at is not None
        and now is not None
        and record.expires_at <= now
    ):
        status = "expired"
    return AccessSetupSessionReadModel(
        session_id=record.session_id,
        target_kind=record.target_kind,
        target_id=record.target_id,
        status=status,
        flow_kind=record.flow_kind,
        requested_by=record.requested_by,
        expires_at=record.expires_at,
        completed_at=record.completed_at,
        metadata=record.metadata,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def oauth_provider_model(record: AccessOAuthProviderRecord) -> AccessOAuthProviderReadModel:
    return AccessOAuthProviderReadModel(
        provider_id=record.provider_id,
        display_name=record.display_name,
        provider_kind=record.provider_kind,
        status=record.status,
        default_scopes=record.default_scopes,
        authorization_url=record.authorization_url,
        token_url=record.token_url,
        revocation_url=record.revocation_url,
        device_code_url=record.device_code_url,
        callback_url=record.callback_url,
        callback_mode=record.callback_mode,
        metadata=record.metadata,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def oauth_account_model(record: AccessOAuthAccountRecord) -> AccessOAuthAccountReadModel:
    return AccessOAuthAccountReadModel(
        account_id=record.account_id,
        provider_id=record.provider_id,
        credential_binding_id=record.credential_binding_id,
        display_name=record.display_name,
        subject=record.subject,
        granted_scopes=record.granted_scopes,
        expires_at=record.expires_at,
        refresh_ready=record.refresh_ready,
        status=record.status,
        masked_preview=record.masked_preview,
        metadata=record.metadata,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def audit_model(record: AccessActionAuditRecord) -> AccessAuditReadModel:
    return AccessAuditReadModel(
        audit_id=record.audit_id,
        action_type=record.action_type,
        target_type=record.target_type,
        target_id=record.target_id,
        status=record.status,
        operator=record.operator,
        source=record.source,
        reason=record.reason,
        request_metadata=record.request_metadata,
        result=record.result,
        error=record.error,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def settings_audit_model(record: object) -> AccessAuditReadModel:
    status = getattr(record, "status", "")
    return AccessAuditReadModel(
        audit_id=str(getattr(record, "id", "")),
        action_type=str(getattr(record, "action_type", "")),
        target_type=str(getattr(record, "target_type", "")),
        target_id=getattr(record, "target_id", None),
        status=str(getattr(status, "value", status)),
        operator=getattr(record, "actor", None),
        source="settings.access_config",
        reason=str(getattr(record, "reason", "")),
        request_metadata=dict(getattr(record, "request_metadata", {}) or {}),
        result=(
            dict(getattr(record, "result", {}) or {})
            if getattr(record, "result", None) is not None
            else None
        ),
        error=(
            dict(getattr(record, "error", {}) or {})
            if getattr(record, "error", None) is not None
            else None
        ),
        created_at=getattr(record, "created_at", None),
        updated_at=getattr(record, "updated_at", None),
    )


def _consumer_merge_key(
    consumer: AccessConsumerBindingReadModel,
) -> tuple[str, str]:
    return (
        consumer.consumer_module.strip().lower(),
        consumer.consumer_id.strip(),
    )


def _overlay_settings_consumer_binding(
    *,
    owner: AccessConsumerBindingReadModel,
    settings: AccessConsumerBindingReadModel,
) -> AccessConsumerBindingReadModel:
    metadata = {
        **dict(owner.metadata),
        "settings_binding_id": settings.binding_id,
        "owner_binding_id": owner.binding_id,
        **dict(settings.metadata),
    }
    return AccessConsumerBindingReadModel(
        binding_id=settings.binding_id,
        consumer_module=owner.consumer_module or settings.consumer_module,
        consumer_kind=owner.consumer_kind or settings.consumer_kind,
        consumer_id=owner.consumer_id or settings.consumer_id,
        display_name=settings.display_name or owner.display_name,
        enabled=owner.enabled and settings.enabled,
        asset_id=settings.asset_id or owner.asset_id,
        credential_binding_id=(
            settings.credential_binding_id or owner.credential_binding_id
        ),
        credential_bindings={
            **dict(owner.credential_bindings),
            **dict(settings.credential_bindings),
        },
        requirement_sets=owner.requirement_sets or settings.requirement_sets,
        status=_merged_consumer_status(owner.status, settings.status),
        metadata=metadata,
        created_at=settings.created_at or owner.created_at,
        updated_at=settings.updated_at or owner.updated_at,
    )


def _merged_consumer_status(owner_status: str, settings_status: str) -> str:
    owner = owner_status.strip().lower()
    settings = settings_status.strip().lower()
    if owner != "active":
        return owner or "disabled"
    if settings != "active":
        return settings or "disabled"
    return "active"
