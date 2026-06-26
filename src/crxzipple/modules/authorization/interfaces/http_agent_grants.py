from __future__ import annotations

from fastapi import HTTPException

from crxzipple.modules.authorization.application import AuthorizationApplicationService

from .http_models import (
    AuthorizationAgentGrantRequest,
    AuthorizationAgentGrantResponse,
)
from .http_payloads import (
    agent_grant_policy_id,
    to_policy_response,
)


def grant_agent_authorization_response(
    payload: AuthorizationAgentGrantRequest,
    service: AuthorizationApplicationService,
) -> AuthorizationAgentGrantResponse:
    agent_id, target_id = _validated_agent_grant_ids(payload)
    try:
        if payload.kind == "effect":
            policy = service.grant_agent_effect_authorization(
                agent_id=agent_id,
                effect_id=target_id,
                actor_type=payload.actor.type,
                actor_id=payload.actor.id,
                reason=payload.reason,
            )
        else:
            policy = service.grant_agent_tool_authorization(
                agent_id=agent_id,
                tool_id=target_id,
                actor_type=payload.actor.type,
                actor_id=payload.actor.id,
                reason=payload.reason,
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AuthorizationAgentGrantResponse(
        agent_id=agent_id,
        kind=payload.kind,
        id=target_id,
        policy_id=policy.id,
        status="enabled",
        policy=to_policy_response(policy),
    )


def revoke_agent_authorization_response(
    payload: AuthorizationAgentGrantRequest,
    service: AuthorizationApplicationService,
) -> AuthorizationAgentGrantResponse:
    agent_id, target_id = _validated_agent_grant_ids(payload)
    try:
        if payload.kind == "effect":
            policy = service.revoke_agent_effect_authorization(
                agent_id=agent_id,
                effect_id=target_id,
                actor_type=payload.actor.type,
                actor_id=payload.actor.id,
                reason=payload.reason,
            )
        else:
            policy = service.revoke_agent_tool_authorization(
                agent_id=agent_id,
                tool_id=target_id,
                actor_type=payload.actor.type,
                actor_id=payload.actor.id,
                reason=payload.reason,
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    policy_id = (
        policy.id
        if policy is not None
        else agent_grant_policy_id(
            agent_id=agent_id,
            kind=payload.kind,
            target_id=target_id,
        )
    )
    return AuthorizationAgentGrantResponse(
        agent_id=agent_id,
        kind=payload.kind,
        id=target_id,
        policy_id=policy_id,
        status="revoked" if policy is not None else "not_found",
        policy=to_policy_response(policy) if policy is not None else None,
    )


def _validated_agent_grant_ids(
    payload: AuthorizationAgentGrantRequest,
) -> tuple[str, str]:
    agent_id = payload.agent_id.strip()
    target_id = payload.id.strip()
    if not agent_id:
        raise HTTPException(status_code=400, detail="agent_id cannot be empty.")
    if not target_id:
        raise HTTPException(status_code=400, detail="id cannot be empty.")
    return agent_id, target_id


__all__ = [
    "grant_agent_authorization_response",
    "revoke_agent_authorization_response",
]
