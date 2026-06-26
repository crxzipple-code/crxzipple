from __future__ import annotations

from typing import Any

from crxzipple.modules.authorization.application.audit_redaction import (
    is_sensitive_audit_key,
    redact_audit_payload,
    redact_audit_value,
)
from crxzipple.modules.authorization.domain import (
    AuthorizationDecision,
    AuthorizationPolicy,
    AuthorizationRequest,
    TemporaryAuthorizationGrant,
)

def policy_payload(policy: AuthorizationPolicy) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": policy.id,
        "description": policy.description,
        "effect": policy.effect.value,
        "actions": list(policy.actions),
        "priority": policy.priority,
        "enabled": policy.enabled,
        "source_kind": policy.source_kind,
    }
    subject: dict[str, Any] = {}
    if policy.subject_type is not None:
        subject["type"] = policy.subject_type
    if policy.subject_id is not None:
        subject["id"] = policy.subject_id
    if policy.subject_match:
        subject["match"] = dict(policy.subject_match)
    if subject:
        payload["subject"] = subject

    resource: dict[str, Any] = {}
    if policy.resource_kind is not None:
        resource["kind"] = policy.resource_kind
    if policy.resource_id is not None:
        resource["id"] = policy.resource_id
    if policy.resource_match:
        resource["match"] = dict(policy.resource_match)
    if resource:
        payload["resource"] = resource

    if policy.context_match:
        payload["context"] = {"match": dict(policy.context_match)}
    if policy.condition is not None:
        payload["condition"] = dict(policy.condition)
    if policy.obligations:
        payload["obligations"] = [
            (
                {"name": obligation.name, "params": dict(obligation.params)}
                if obligation.params
                else obligation.name
            )
            for obligation in policy.obligations
        ]
    return payload


def decision_payload(decision: AuthorizationDecision) -> dict[str, Any]:
    return {
        "allowed": decision.allowed,
        "reason": decision.reason,
        "code": decision.code.value,
        "matched_policy_ids": list(decision.matched_policy_ids),
        "obligations": [
            {"name": obligation.name, "params": dict(obligation.params)}
            for obligation in decision.obligations
        ],
        "details": dict(decision.details),
    }


def request_payload(request: AuthorizationRequest) -> dict[str, Any]:
    return {
        "subject": {
            "type": request.subject.type,
            "id": request.subject.id,
            "attrs": dict(request.subject.attrs),
        },
        "action": request.action,
        "resource": {
            "kind": request.resource.kind,
            "id": request.resource.id,
            "attrs": dict(request.resource.attrs),
        },
        "context": {"attrs": dict(request.context.attrs)},
    }


def grant_payload(grant: TemporaryAuthorizationGrant) -> dict[str, Any]:
    return {
        "id": grant.id,
        "scope": grant.scope.value,
        "run_id": grant.run_id,
        "session_key": grant.session_key,
        "agent_id": grant.agent_id,
        "approval_request_id": grant.approval_request_id,
        "effect_ids": list(grant.effect_ids),
        "tool_ids": list(grant.tool_ids),
        "created_at": grant.created_at.isoformat(),
    }


__all__ = [
    "decision_payload",
    "grant_payload",
    "is_sensitive_audit_key",
    "policy_payload",
    "redact_audit_payload",
    "redact_audit_value",
    "request_payload",
]
