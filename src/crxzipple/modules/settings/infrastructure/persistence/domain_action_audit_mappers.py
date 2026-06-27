from __future__ import annotations

from uuid import uuid4

from crxzipple.modules.settings.domain.entities import SettingsActionAudit
from crxzipple.modules.settings.infrastructure.persistence.models import (
    SettingsActionAuditModel,
)
from crxzipple.modules.settings.infrastructure.persistence.records import (
    SettingsActionAuditRecord,
)
from crxzipple.modules.settings.infrastructure.persistence.redaction import (
    redacted_json_object,
)


def audit_model_from_domain(audit: SettingsActionAudit) -> SettingsActionAuditModel:
    return SettingsActionAuditModel(
        audit_id=audit.id,
        action_id=None,
        action_type=audit.action_type,
        target_type=audit.target_type,
        target_id=audit.target_id,
        resource_id=audit.target_id,
        resource_kind=audit.target_type,
        status=audit.status.value,
        actor=audit.actor,
        source="settings.application",
        reason=audit.reason,
        risk=audit.risk or "normal",
        confirmation=False,
        risk_acknowledged=False,
        request_metadata=redacted_json_object(dict(audit.request_metadata)) or {},
        result=(
            redacted_json_object(dict(audit.result))
            if audit.result is not None
            else None
        ),
        error=(
            redacted_json_object(dict(audit.error))
            if audit.error is not None
            else None
        ),
        redaction_policy=dict(audit.redaction_policy),
        trace_context={},
        created_at=audit.created_at,
        updated_at=audit.updated_at or audit.created_at,
    )


def audit_from_record(record: SettingsActionAuditRecord) -> SettingsActionAudit:
    return SettingsActionAudit(
        id=record.audit_id,
        action_type=record.action_type,
        target_type=record.target_type,
        target_id=record.target_id,
        reason=record.reason,
        status=record.status,
        actor=record.actor,
        risk=record.risk,
        request_metadata=record.request_metadata,
        result=record.result,
        error=record.error,
        created_at=record.created_at,
        updated_at=record.updated_at,
        redaction_policy=record.redaction_policy,
    )


def apply_audit_model(
    model: SettingsActionAuditModel,
    stored: SettingsActionAuditModel,
) -> None:
    model.action_type = stored.action_type
    model.target_type = stored.target_type
    model.target_id = stored.target_id
    model.resource_id = stored.resource_id
    model.resource_kind = stored.resource_kind
    model.status = stored.status
    model.actor = stored.actor
    model.source = stored.source
    model.reason = stored.reason
    model.risk = stored.risk
    model.request_metadata = stored.request_metadata
    model.result = stored.result
    model.error = stored.error
    model.redaction_policy = stored.redaction_policy
    model.trace_context = stored.trace_context
    model.created_at = stored.created_at
    model.updated_at = stored.updated_at


def uuid_hex() -> str:
    return uuid4().hex


__all__ = [
    "apply_audit_model",
    "audit_from_record",
    "audit_model_from_domain",
    "uuid_hex",
]
