from __future__ import annotations

from typing import Protocol

from crxzipple.modules.authorization.domain import (
    AuthorizationDecision,
    AuthorizationRequest,
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

    def grant_run_authorization(
        self,
        *,
        run_id: str,
        agent_id: str | None,
        approval_request_id: str | None,
        effect_ids: tuple[str, ...],
        tool_ids: tuple[str, ...],
    ) -> None:
        ...

    def grant_session_authorization(
        self,
        *,
        session_key: str,
        agent_id: str | None,
        approval_request_id: str | None,
        effect_ids: tuple[str, ...],
        tool_ids: tuple[str, ...],
    ) -> None:
        ...

    def grant_agent_effect_authorization(
        self,
        *,
        agent_id: str,
        effect_id: str,
    ) -> None:
        ...

    def grant_agent_tool_authorization(
        self,
        *,
        agent_id: str,
        tool_id: str,
    ) -> None:
        ...
