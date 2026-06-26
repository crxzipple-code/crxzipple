from __future__ import annotations

from dataclasses import dataclass

from crxzipple.modules.authorization.domain import (
    AuthorizationPolicy,
    AuthorizationPolicyRepository,
)

from .agent_managed_policies import (
    agent_effect_authorization_policy_id,
    agent_tool_authorization_policy_id,
    build_agent_effect_authorization_policy,
    build_agent_tool_authorization_policy,
    ensure_local_managed_policy,
)
from .policy_lifecycle import AuthorizationPolicyLifecycle


@dataclass(slots=True)
class AgentAuthorizationGrantService:
    policy_repository: AuthorizationPolicyRepository
    policy_lifecycle: AuthorizationPolicyLifecycle

    def grant_effect_authorization(
        self,
        *,
        agent_id: str,
        effect_id: str,
        actor_type: str | None = None,
        actor_id: str | None = None,
        reason: str = "",
    ) -> AuthorizationPolicy:
        return self.policy_lifecycle.upsert_policy(
            build_agent_effect_authorization_policy(
                agent_id=agent_id,
                effect_id=effect_id,
            ),
            actor_type=actor_type,
            actor_id=actor_id,
            reason=reason,
        )

    def grant_tool_authorization(
        self,
        *,
        agent_id: str,
        tool_id: str,
        actor_type: str | None = None,
        actor_id: str | None = None,
        reason: str = "",
    ) -> AuthorizationPolicy:
        return self.policy_lifecycle.upsert_policy(
            build_agent_tool_authorization_policy(
                agent_id=agent_id,
                tool_id=tool_id,
            ),
            actor_type=actor_type,
            actor_id=actor_id,
            reason=reason,
        )

    def revoke_effect_authorization(
        self,
        *,
        agent_id: str,
        effect_id: str,
        actor_type: str | None = None,
        actor_id: str | None = None,
        reason: str = "",
    ) -> AuthorizationPolicy | None:
        return self._delete_agent_managed_policy(
            agent_effect_authorization_policy_id(
                agent_id=agent_id,
                effect_id=effect_id,
            ),
            actor_type=actor_type,
            actor_id=actor_id,
            reason=reason,
        )

    def revoke_tool_authorization(
        self,
        *,
        agent_id: str,
        tool_id: str,
        actor_type: str | None = None,
        actor_id: str | None = None,
        reason: str = "",
    ) -> AuthorizationPolicy | None:
        return self._delete_agent_managed_policy(
            agent_tool_authorization_policy_id(
                agent_id=agent_id,
                tool_id=tool_id,
            ),
            actor_type=actor_type,
            actor_id=actor_id,
            reason=reason,
        )

    def _delete_agent_managed_policy(
        self,
        policy_id: str,
        *,
        actor_type: str | None,
        actor_id: str | None,
        reason: str,
    ) -> AuthorizationPolicy | None:
        policy = self.policy_repository.get(policy_id)
        if policy is None:
            return None
        ensure_local_managed_policy(policy, policy_id)
        return self.policy_lifecycle.delete_policy(
            policy_id,
            actor_type=actor_type,
            actor_id=actor_id,
            reason=reason,
        )


__all__ = ["AgentAuthorizationGrantService"]
