from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from crxzipple.modules.authorization.domain import AuthorizationAuditRecord

from .audit_redaction import redact_audit_payload


def build_authorization_audit_record(
    *,
    action: str,
    status: str,
    actor_type: str | None = None,
    actor_id: str | None = None,
    target_policy_id: str | None = None,
    reason: str = "",
    before_payload: dict[str, Any] | None = None,
    after_payload: dict[str, Any] | None = None,
    decision_payload: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> AuthorizationAuditRecord:
    return AuthorizationAuditRecord(
        id=uuid4().hex,
        action=action,
        status=status,
        actor_type=(actor_type or "").strip() or None,
        actor_id=(actor_id or "").strip() or None,
        target_policy_id=(target_policy_id or "").strip() or None,
        reason=reason.strip(),
        before_payload=redact_audit_payload(before_payload or {}),
        after_payload=redact_audit_payload(after_payload or {}),
        decision_payload=redact_audit_payload(decision_payload or {}),
        metadata=redact_audit_payload(metadata or {}),
        created_at=datetime.now(timezone.utc),
    )
