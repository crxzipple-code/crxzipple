from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from crxzipple.modules.authorization.domain import (
    AuthorizationContext,
    AuthorizationEffect,
    AuthorizationObligation,
    AuthorizationPolicy,
    AuthorizationRequest,
    AuthorizationResource,
    AuthorizationSubject,
)

from .http_models import (
    AuthorizationAuditResponse,
    AuthorizationCheckRequest,
    AuthorizationDecisionResponse,
    AuthorizationObligationResponse,
    AuthorizationPolicyResponse,
    AuthorizationPolicyWriteRequest,
)


def authorization_request_from_payload(
    payload: AuthorizationCheckRequest,
) -> AuthorizationRequest:
    return AuthorizationRequest(
        subject=AuthorizationSubject(
            type=payload.subject.type,
            id=payload.subject.id,
            attrs=dict(payload.subject.attrs),
        ),
        action=payload.action,
        resource=AuthorizationResource(
            kind=payload.resource.kind,
            id=payload.resource.id,
            attrs=dict(payload.resource.attrs),
        ),
        context=AuthorizationContext(attrs=dict(payload.context.attrs)),
    )


def policy_from_request(payload: AuthorizationPolicyWriteRequest) -> AuthorizationPolicy:
    policy_id = payload.id.strip()
    if not policy_id:
        raise HTTPException(status_code=400, detail="Policy id cannot be empty.")
    actions = tuple(
        dict.fromkeys(
            action.strip()
            for action in payload.actions
            if action.strip()
        ),
    )
    if not actions:
        raise HTTPException(status_code=400, detail="Policy actions cannot be empty.")
    try:
        effect = AuthorizationEffect(payload.effect.strip().lower())
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported authorization effect '{payload.effect}'.",
        ) from exc
    return AuthorizationPolicy(
        id=policy_id,
        description=payload.description.strip(),
        effect=effect,
        actions=actions,
        subject_type=(payload.subject_type or "").strip() or None,
        subject_id=(payload.subject_id or "").strip() or None,
        subject_match=dict(payload.subject_match),
        resource_kind=(payload.resource_kind or "").strip() or None,
        resource_id=(payload.resource_id or "").strip() or None,
        resource_match=dict(payload.resource_match),
        context_match=dict(payload.context_match),
        condition=dict(payload.condition) if payload.condition is not None else None,
        obligations=tuple(
            AuthorizationObligation(name=item.name, params=dict(item.params))
            for item in payload.obligations
        ),
        priority=payload.priority,
        enabled=payload.enabled,
        source_kind=payload.source_kind.strip() or "local_managed",
    )


def to_decision_response(decision: Any) -> AuthorizationDecisionResponse:
    return AuthorizationDecisionResponse(
        allowed=decision.allowed,
        reason=decision.reason,
        code=decision.code.value,
        matched_policy_ids=list(decision.matched_policy_ids),
        obligations=[
            AuthorizationObligationResponse(name=item.name, params=dict(item.params))
            for item in decision.obligations
        ],
        details=dict(decision.details),
    )


def to_policy_response(policy: Any) -> AuthorizationPolicyResponse:
    return AuthorizationPolicyResponse(
        id=policy.id,
        description=policy.description,
        effect=policy.effect.value,
        actions=list(policy.actions),
        subject_type=policy.subject_type,
        subject_id=policy.subject_id,
        subject_match=dict(policy.subject_match),
        resource_kind=policy.resource_kind,
        resource_id=policy.resource_id,
        resource_match=dict(policy.resource_match),
        context_match=dict(policy.context_match),
        condition=dict(policy.condition) if policy.condition is not None else None,
        obligations=[
            AuthorizationObligationResponse(name=item.name, params=dict(item.params))
            for item in policy.obligations
        ],
        priority=policy.priority,
        enabled=policy.enabled,
        source_kind=policy.source_kind,
    )


def to_audit_response(record: Any) -> AuthorizationAuditResponse:
    return AuthorizationAuditResponse(
        id=record.id,
        action=record.action,
        status=record.status,
        actor_type=record.actor_type,
        actor_id=record.actor_id,
        target_policy_id=record.target_policy_id,
        reason=record.reason,
        before_payload=dict(record.before_payload),
        after_payload=dict(record.after_payload),
        decision_payload=dict(record.decision_payload),
        metadata=dict(record.metadata),
        created_at=record.created_at.isoformat(),
    )


def agent_grant_policy_id(
    *,
    agent_id: str,
    kind: str,
    target_id: str,
) -> str:
    def _clean(value: str) -> str:
        return "".join(char if char.isalnum() else "_" for char in value)

    if kind == "effect":
        return f"local_allow_agent_effect__{_clean(agent_id)}__{_clean(target_id)}"
    return f"local_allow_agent_tool__{_clean(agent_id)}__{_clean(target_id)}"


__all__ = [
    "agent_grant_policy_id",
    "authorization_request_from_payload",
    "policy_from_request",
    "to_audit_response",
    "to_decision_response",
    "to_policy_response",
]
