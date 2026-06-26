from __future__ import annotations

from typing import Any

from crxzipple.modules.agent.application.resolution_authorization import (
    authorization_grant_from_policy,
)
from crxzipple.modules.agent.application.resolution_models import (
    AgentAuthorizationGrant,
    AgentResolutionTrace,
)


def resolve_authorization_grants(
    profile_id: str,
    *,
    authorization_policies: Any | None,
    trace: list[AgentResolutionTrace],
) -> list[AgentAuthorizationGrant]:
    if authorization_policies is None:
        trace.append(
            AgentResolutionTrace(
                source="authorization",
                status="unavailable",
                detail="Authorization policy query port is not configured",
            ),
        )
        return []

    try:
        policies = authorization_policies.list_policies()
    except Exception as exc:  # pragma: no cover - defensive partial stack guard
        trace.append(
            AgentResolutionTrace(
                source="authorization",
                status="error",
                detail=str(exc),
            ),
        )
        return []

    grants = [
        grant
        for policy in policies
        if (grant := authorization_grant_from_policy(policy, profile_id)) is not None
    ]
    trace.append(
        AgentResolutionTrace(
            source="authorization",
            status="resolved",
            detail=f"{len(grants)} agent authorization policies matched",
        ),
    )
    return grants


__all__ = ["resolve_authorization_grants"]
