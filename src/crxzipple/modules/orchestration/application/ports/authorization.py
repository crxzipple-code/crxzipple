from __future__ import annotations

from typing import Protocol

from crxzipple.modules.authorization.domain import (
    AuthorizationDecision,
    AuthorizationPolicy,
    AuthorizationRequest,
    TemporaryAuthorizationGrant,
    ToolExecutionAuthorizationRequest,
)


class AuthorizationPort(Protocol):
    def is_enabled(self) -> bool:
        ...

    def check(self, request: AuthorizationRequest) -> AuthorizationDecision:
        ...

    def check_tool_execution(
        self,
        request: ToolExecutionAuthorizationRequest,
    ) -> AuthorizationDecision:
        ...

    def grant_run_access(
        self,
        *,
        run_id: str,
        agent_id: str | None,
        approval_request_id: str | None,
        effect_ids: tuple[str, ...],
        tool_ids: tuple[str, ...],
    ) -> TemporaryAuthorizationGrant:
        ...

    def grant_session_access(
        self,
        *,
        session_key: str,
        agent_id: str | None,
        approval_request_id: str | None,
        effect_ids: tuple[str, ...],
        tool_ids: tuple[str, ...],
    ) -> TemporaryAuthorizationGrant:
        ...

    def grant_agent_effect_access(
        self,
        *,
        agent_id: str,
        effect_id: str,
    ) -> AuthorizationPolicy:
        ...
