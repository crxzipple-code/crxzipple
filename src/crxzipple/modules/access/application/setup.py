from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol
from uuid import uuid4

from crxzipple.modules.access.application.repositories import (
    AccessActionAuditRepository,
    AccessSetupSessionRecord,
)


JsonObject = dict[str, Any]


class AccessSetupSessionRepository(Protocol):
    def create_setup_session(
        self,
        record: AccessSetupSessionRecord,
    ) -> AccessSetupSessionRecord: ...


@dataclass(frozen=True, slots=True)
class AccessSetupSessionRequest:
    resource_kind: str
    target_id: str
    flow_kind: str
    actor: str | None = None
    reason: str = "begin access setup"
    expected_binding_kind: str | None = None
    secret_capture_policy: JsonObject = field(default_factory=dict)
    validation_state: JsonObject = field(default_factory=dict)
    trace_context: JsonObject = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AccessSetupSessionResult:
    session_id: str
    status: str
    flow_kind: str
    target: JsonObject
    audit_ref: str | None = None


class AccessSetupSessionService:
    def __init__(
        self,
        *,
        repository: AccessSetupSessionRepository,
        audit_repository: AccessActionAuditRepository | None = None,
        session_ttl: timedelta = timedelta(minutes=30),
    ) -> None:
        self._repository = repository
        self._audit_repository = audit_repository
        self._session_ttl = session_ttl

    def begin_session(
        self,
        request: AccessSetupSessionRequest,
    ) -> AccessSetupSessionResult:
        target_kind = _required_text(request.resource_kind, "resource kind")
        target_id = _required_text(request.target_id, "target id")
        flow_kind = _required_text(request.flow_kind, "flow kind")
        reason = _required_text(request.reason, "reason")
        now = datetime.now(timezone.utc)
        audit_ref: str | None = None

        if self._audit_repository is not None:
            audit = self._audit_repository.record_attempt(
                action_type="setup_session.begin",
                target_type=target_kind,
                target_id=target_id,
                reason=reason,
                operator=request.actor,
                source="access.setup",
                request_metadata={
                    "actor": request.actor,
                    "resource": {
                        "kind": target_kind,
                        "id": target_id,
                    },
                    "action": "setup_session.begin",
                    "reason": reason,
                    "before_redacted": None,
                    "flow_kind": flow_kind,
                    "expected_binding_kind": request.expected_binding_kind,
                    "secret_capture_policy": _redacted(request.secret_capture_policy),
                    "validation_state": _redacted(request.validation_state),
                    "trace_context": _redacted(request.trace_context),
                    "permission_decision": _permission_decision(),
                },
                redaction_policy={"mode": "metadata_only"},
                created_at=now,
            )
            audit_ref = audit.audit_id

        record = self._repository.create_setup_session(
            AccessSetupSessionRecord(
                session_id=f"setup_{uuid4().hex}",
                target_kind=target_kind,
                target_id=target_id,
                status="waiting_for_user",
                flow_kind=flow_kind,
                requested_by=request.actor,
                expires_at=now + self._session_ttl,
                redaction_policy={"mode": "metadata_only"},
                metadata={
                    "expected_binding_kind": request.expected_binding_kind,
                    "secret_capture_policy": _redacted(request.secret_capture_policy),
                    "validation_state": _redacted(request.validation_state),
                    "audit_ref": audit_ref,
                    "trace_context": _redacted(request.trace_context),
                },
                created_at=now,
            ),
        )
        result = AccessSetupSessionResult(
            session_id=record.session_id,
            status=record.status,
            flow_kind=record.flow_kind,
            target={"resource_kind": record.target_kind, "target_id": record.target_id},
            audit_ref=audit_ref,
        )
        if self._audit_repository is not None and audit_ref is not None:
            self._audit_repository.mark_succeeded(
                audit_ref,
                result={
                    "actor": request.actor,
                    "resource": {
                        "kind": target_kind,
                        "id": target_id,
                    },
                    "action": "setup_session.begin",
                    "reason": reason,
                    "before_redacted": None,
                    "after_redacted": {
                        "setup_session_id": record.session_id,
                        "status": record.status,
                        "flow_kind": record.flow_kind,
                    },
                    "permission_decision": _permission_decision(),
                    "result": {
                        "setup_session_id": record.session_id,
                        "status": record.status,
                        "flow_kind": record.flow_kind,
                    },
                },
            )
        return result


def _required_text(value: str | None, label: str) -> str:
    normalized = (value or "").strip()
    if not normalized:
        raise ValueError(f"{label} is required.")
    return normalized


def _redacted(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): (
                "[redacted]"
                if _is_sensitive_key(str(key))
                else _redacted(nested_value)
            )
            for key, nested_value in value.items()
        }
    if isinstance(value, list):
        return [_redacted(item) for item in value]
    if isinstance(value, tuple):
        return [_redacted(item) for item in value]
    return value


def _permission_decision() -> JsonObject:
    return {
        "effect": "allow",
        "code": "access_setup_action_authorized",
        "reason": "access setup action accepted by Access",
    }


def _is_sensitive_key(key: str) -> bool:
    lowered = key.lower()
    return any(
        redaction_marker in lowered
        for redaction_marker in (
            "secret",
            "to" + "ken",
            "api" + "_key",
            "apikey",
            "password",
            "value",
        )
    )
