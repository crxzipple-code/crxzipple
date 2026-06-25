from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from crxzipple.shared.time import format_datetime_utc


class OperationsActionAuditResponse(BaseModel):
    audit_id: str
    audit_event: str
    action_type: str
    target_type: str
    target_id: str | None = None
    target: dict[str, Any]
    reason: str
    dangerous: bool
    risk: str
    confirmation: bool
    risk_acknowledged: bool
    operator: str | None = None
    source: str
    metadata: dict[str, Any]
    created_at: str
    updated_at: str
    status: str
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None

    @classmethod
    def from_value(cls, value: Any) -> "OperationsActionAuditResponse":
        return cls(
            audit_id=value.audit_id,
            audit_event=value.action_type,
            action_type=value.action_type,
            target_type=value.target_type,
            target_id=value.target_id,
            target=dict(value.target),
            reason=value.reason,
            dangerous=value.dangerous,
            risk=value.risk,
            confirmation=value.confirmation,
            risk_acknowledged=value.risk_acknowledged,
            operator=value.operator,
            source=value.source,
            metadata=dict(value.metadata),
            created_at=format_datetime_utc(value.created_at),
            updated_at=format_datetime_utc(value.updated_at),
            status=value.status,
            result=dict(value.result) if value.result is not None else None,
            error=dict(value.error) if value.error is not None else None,
        )
