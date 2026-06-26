"""Orchestration run aggregate."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from crxzipple.modules.orchestration.domain.exceptions import (
    OrchestrationValidationError,
)
from crxzipple.modules.orchestration.domain.value_objects import (
    ApprovalDecision,
    ApprovalResolution,
    InboundInstruction,
    OrchestrationErrorPayload,
    OrchestrationQueuePolicy,
    OrchestrationRunStage,
    OrchestrationRunStatus,
    PendingApprovalRequest,
    ReplyTarget,
    utcnow,
)
from crxzipple.modules.orchestration.domain.run_worker_lifecycle import (
    OrchestrationRunWorkerLifecycleMixin,
)
from crxzipple.modules.orchestration.domain.run_terminal_lifecycle import (
    OrchestrationRunTerminalLifecycleMixin,
)
from crxzipple.modules.orchestration.domain.run_queue_lifecycle import (
    OrchestrationRunQueueLifecycleMixin,
)
from crxzipple.shared.domain import AggregateRoot
from crxzipple.shared.domain.events import Event
from crxzipple.shared.orchestration_observation import (
    ORCHESTRATION_RUN_ADVANCED_EVENT,
    ORCHESTRATION_RUN_APPROVAL_RESOLVED_EVENT,
    ORCHESTRATION_RUN_LLM_ATTEMPT_REWOUND_EVENT,
    ORCHESTRATION_RUN_WAITING_EVENT,
    ORCHESTRATION_RUN_WAITING_FOR_CONFIRMATION_EVENT,
)

from .entity_payloads import (
    _optional_payload_dict,
    _waiting_reason,
)

@dataclass(kw_only=True)
class OrchestrationRun(
    OrchestrationRunQueueLifecycleMixin,
    OrchestrationRunWorkerLifecycleMixin,
    OrchestrationRunTerminalLifecycleMixin,
    AggregateRoot[str],
):
    inbound_instruction: InboundInstruction
    reply_target: ReplyTarget | None = None
    status: OrchestrationRunStatus = OrchestrationRunStatus.ACCEPTED
    stage: OrchestrationRunStage = OrchestrationRunStage.ACCEPTED
    active_session_id: str | None = None
    agent_id: str | None = None
    lane_key: str | None = None
    lane_lock_key: str | None = None
    queue_policy: OrchestrationQueuePolicy = OrchestrationQueuePolicy.FIFO
    priority: int = 100
    current_step: int = 0
    max_steps: int = 99
    pending_tool_run_ids: tuple[str, ...] = field(default_factory=tuple)
    waiting_reason: str | None = None
    pending_approval_request_payload: dict[str, object] | None = None
    last_approval_resolution_payload: dict[str, object] | None = None
    recovery_contract_payload: dict[str, object] | None = None
    result_payload: dict[str, object] | None = None
    error: OrchestrationErrorPayload | None = None
    worker_id: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)
    queued_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise OrchestrationValidationError("Orchestration run id cannot be empty.")
        if self.priority < 0:
            raise OrchestrationValidationError(
                "Orchestration run priority cannot be negative.",
            )
        if self.current_step < 0:
            raise OrchestrationValidationError(
                "Orchestration run current_step cannot be negative.",
            )
        if self.max_steps <= 0:
            raise OrchestrationValidationError(
                "Orchestration run max_steps must be greater than zero.",
            )
        if self.active_session_id is not None:
            self.active_session_id = self.active_session_id.strip() or None
        if self.agent_id is not None:
            self.agent_id = self.agent_id.strip() or None
        if self.lane_key is not None:
            self.lane_key = self.lane_key.strip() or None
        if self.lane_lock_key is not None:
            self.lane_lock_key = self.lane_lock_key.strip() or None
        if self.waiting_reason is not None:
            self.waiting_reason = _waiting_reason(self.waiting_reason)
        if not isinstance(self.queue_policy, OrchestrationQueuePolicy):
            self.queue_policy = OrchestrationQueuePolicy(str(self.queue_policy))
        self.pending_tool_run_ids = tuple(
            tool_run_id.strip()
            for tool_run_id in self.pending_tool_run_ids
            if tool_run_id is not None and tool_run_id.strip()
        )
        self.metadata = dict(self.metadata)
        self.pending_approval_request_payload = _optional_payload_dict(
            self.pending_approval_request_payload,
        )
        self.last_approval_resolution_payload = _optional_payload_dict(
            self.last_approval_resolution_payload,
        )
        self.recovery_contract_payload = _optional_payload_dict(
            self.recovery_contract_payload,
        )
        if self.result_payload is not None:
            self.result_payload = dict(self.result_payload)

    @property
    def session_key(self) -> str | None:
        raw = self.metadata.get("session_key")
        if not isinstance(raw, str):
            return None
        normalized = raw.strip()
        return normalized or None

    @classmethod
    def accept(
        cls,
        *,
        run_id: str,
        inbound_instruction: InboundInstruction,
        reply_target: ReplyTarget | None = None,
        priority: int = 100,
        max_steps: int = 99,
        queue_policy: OrchestrationQueuePolicy = OrchestrationQueuePolicy.FIFO,
        metadata: dict[str, object] | None = None,
    ) -> "OrchestrationRun":
        run = cls(
            id=run_id,
            inbound_instruction=inbound_instruction,
            reply_target=reply_target,
            priority=priority,
            max_steps=max_steps,
            queue_policy=queue_policy,
            metadata=metadata or {},
        )
        run.record_event(
            Event(
                name="orchestration.run.accepted",
                payload={
                    "run_id": run.id,
                    "source": run.inbound_instruction.source,
                    "session_key": run.session_key,
                    "status": run.status.value,
                    "stage": run.stage.value,
                    "current_step": run.current_step,
                    "priority": run.priority,
                },
            ),
        )
        return run

    def advance(
        self,
        *,
        worker_id: str,
        stage: OrchestrationRunStage,
        step_increment: int = 0,
        metadata: dict[str, object] | None = None,
        happened_at: datetime | None = None,
    ) -> None:
        if self.status is not OrchestrationRunStatus.RUNNING:
            raise OrchestrationValidationError(
                "Only running orchestration runs can be advanced.",
            )
        if stage not in {
            OrchestrationRunStage.RUNNING,
            OrchestrationRunStage.LLM,
            OrchestrationRunStage.TOOL,
            OrchestrationRunStage.FINALIZING,
        }:
            raise OrchestrationValidationError(
                "Orchestration run advance stage is not supported.",
            )
        if step_increment < 0:
            raise OrchestrationValidationError(
                "Orchestration run step_increment cannot be negative.",
            )
        next_step = self.current_step + step_increment
        if next_step > self.max_steps:
            raise OrchestrationValidationError(
                "Orchestration run step budget would exceed max_steps.",
            )

        normalized_worker_id = self._require_worker(worker_id)
        timestamp = happened_at or utcnow()
        self.worker_id = normalized_worker_id
        self.stage = stage
        self.current_step = next_step
        self.updated_at = timestamp
        self.waiting_reason = None
        if metadata:
            self.metadata.update(metadata)
        self.record_event(
            Event(
                name=ORCHESTRATION_RUN_ADVANCED_EVENT,
                payload={
                    "run_id": self.id,
                    "worker_id": self.worker_id,
                    "session_key": self.session_key,
                    "active_session_id": self.active_session_id,
                    "agent_id": self.agent_id,
                    "status": self.status.value,
                    "stage": self.stage.value,
                    "current_step": self.current_step,
                    "lane_key": self.lane_key,
                    "lane_lock_key": self.lane_lock_key,
                },
            ),
        )

    def rewind_llm_attempt(
        self,
        *,
        worker_id: str,
        previous_stage: OrchestrationRunStage,
        previous_step: int,
        happened_at: datetime | None = None,
    ) -> None:
        if self.status is not OrchestrationRunStatus.RUNNING:
            raise OrchestrationValidationError(
                "Only running orchestration runs can rewind an llm attempt.",
            )
        if self.stage is not OrchestrationRunStage.LLM:
            raise OrchestrationValidationError(
                "Only orchestration runs in llm stage can rewind an llm attempt.",
            )
        if previous_step < 0:
            raise OrchestrationValidationError(
                "Orchestration run previous_step cannot be negative.",
            )
        if previous_step > self.current_step:
            raise OrchestrationValidationError(
                "Orchestration run previous_step cannot exceed current_step.",
            )
        normalized_worker_id = self._require_worker(worker_id)
        timestamp = happened_at or utcnow()
        self.worker_id = normalized_worker_id
        self.stage = previous_stage
        self.current_step = previous_step
        self.updated_at = timestamp
        self.waiting_reason = None
        self.metadata.pop("llm_stream_invocation_id", None)
        self.metadata.pop("llm_stream_text", None)
        self.record_event(
            Event(
                name=ORCHESTRATION_RUN_LLM_ATTEMPT_REWOUND_EVENT,
                payload={
                    "run_id": self.id,
                    "worker_id": self.worker_id,
                    "session_key": self.session_key,
                    "active_session_id": self.active_session_id,
                    "agent_id": self.agent_id,
                    "status": self.status.value,
                    "stage": self.stage.value,
                    "current_step": self.current_step,
                    "lane_key": self.lane_key,
                    "lane_lock_key": self.lane_lock_key,
                },
            ),
        )

    def wait_on_tool(
        self,
        *,
        worker_id: str,
        pending_tool_run_ids: tuple[str, ...] | list[str],
        reason: str | None = None,
        happened_at: datetime | None = None,
    ) -> None:
        if self.status is not OrchestrationRunStatus.RUNNING:
            raise OrchestrationValidationError(
                "Only running orchestration runs can wait on tools.",
            )
        self._require_worker(worker_id)
        normalized_tool_run_ids = tuple(
            tool_run_id.strip()
            for tool_run_id in pending_tool_run_ids
            if tool_run_id is not None and tool_run_id.strip()
        )
        if not normalized_tool_run_ids:
            raise OrchestrationValidationError(
                "Waiting on tool requires at least one pending tool run id.",
            )
        timestamp = happened_at or utcnow()
        self.status = OrchestrationRunStatus.WAITING
        self.stage = OrchestrationRunStage.WAITING_ON_TOOL
        self.pending_tool_run_ids = normalized_tool_run_ids
        self.waiting_reason = _waiting_reason(reason) or "waiting_on_tool"
        self.worker_id = None
        self.updated_at = timestamp
        self.record_event(
            Event(
                name=ORCHESTRATION_RUN_WAITING_EVENT,
                payload={
                    "run_id": self.id,
                    "session_key": self.session_key,
                    "active_session_id": self.active_session_id,
                    "agent_id": self.agent_id,
                    "status": self.status.value,
                    "stage": self.stage.value,
                    "current_step": self.current_step,
                    "lane_key": self.lane_key,
                    "pending_tool_run_ids": list(self.pending_tool_run_ids),
                    "reason": self.waiting_reason,
                },
            ),
        )

    def wait_on_tool_after_confirmation(
        self,
        *,
        pending_tool_run_ids: tuple[str, ...] | list[str],
        reason: str | None = None,
        happened_at: datetime | None = None,
    ) -> None:
        if self.status is not OrchestrationRunStatus.WAITING:
            raise OrchestrationValidationError(
                "Only waiting orchestration runs can transition to tool wait after confirmation.",
            )
        if self.stage is not OrchestrationRunStage.WAITING_FOR_CONFIRMATION:
            raise OrchestrationValidationError(
                "Orchestration run is not waiting for confirmation.",
            )
        normalized_tool_run_ids = tuple(
            tool_run_id.strip()
            for tool_run_id in pending_tool_run_ids
            if tool_run_id is not None and tool_run_id.strip()
        )
        if not normalized_tool_run_ids:
            raise OrchestrationValidationError(
                "Waiting on tool requires at least one pending tool run id.",
            )
        timestamp = happened_at or utcnow()
        self.status = OrchestrationRunStatus.WAITING
        self.stage = OrchestrationRunStage.WAITING_ON_TOOL
        self.pending_tool_run_ids = normalized_tool_run_ids
        self.waiting_reason = _waiting_reason(reason) or "waiting_on_tool"
        self.worker_id = None
        self.updated_at = timestamp
        self.record_event(
            Event(
                name=ORCHESTRATION_RUN_WAITING_EVENT,
                payload={
                    "run_id": self.id,
                    "session_key": self.session_key,
                    "active_session_id": self.active_session_id,
                    "agent_id": self.agent_id,
                    "status": self.status.value,
                    "stage": self.stage.value,
                    "current_step": self.current_step,
                    "lane_key": self.lane_key,
                    "pending_tool_run_ids": list(self.pending_tool_run_ids),
                    "reason": self.waiting_reason,
                },
            ),
        )

    def pending_approval_request(self) -> PendingApprovalRequest | None:
        if self.pending_approval_request_payload is None:
            return None
        return PendingApprovalRequest.from_payload(self.pending_approval_request_payload)

    def wait_for_confirmation(
        self,
        *,
        worker_id: str,
        request: PendingApprovalRequest,
        reason: str | None = None,
        happened_at: datetime | None = None,
    ) -> None:
        if self.status is not OrchestrationRunStatus.RUNNING:
            raise OrchestrationValidationError(
                "Only running orchestration runs can wait for confirmation.",
            )
        self._require_worker(worker_id)
        timestamp = happened_at or utcnow()
        self.status = OrchestrationRunStatus.WAITING
        self.stage = OrchestrationRunStage.WAITING_FOR_CONFIRMATION
        self.pending_tool_run_ids = ()
        self.waiting_reason = _waiting_reason(reason) or "waiting_for_confirmation"
        self.worker_id = None
        self.updated_at = timestamp
        self.pending_approval_request_payload = request.to_payload()
        self.record_event(
            Event(
                name=ORCHESTRATION_RUN_WAITING_FOR_CONFIRMATION_EVENT,
                payload={
                    "run_id": self.id,
                    "session_key": self.session_key,
                    "active_session_id": self.active_session_id,
                    "agent_id": self.agent_id,
                    "status": self.status.value,
                    "stage": self.stage.value,
                    "current_step": self.current_step,
                    "lane_key": self.lane_key,
                    "request_id": request.request_id,
                    "effect_id": request.effect_id,
                    "reason": self.waiting_reason,
                },
            ),
        )

    def resolve_approval_request(
        self,
        *,
        request_id: str,
        decision: ApprovalDecision,
        happened_at: datetime | None = None,
    ) -> PendingApprovalRequest:
        if self.status is not OrchestrationRunStatus.WAITING:
            raise OrchestrationValidationError(
                "Only waiting orchestration runs can resolve approval requests.",
            )
        if self.stage is not OrchestrationRunStage.WAITING_FOR_CONFIRMATION:
            raise OrchestrationValidationError(
                "Orchestration run is not waiting for confirmation.",
            )
        pending_request = self.pending_approval_request()
        if pending_request is None:
            raise OrchestrationValidationError(
                "Orchestration run has no pending approval request.",
            )
        normalized_request_id = request_id.strip()
        if not normalized_request_id:
            raise OrchestrationValidationError(
                "Approval request_id cannot be empty.",
            )
        if pending_request.request_id != normalized_request_id:
            raise OrchestrationValidationError(
                "Approval request id does not match the pending approval request.",
            )
        timestamp = happened_at or utcnow()
        self.pending_approval_request_payload = None
        self.last_approval_resolution_payload = ApprovalResolution(
            request_id=normalized_request_id,
            decision=decision,
            resolved_at=timestamp,
        ).to_payload()
        self.updated_at = timestamp
        self.record_event(
            Event(
                name=ORCHESTRATION_RUN_APPROVAL_RESOLVED_EVENT,
                payload={
                    "run_id": self.id,
                    "session_key": self.session_key,
                    "active_session_id": self.active_session_id,
                    "agent_id": self.agent_id,
                    "status": self.status.value,
                    "stage": self.stage.value,
                    "current_step": self.current_step,
                    "request_id": normalized_request_id,
                    "decision": decision.value,
                },
            ),
        )
        return pending_request
