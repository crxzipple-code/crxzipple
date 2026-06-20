"""Follow-up orchestration flows that are scheduled from completed runs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol

from crxzipple.core.logger import get_logger
from crxzipple.modules.orchestration.application.commands import (
    SubmitBoundOrchestrationTurnInput,
)
from crxzipple.modules.orchestration.application.intake_commands import (
    AcceptOrchestrationRunInput,
)
from crxzipple.modules.orchestration.application.ports import SessionLookupPort
from crxzipple.modules.orchestration.domain.entities import OrchestrationRun
from crxzipple.modules.orchestration.domain.value_objects import InboundInstruction

logger = get_logger(__name__)


class SubmitBoundTurnPort(Protocol):
    def __call__(
        self,
        data: SubmitBoundOrchestrationTurnInput,
        *,
        inline_worker_id: str | None = None,
    ) -> OrchestrationRun:
        ...


@dataclass(slots=True)
class SessionsSpawnFollowupService:
    session_service: SessionLookupPort | None
    get_run: Callable[[str], OrchestrationRun]
    submit_bound_turn: SubmitBoundTurnPort
    queue_followup_continuation: Callable[[str], object]

    def queue_child_completion_continuation(self, run: OrchestrationRun) -> None:
        spawn_payload = run.metadata.get("sessions_spawn")
        if not isinstance(spawn_payload, dict):
            return
        try:
            self.queue_followup_continuation(run.id)
        except Exception:
            logger.exception(
                "failed to queue sessions_spawn follow-up continuation",
                extra={"child_run_id": run.id},
            )

    def process_child_completion(
        self,
        child_run_id: str,
    ) -> OrchestrationRun | None:
        return self.enqueue_for_completed_child(self.get_run(child_run_id))

    def enqueue_for_completed_child(
        self,
        run: OrchestrationRun,
    ) -> OrchestrationRun | None:
        spawn_payload = run.metadata.get("sessions_spawn")
        if not isinstance(spawn_payload, dict):
            return None
        requester_session_key = str(
            spawn_payload.get("requester_session_key", ""),
        ).strip()
        requester_agent_id = str(
            spawn_payload.get("requester_agent_id", ""),
        ).strip()
        if not requester_session_key or not requester_agent_id:
            return None
        if self.session_service is None:
            return None

        try:
            requester_session = self.session_service.get_session(requester_session_key)
        except Exception:
            logger.exception(
                "failed to load requester session for sessions_spawn follow-up",
                extra={
                    "child_run_id": run.id,
                    "requester_session_key": requester_session_key,
                },
            )
            return None

        followup_text = self.followup_text(run)
        try:
            followup_metadata = {
                "child_run_id": run.id,
                "child_session_key": run.session_key,
                "requester_session_key": requester_session_key,
                "requester_run_id": spawn_payload.get("requester_run_id"),
            }
            queued = self.submit_bound_turn(
                SubmitBoundOrchestrationTurnInput(
                    accept_input=AcceptOrchestrationRunInput(
                        inbound_instruction=InboundInstruction(
                            source="sessions_spawn_followup",
                            content={
                                "blocks": [
                                    {
                                        "type": "text",
                                        "text": followup_text,
                                    },
                                ],
                            },
                            metadata={
                                **followup_metadata,
                                "requester_agent_id": requester_agent_id,
                            },
                        ),
                    ),
                    agent_id=requester_agent_id,
                    session_key=requester_session.id,
                    active_session_id=requester_session.active_session_id,
                    metadata={
                        "runtime_request_flow_hint": {
                            "mode": "recovery_resume",
                            "reason": "child_session_completed",
                        },
                        "sessions_spawn_followup": followup_metadata,
                    },
                ),
                inline_worker_id=f"sessions_spawn_followup:{run.id}",
            )
            return self.get_run(queued.id)
        except Exception:
            logger.exception(
                "failed to enqueue sessions_spawn follow-up run",
                extra={
                    "child_run_id": run.id,
                    "requester_session_key": requester_session_key,
                },
            )
            return None

    @staticmethod
    def followup_text(run: OrchestrationRun) -> str:
        output_text = None
        if isinstance(run.result_payload, dict):
            raw_output_text = run.result_payload.get("output_text")
            if isinstance(raw_output_text, str) and raw_output_text.strip():
                output_text = raw_output_text.strip()
        lines = [
            "Child session completed.",
            f"- child_session_key: {run.session_key or 'unknown'}",
            f"- child_run_id: {run.id}",
        ]
        if output_text is not None:
            lines.extend(
                [
                    "",
                    "Child result:",
                    output_text,
                ],
            )
        else:
            lines.append("- child_result: [no textual output]")
        return "\n".join(lines).strip()
