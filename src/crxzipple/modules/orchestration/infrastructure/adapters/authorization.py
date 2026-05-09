from __future__ import annotations

from dataclasses import dataclass

from crxzipple.modules.authorization.application import AuthorizationApplicationService
from crxzipple.modules.orchestration.application.ports import AuthorizationPort


@dataclass(slots=True)
class AuthorizationServiceAdapter(AuthorizationPort):
    service: AuthorizationApplicationService

    def is_enabled(self) -> bool:
        return self.service.is_enabled()

    def check(self, request):
        return self.service.check(request)

    def check_tool_execution(self, request):
        return self.service.check_tool_execution(request)

    def grant_run_authorization(
        self,
        *,
        run_id: str,
        agent_id: str | None,
        approval_request_id: str | None,
        effect_ids: tuple[str, ...],
        tool_ids: tuple[str, ...],
    ):
        return self.service.grant_run_authorization(
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
    ):
        return self.service.grant_session_authorization(
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
    ):
        return self.service.grant_agent_effect_authorization(
            agent_id=agent_id,
            effect_id=effect_id,
        )

    def grant_agent_tool_authorization(
        self,
        *,
        agent_id: str,
        tool_id: str,
    ):
        return self.service.grant_agent_tool_authorization(
            agent_id=agent_id,
            tool_id=tool_id,
        )
