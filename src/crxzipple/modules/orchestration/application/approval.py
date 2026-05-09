"""Approval application services for orchestration waits."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from crxzipple.modules.orchestration.application.ports import AuthorizationPort
from crxzipple.modules.orchestration.application.commands import (
    ResolveApprovalRequestInput,
)
from crxzipple.modules.orchestration.domain.entities import OrchestrationRun
from crxzipple.modules.orchestration.domain.exceptions import (
    OrchestrationValidationError,
)
from crxzipple.modules.orchestration.domain.value_objects import (
    ApprovalDecision,
    PendingApprovalRequest,
)
from crxzipple.modules.session.application import (
    AppendSessionMessageInput,
    SessionApplicationService,
)
from crxzipple.modules.session.domain import SessionMessageKind


@dataclass(slots=True)
class ApprovalControlService:
    """External approval-resolution entrypoint for waiting orchestration runs."""

    resolve_approval_request_fn: Callable[
        [ResolveApprovalRequestInput],
        OrchestrationRun,
    ]

    def resolve_approval_request(
        self,
        data: ResolveApprovalRequestInput,
    ) -> OrchestrationRun:
        return self.resolve_approval_request_fn(data)


@dataclass(slots=True)
class ApprovalResolutionService:
    """Authorization and transcript side effects for approval decisions."""

    authorization_port: AuthorizationPort | None
    session_service: SessionApplicationService | None
    get_run: Callable[[str], OrchestrationRun]

    def grant_run_tool_authorization(
        self,
        *,
        run_id: str,
        approval_request_id: str | None,
        effect_ids: tuple[str, ...],
        tool_ids: tuple[str, ...],
    ) -> None:
        if self.authorization_port is None:
            raise RuntimeError("Authorization service is not configured.")
        run = self.get_run(run_id)
        self.authorization_port.grant_run_authorization(
            run_id=run.id,
            agent_id=run.agent_id,
            approval_request_id=approval_request_id,
            effect_ids=effect_ids,
            tool_ids=tool_ids,
        )

    def grant_session_tool_authorization(
        self,
        *,
        run_id: str,
        approval_request_id: str | None,
        effect_ids: tuple[str, ...],
        tool_ids: tuple[str, ...],
    ) -> None:
        if self.authorization_port is None:
            raise RuntimeError("Authorization service is not configured.")
        run = self.get_run(run_id)
        session_key = str(run.metadata.get("session_key", "")).strip()
        if not session_key:
            raise OrchestrationValidationError(
                "Orchestration run metadata.session_key is required for session grants.",
            )
        self.authorization_port.grant_session_authorization(
            session_key=session_key,
            agent_id=run.agent_id,
            approval_request_id=approval_request_id,
            effect_ids=effect_ids,
            tool_ids=tool_ids,
        )

    def grant_agent_effect_authorization(
        self,
        *,
        run_id: str,
        effect_ids: tuple[str, ...],
    ) -> None:
        if self.authorization_port is None:
            raise RuntimeError("Authorization service is not configured.")
        run = self.get_run(run_id)
        if run.agent_id is None or not run.agent_id.strip():
            raise OrchestrationValidationError(
                "Orchestration run agent_id is required for agent grants.",
            )
        for effect_id in effect_ids:
            self.authorization_port.grant_agent_effect_authorization(
                agent_id=run.agent_id,
                effect_id=effect_id,
            )

    def append_resolution_message(
        self,
        *,
        run_id: str,
        request: PendingApprovalRequest,
        decision: ApprovalDecision,
    ) -> None:
        if self.session_service is None:
            raise RuntimeError("Orchestration session service is not configured.")
        run = self.get_run(run_id)
        session_key = str(run.metadata.get("session_key", "")).strip()
        if not session_key:
            raise OrchestrationValidationError(
                "Orchestration run metadata.session_key is required for approval messages.",
            )
        if run.active_session_id is None or not run.active_session_id.strip():
            raise OrchestrationValidationError(
                "Orchestration run active_session_id is required for approval messages.",
            )
        status = "approved" if decision is not ApprovalDecision.DENY else "denied"
        tool_name = request.tool_name or request.effect_id
        target_phrase = (
            f"running {tool_name}"
            if request.tool_name is not None
            else f"{request.label} ({request.effect_id})"
        )
        detail = {
            ApprovalDecision.ALLOW_ONCE: (
                f"Approved once for this turn only for {target_phrase}. "
                "This access expires after the current turn and must be requested again later if it is still needed."
            ),
            ApprovalDecision.ALLOW_FOR_SESSION: (
                f"Approved for this session for {target_phrase}. "
                "This access remains available for later turns in the current session unless visibility changes."
            ),
            ApprovalDecision.ALWAYS_FOR_AGENT: (
                f"Approved for future turns with this agent for {target_phrase}. "
                "This access should remain available in later turns unless visibility changes."
            ),
            ApprovalDecision.DENY: "Denied by the user.",
        }[decision]
        self.session_service.append_message(
            AppendSessionMessageInput(
                session_key=session_key,
                session_id=run.active_session_id,
                role="tool",
                kind=SessionMessageKind.TOOL_RESULT,
                content_payload={
                    "tool_name": tool_name,
                    "tool_call_id": request.request_id,
                    "status": status,
                    "effect_id": request.effect_id,
                    "label": request.label,
                    "decision": decision.value,
                    "tool_ids": list(request.tool_ids),
                    "output": detail,
                },
                source_kind="approval_request",
                source_id=request.request_id,
                metadata={
                    "tool_call_id": request.request_id,
                    "tool_name": tool_name,
                },
            ),
        )
