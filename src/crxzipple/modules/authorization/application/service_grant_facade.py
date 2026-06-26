from __future__ import annotations

from crxzipple.modules.authorization.domain import (
    AuthorizationPolicy,
    TemporaryAuthorizationGrant,
)


class AuthorizationGrantFacadeMixin:
    def grant_run_authorization(
        self,
        *,
        run_id: str,
        agent_id: str | None,
        approval_request_id: str | None,
        effect_ids: tuple[str, ...],
        tool_ids: tuple[str, ...],
    ) -> TemporaryAuthorizationGrant:
        return self._temporary_grants().grant_run_authorization(
            run_id=run_id,
            agent_id=agent_id,
            approval_request_id=approval_request_id,
            effect_ids=effect_ids,
            tool_ids=tool_ids,
        )

    def grant_session_authorization(
        self,
        *,
        session_key: str,
        agent_id: str | None,
        approval_request_id: str | None,
        effect_ids: tuple[str, ...],
        tool_ids: tuple[str, ...],
    ) -> TemporaryAuthorizationGrant:
        return self._temporary_grants().grant_session_authorization(
            session_key=session_key,
            agent_id=agent_id,
            approval_request_id=approval_request_id,
            effect_ids=effect_ids,
            tool_ids=tool_ids,
        )

    def grant_agent_effect_authorization(
        self,
        *,
        agent_id: str,
        effect_id: str,
        actor_type: str | None = None,
        actor_id: str | None = None,
        reason: str = "",
    ) -> AuthorizationPolicy:
        return self._agent_grants().grant_effect_authorization(
            agent_id=agent_id,
            effect_id=effect_id,
            actor_type=actor_type,
            actor_id=actor_id,
            reason=reason,
        )

    def grant_agent_tool_authorization(
        self,
        *,
        agent_id: str,
        tool_id: str,
        actor_type: str | None = None,
        actor_id: str | None = None,
        reason: str = "",
    ) -> AuthorizationPolicy:
        return self._agent_grants().grant_tool_authorization(
            agent_id=agent_id,
            tool_id=tool_id,
            actor_type=actor_type,
            actor_id=actor_id,
            reason=reason,
        )

    def revoke_agent_effect_authorization(
        self,
        *,
        agent_id: str,
        effect_id: str,
        actor_type: str | None = None,
        actor_id: str | None = None,
        reason: str = "",
    ) -> AuthorizationPolicy | None:
        return self._agent_grants().revoke_effect_authorization(
            agent_id=agent_id,
            effect_id=effect_id,
            actor_type=actor_type,
            actor_id=actor_id,
            reason=reason,
        )

    def revoke_agent_tool_authorization(
        self,
        *,
        agent_id: str,
        tool_id: str,
        actor_type: str | None = None,
        actor_id: str | None = None,
        reason: str = "",
    ) -> AuthorizationPolicy | None:
        return self._agent_grants().revoke_tool_authorization(
            agent_id=agent_id,
            tool_id=tool_id,
            actor_type=actor_type,
            actor_id=actor_id,
            reason=reason,
        )
