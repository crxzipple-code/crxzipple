from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from crxzipple.modules.orchestration.domain.exceptions import (
    OrchestrationValidationError,
)
from crxzipple.modules.orchestration.domain.value_objects import (
    DeliveryTarget,
    InboundInstruction,
    OrchestrationErrorPayload,
    OrchestrationQueuePolicy,
    OrchestrationRunStage,
    OrchestrationRunStatus,
    utcnow,
)
from crxzipple.shared.domain import AggregateRoot
from crxzipple.shared.domain.events import DomainEvent


@dataclass(kw_only=True)
class OrchestrationRun(AggregateRoot[str]):
    inbound_instruction: InboundInstruction
    delivery_target: DeliveryTarget | None = None
    status: OrchestrationRunStatus = OrchestrationRunStatus.ACCEPTED
    stage: OrchestrationRunStage = OrchestrationRunStage.ACCEPTED
    bulk_key: str | None = None
    active_session_id: str | None = None
    agent_id: str | None = None
    lane_key: str | None = None
    queue_policy: OrchestrationQueuePolicy = OrchestrationQueuePolicy.FIFO
    priority: int = 100
    current_step: int = 0
    max_steps: int = 12
    pending_tool_run_ids: tuple[str, ...] = field(default_factory=tuple)
    waiting_reason: str | None = None
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
        if self.bulk_key is not None:
            self.bulk_key = self.bulk_key.strip() or None
        if self.active_session_id is not None:
            self.active_session_id = self.active_session_id.strip() or None
        if self.agent_id is not None:
            self.agent_id = self.agent_id.strip() or None
        if self.lane_key is not None:
            self.lane_key = self.lane_key.strip() or None
        if self.waiting_reason is not None:
            self.waiting_reason = self.waiting_reason.strip() or None
        if not isinstance(self.queue_policy, OrchestrationQueuePolicy):
            self.queue_policy = OrchestrationQueuePolicy(str(self.queue_policy))
        self.pending_tool_run_ids = tuple(
            tool_run_id.strip()
            for tool_run_id in self.pending_tool_run_ids
            if tool_run_id is not None and tool_run_id.strip()
        )
        self.metadata = dict(self.metadata)
        if self.result_payload is not None:
            self.result_payload = dict(self.result_payload)

    @classmethod
    def accept(
        cls,
        *,
        run_id: str,
        inbound_instruction: InboundInstruction,
        delivery_target: DeliveryTarget | None = None,
        priority: int = 100,
        max_steps: int = 12,
        queue_policy: OrchestrationQueuePolicy = OrchestrationQueuePolicy.FIFO,
        metadata: dict[str, object] | None = None,
    ) -> "OrchestrationRun":
        run = cls(
            id=run_id,
            inbound_instruction=inbound_instruction,
            delivery_target=delivery_target,
            priority=priority,
            max_steps=max_steps,
            queue_policy=queue_policy,
            metadata=metadata or {},
        )
        run.record_event(
            DomainEvent(
                name="orchestration.run.accepted",
                payload={
                    "run_id": run.id,
                    "source": run.inbound_instruction.source,
                },
            ),
        )
        return run

    def route(
        self,
        *,
        agent_id: str,
        bulk_key: str,
        lane_key: str | None = None,
        priority: int | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        normalized_agent_id = agent_id.strip()
        normalized_bulk_key = bulk_key.strip()
        if not normalized_agent_id:
            raise OrchestrationValidationError("Orchestration run agent_id cannot be empty.")
        if not normalized_bulk_key:
            raise OrchestrationValidationError("Orchestration run bulk_key cannot be empty.")
        if priority is not None and priority < 0:
            raise OrchestrationValidationError(
                "Orchestration run priority cannot be negative.",
            )
        self.agent_id = normalized_agent_id
        self.bulk_key = normalized_bulk_key
        self.lane_key = lane_key.strip() if lane_key is not None and lane_key.strip() else self.lane_key
        if priority is not None:
            self.priority = priority
        if metadata:
            self.metadata.update(metadata)
        self.stage = OrchestrationRunStage.ROUTED
        self.updated_at = utcnow()
        self.record_event(
            DomainEvent(
                name="orchestration.run.routed",
                payload={
                    "run_id": self.id,
                    "agent_id": self.agent_id,
                    "bulk_key": self.bulk_key,
                    "lane_key": self.lane_key,
                },
            ),
        )

    def bind_session(
        self,
        *,
        active_session_id: str,
        bulk_key: str | None = None,
    ) -> None:
        normalized_session_id = active_session_id.strip()
        if not normalized_session_id:
            raise OrchestrationValidationError(
                "Orchestration run active_session_id cannot be empty.",
            )
        if bulk_key is not None:
            normalized_bulk_key = bulk_key.strip()
            if not normalized_bulk_key:
                raise OrchestrationValidationError(
                    "Orchestration run bulk_key cannot be empty.",
                )
            self.bulk_key = normalized_bulk_key
        self.active_session_id = normalized_session_id
        self.stage = OrchestrationRunStage.BULK_READY
        self.updated_at = utcnow()
        self.record_event(
            DomainEvent(
                name="orchestration.run.bulk_ready",
                payload={
                    "run_id": self.id,
                    "bulk_key": self.bulk_key,
                    "active_session_id": self.active_session_id,
                },
            ),
        )

    def enqueue(
        self,
        *,
        lane_key: str | None = None,
        queue_policy: OrchestrationQueuePolicy | None = None,
        priority: int | None = None,
    ) -> None:
        if priority is not None and priority < 0:
            raise OrchestrationValidationError(
                "Orchestration run priority cannot be negative.",
            )
        if lane_key is not None:
            normalized_lane_key = lane_key.strip()
            if not normalized_lane_key:
                raise OrchestrationValidationError("Orchestration run lane_key cannot be empty.")
            self.lane_key = normalized_lane_key
        if queue_policy is not None:
            self.queue_policy = queue_policy
        if priority is not None:
            self.priority = priority
        self.status = OrchestrationRunStatus.QUEUED
        self.stage = OrchestrationRunStage.QUEUED
        self.waiting_reason = None
        self.pending_tool_run_ids = ()
        self.worker_id = None
        self.queued_at = utcnow()
        self.updated_at = self.queued_at
        self.record_event(
            DomainEvent(
                name="orchestration.run.queued",
                payload={
                    "run_id": self.id,
                    "lane_key": self.lane_key,
                    "priority": self.priority,
                },
            ),
        )

    def claim(self, *, worker_id: str, claimed_at: datetime | None = None) -> None:
        normalized_worker_id = worker_id.strip()
        if not normalized_worker_id:
            raise OrchestrationValidationError("Orchestration worker_id cannot be empty.")
        timestamp = claimed_at or utcnow()
        self.status = OrchestrationRunStatus.RUNNING
        self.stage = OrchestrationRunStage.RUNNING
        self.worker_id = normalized_worker_id
        self.started_at = timestamp
        self.updated_at = timestamp
        self.record_event(
            DomainEvent(
                name="orchestration.run.claimed",
                payload={
                    "run_id": self.id,
                    "worker_id": self.worker_id,
                    "lane_key": self.lane_key,
                },
            ),
        )

    def heartbeat(
        self,
        *,
        worker_id: str,
        happened_at: datetime | None = None,
    ) -> None:
        if self.status is not OrchestrationRunStatus.RUNNING:
            raise OrchestrationValidationError(
                "Only running orchestration runs can be heartbeated.",
            )
        normalized_worker_id = self._require_worker(worker_id)
        timestamp = happened_at or utcnow()
        self.worker_id = normalized_worker_id
        self.updated_at = timestamp
        self.record_event(
            DomainEvent(
                name="orchestration.run.heartbeated",
                payload={
                    "run_id": self.id,
                    "worker_id": self.worker_id,
                    "stage": self.stage.value,
                },
            ),
        )

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
            DomainEvent(
                name="orchestration.run.advanced",
                payload={
                    "run_id": self.id,
                    "worker_id": self.worker_id,
                    "stage": self.stage.value,
                    "current_step": self.current_step,
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
        self.waiting_reason = (
            reason.strip()
            if reason is not None and reason.strip()
            else "waiting_on_tool"
        )
        self.worker_id = None
        self.updated_at = timestamp
        self.record_event(
            DomainEvent(
                name="orchestration.run.waiting",
                payload={
                    "run_id": self.id,
                    "pending_tool_run_ids": list(self.pending_tool_run_ids),
                    "reason": self.waiting_reason,
                },
            ),
        )

    def resume(
        self,
        *,
        priority: int | None = None,
        lane_key: str | None = None,
        queue_policy: OrchestrationQueuePolicy | None = None,
        reason: str | None = None,
        happened_at: datetime | None = None,
        clear_pending_tool_run_ids: bool = True,
    ) -> None:
        if self.status is not OrchestrationRunStatus.WAITING:
            raise OrchestrationValidationError(
                "Only waiting orchestration runs can be resumed.",
            )
        if priority is not None and priority < 0:
            raise OrchestrationValidationError(
                "Orchestration run priority cannot be negative.",
            )
        if lane_key is not None:
            normalized_lane_key = lane_key.strip()
            if not normalized_lane_key:
                raise OrchestrationValidationError(
                    "Orchestration run lane_key cannot be empty.",
                )
            self.lane_key = normalized_lane_key
        if queue_policy is not None:
            self.queue_policy = queue_policy
        if priority is not None:
            self.priority = priority
        if clear_pending_tool_run_ids:
            self.pending_tool_run_ids = ()
        timestamp = happened_at or utcnow()
        self.status = OrchestrationRunStatus.QUEUED
        self.stage = OrchestrationRunStage.QUEUED
        self.waiting_reason = None
        self.worker_id = None
        self.queued_at = timestamp
        self.updated_at = timestamp
        self.record_event(
            DomainEvent(
                name="orchestration.run.resumed",
                payload={
                    "run_id": self.id,
                    "lane_key": self.lane_key,
                    "priority": self.priority,
                    "reason": reason.strip() if reason is not None and reason.strip() else None,
                },
            ),
        )

    def complete(
        self,
        *,
        worker_id: str,
        result_payload: dict[str, object] | None = None,
        happened_at: datetime | None = None,
    ) -> None:
        if self.status is not OrchestrationRunStatus.RUNNING:
            raise OrchestrationValidationError(
                "Only running orchestration runs can be completed.",
            )
        normalized_worker_id = self._require_worker(worker_id)
        timestamp = happened_at or utcnow()
        self.status = OrchestrationRunStatus.COMPLETED
        self.stage = OrchestrationRunStage.COMPLETED
        self.worker_id = normalized_worker_id
        self.pending_tool_run_ids = ()
        self.waiting_reason = None
        self.result_payload = dict(result_payload or {})
        self.completed_at = timestamp
        self.updated_at = timestamp
        self.record_event(
            DomainEvent(
                name="orchestration.run.completed",
                payload={
                    "run_id": self.id,
                    "worker_id": self.worker_id,
                },
            ),
        )

    def fail(
        self,
        *,
        worker_id: str | None = None,
        message: str,
        code: str = "orchestration_failed",
        details: dict[str, object] | None = None,
        happened_at: datetime | None = None,
    ) -> None:
        if self.status not in {
            OrchestrationRunStatus.RUNNING,
            OrchestrationRunStatus.WAITING,
        }:
            raise OrchestrationValidationError(
                "Only running or waiting orchestration runs can fail.",
            )
        normalized_worker_id: str | None = None
        if worker_id is not None:
            normalized_worker_id = self._require_worker(worker_id)
        timestamp = happened_at or utcnow()
        self.status = OrchestrationRunStatus.FAILED
        self.stage = OrchestrationRunStage.FAILED
        self.worker_id = normalized_worker_id
        self.pending_tool_run_ids = ()
        self.waiting_reason = None
        self.error = OrchestrationErrorPayload(
            message=message,
            code=code,
            details=details or {},
        )
        self.completed_at = timestamp
        self.updated_at = timestamp
        self.record_event(
            DomainEvent(
                name="orchestration.run.failed",
                payload={
                    "run_id": self.id,
                    "worker_id": self.worker_id,
                    "code": self.error.code,
                },
            ),
        )

    def cancel(self, *, reason: str | None = None) -> None:
        self.status = OrchestrationRunStatus.CANCELLED
        self.stage = OrchestrationRunStage.CANCELLED
        self.waiting_reason = reason.strip() if reason is not None and reason.strip() else None
        self.completed_at = utcnow()
        self.updated_at = self.completed_at
        self.record_event(
            DomainEvent(
                name="orchestration.run.cancelled",
                payload={
                    "run_id": self.id,
                    "reason": self.waiting_reason,
                },
            ),
        )

    def _require_worker(self, worker_id: str) -> str:
        normalized_worker_id = worker_id.strip()
        if not normalized_worker_id:
            raise OrchestrationValidationError("Orchestration worker_id cannot be empty.")
        if self.worker_id is not None and self.worker_id != normalized_worker_id:
            raise OrchestrationValidationError(
                "Orchestration run is already owned by a different worker.",
            )
        return normalized_worker_id
