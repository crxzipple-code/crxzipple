from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class OperationsActionAudit:
    audit_id: str
    action_type: str
    target_type: str
    target_id: str | None
    target: dict[str, Any]
    reason: str
    dangerous: bool
    risk: str
    confirmation: bool
    risk_acknowledged: bool
    operator: str | None
    source: str
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    status: str
    result: dict[str, Any] | None
    error: dict[str, Any] | None


class OperationsActionAuditStore(Protocol):
    def record_attempt(
        self,
        *,
        action_type: str,
        target_type: str,
        target_id: str | None,
        target: dict[str, Any],
        reason: str,
        dangerous: bool,
        risk: str,
        confirmation: bool,
        risk_acknowledged: bool,
        operator: str | None,
        source: str,
        metadata: dict[str, Any],
        created_at: datetime | None = None,
    ) -> OperationsActionAudit:
        ...

    def mark_succeeded(
        self,
        audit_id: str,
        *,
        result: dict[str, Any] | None = None,
        updated_at: datetime | None = None,
    ) -> OperationsActionAudit:
        ...

    def mark_failed(
        self,
        audit_id: str,
        *,
        error: dict[str, Any],
        updated_at: datetime | None = None,
    ) -> OperationsActionAudit:
        ...

    def list_recent(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[OperationsActionAudit, ...]:
        ...
