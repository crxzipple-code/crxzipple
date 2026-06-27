from __future__ import annotations

from crxzipple.modules.settings.infrastructure.persistence.models import (
    SettingsActionAuditModel,
)
from crxzipple.modules.settings.infrastructure.persistence.records import (
    SettingsActionAuditRecord,
)
from crxzipple.shared.time import coerce_utc_datetime


def _action_audit_record(model: SettingsActionAuditModel) -> SettingsActionAuditRecord:
    return SettingsActionAuditRecord(
        audit_id=model.audit_id,
        action_id=model.action_id,
        action_type=model.action_type,
        target_type=model.target_type,
        target_id=model.target_id,
        resource_id=model.resource_id,
        resource_kind=model.resource_kind,
        status=model.status,
        actor=model.actor,
        source=model.source,
        reason=model.reason,
        risk=model.risk,
        confirmation=model.confirmation,
        risk_acknowledged=model.risk_acknowledged,
        request_metadata=dict(model.request_metadata),
        result=dict(model.result) if model.result is not None else None,
        error=dict(model.error) if model.error is not None else None,
        redaction_policy=dict(model.redaction_policy),
        trace_context=dict(model.trace_context),
        created_at=coerce_utc_datetime(model.created_at),
        updated_at=coerce_utc_datetime(model.updated_at),
    )
