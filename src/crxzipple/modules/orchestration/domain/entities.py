from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from crxzipple.modules.orchestration.domain.exceptions import (
    OrchestrationValidationError,
)
from crxzipple.modules.orchestration.domain.value_objects import (
    ApprovalDecision,
    ApprovalResolution,
    ExecutionChainStatus,
    ExecutionOwnerReference,
    ExecutionStepItemKind,
    ExecutionStepItemStatus,
    ExecutionStepKind,
    ExecutionStepStatus,
    InboundInstruction,
    OrchestrationBoundSessionTarget,
    OrchestrationIngressStatus,
    OrchestrationIngressRequestKind,
    OrchestrationExecutorLeaseStatus,
    OrchestrationErrorPayload,
    OrchestrationQueuePolicy,
    OrchestrationRunStage,
    OrchestrationRunStatus,
    PendingApprovalRequest,
    ReplyTarget,
    utcnow,
)
from crxzipple.shared.domain import AggregateRoot
from crxzipple.shared.domain.events import Event
from crxzipple.shared.orchestration_observation import (
    ORCHESTRATION_RUN_ADVANCED_EVENT,
    ORCHESTRATION_RUN_APPROVAL_RESOLVED_EVENT,
    ORCHESTRATION_RUN_CANCELLED_EVENT,
    ORCHESTRATION_RUN_CLAIMED_EVENT,
    ORCHESTRATION_RUN_COMPLETED_EVENT,
    ORCHESTRATION_RUN_FAILED_EVENT,
    ORCHESTRATION_RUN_LLM_ATTEMPT_REWOUND_EVENT,
    ORCHESTRATION_RUN_QUEUED_EVENT,
    ORCHESTRATION_RUN_RESUMED_EVENT,
    ORCHESTRATION_RUN_WAITING_EVENT,
    ORCHESTRATION_RUN_WAITING_FOR_CONFIRMATION_EVENT,
    ORCHESTRATION_RUN_WORKER_LEASE_RECOVERED_EVENT,
)

WAITING_REASON_MAX_CHARS = 100


def _optional_payload_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _optional_datetime_payload(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _optional_payload_dict(value: object) -> dict[str, object] | None:
    return dict(value) if isinstance(value, dict) else None


def _active_run_ids_from_metadata(metadata: dict[str, object]) -> list[str]:
    runtime_state = metadata.get("runtime_state")
    if not isinstance(runtime_state, dict):
        return []
    raw_active_run_ids = runtime_state.get("active_run_ids")
    if not isinstance(raw_active_run_ids, (list, tuple, set)):
        return []
    return [
        text
        for item in raw_active_run_ids
        for text in (_optional_payload_text(item),)
        if text is not None
    ]


def _normalized_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _waiting_reason(value: str | None) -> str | None:
    normalized = _normalized_optional_text(value)
    if normalized is None:
        return None
    if len(normalized) <= WAITING_REASON_MAX_CHARS:
        return normalized
    return f"{normalized[: WAITING_REASON_MAX_CHARS - 3]}..."


def _normalized_payload(value: dict[str, object] | None) -> dict[str, object] | None:
    if value is None:
        return None
    return dict(value)


@dataclass(kw_only=True)
class ExecutionChain(AggregateRoot[str]):
    turn_id: str
    status: ExecutionChainStatus = ExecutionChainStatus.CREATED
    active_step_id: str | None = None
    step_count: int = 0
    error_payload: OrchestrationErrorPayload | None = None
    created_at: datetime = field(default_factory=utcnow)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise OrchestrationValidationError("Execution chain id cannot be empty.")
        if not self.turn_id.strip():
            raise OrchestrationValidationError("Execution chain turn_id cannot be empty.")
        if not isinstance(self.status, ExecutionChainStatus):
            self.status = ExecutionChainStatus(str(self.status))
        self.active_step_id = _normalized_optional_text(self.active_step_id)
        if self.step_count < 0:
            raise OrchestrationValidationError(
                "Execution chain step_count cannot be negative.",
            )

    @classmethod
    def create(cls, *, chain_id: str, turn_id: str) -> "ExecutionChain":
        return cls(id=chain_id, turn_id=turn_id)

    def start(self, *, active_step_id: str | None = None) -> None:
        timestamp = utcnow()
        self.status = ExecutionChainStatus.RUNNING
        self.active_step_id = _normalized_optional_text(active_step_id)
        self.started_at = self.started_at or timestamp
        self.updated_at = timestamp

    def set_active_step(self, step_id: str | None) -> None:
        self.active_step_id = _normalized_optional_text(step_id)
        self.updated_at = utcnow()

    def increment_step_count(self) -> None:
        self.step_count += 1
        self.updated_at = utcnow()

    def wait(self, *, active_step_id: str | None = None) -> None:
        self.status = ExecutionChainStatus.WAITING
        if active_step_id is not None:
            self.active_step_id = _normalized_optional_text(active_step_id)
        self.updated_at = utcnow()

    def complete(self) -> None:
        timestamp = utcnow()
        self.status = ExecutionChainStatus.COMPLETED
        self.active_step_id = None
        self.completed_at = timestamp
        self.updated_at = timestamp
        self.error_payload = None

    def fail(
        self,
        *,
        message: str,
        code: str = "execution_chain_failed",
        details: dict[str, object] | None = None,
    ) -> None:
        timestamp = utcnow()
        self.status = ExecutionChainStatus.FAILED
        self.completed_at = timestamp
        self.updated_at = timestamp
        self.error_payload = OrchestrationErrorPayload(
            message=message,
            code=code,
            details=details or {},
        )

    def cancel(self) -> None:
        timestamp = utcnow()
        self.status = ExecutionChainStatus.CANCELLED
        self.active_step_id = None
        self.completed_at = timestamp
        self.updated_at = timestamp


@dataclass(kw_only=True)
class ExecutionStep(AggregateRoot[str]):
    chain_id: str
    turn_id: str
    step_index: int
    kind: ExecutionStepKind
    status: ExecutionStepStatus = ExecutionStepStatus.CREATED
    dispatch_task_id: str | None = None
    owner: ExecutionOwnerReference | None = None
    correlation_key: str | None = None
    error_payload: OrchestrationErrorPayload | None = None
    created_at: datetime = field(default_factory=utcnow)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise OrchestrationValidationError("Execution step id cannot be empty.")
        if not self.chain_id.strip():
            raise OrchestrationValidationError("Execution step chain_id cannot be empty.")
        if not self.turn_id.strip():
            raise OrchestrationValidationError("Execution step turn_id cannot be empty.")
        if self.step_index < 0:
            raise OrchestrationValidationError(
                "Execution step step_index cannot be negative.",
            )
        if not isinstance(self.kind, ExecutionStepKind):
            self.kind = ExecutionStepKind(str(self.kind))
        if not isinstance(self.status, ExecutionStepStatus):
            self.status = ExecutionStepStatus(str(self.status))
        self.dispatch_task_id = _normalized_optional_text(self.dispatch_task_id)
        self.correlation_key = _normalized_optional_text(self.correlation_key)

    @classmethod
    def create(
        cls,
        *,
        step_id: str,
        chain_id: str,
        turn_id: str,
        step_index: int,
        kind: ExecutionStepKind,
        correlation_key: str | None = None,
    ) -> "ExecutionStep":
        return cls(
            id=step_id,
            chain_id=chain_id,
            turn_id=turn_id,
            step_index=step_index,
            kind=kind,
            correlation_key=correlation_key,
        )

    def assign_dispatch_task(self, dispatch_task_id: str | None) -> None:
        self.dispatch_task_id = _normalized_optional_text(dispatch_task_id)
        self.updated_at = utcnow()

    def link_owner(self, owner: ExecutionOwnerReference | None) -> None:
        self.owner = owner
        self.updated_at = utcnow()

    def start(self) -> None:
        timestamp = utcnow()
        self.status = ExecutionStepStatus.RUNNING
        self.started_at = self.started_at or timestamp
        self.updated_at = timestamp

    def wait(self) -> None:
        self.status = ExecutionStepStatus.WAITING
        self.updated_at = utcnow()

    def complete(self) -> None:
        timestamp = utcnow()
        self.status = ExecutionStepStatus.COMPLETED
        self.completed_at = timestamp
        self.updated_at = timestamp
        self.error_payload = None

    def fail(
        self,
        *,
        message: str,
        code: str = "execution_step_failed",
        details: dict[str, object] | None = None,
    ) -> None:
        timestamp = utcnow()
        self.status = ExecutionStepStatus.FAILED
        self.completed_at = timestamp
        self.updated_at = timestamp
        self.error_payload = OrchestrationErrorPayload(
            message=message,
            code=code,
            details=details or {},
        )

    def cancel(self) -> None:
        timestamp = utcnow()
        self.status = ExecutionStepStatus.CANCELLED
        self.completed_at = timestamp
        self.updated_at = timestamp


@dataclass(kw_only=True)
class ExecutionStepItem(AggregateRoot[str]):
    step_id: str
    chain_id: str
    turn_id: str
    item_index: int
    kind: ExecutionStepItemKind
    status: ExecutionStepItemStatus = ExecutionStepItemStatus.CREATED
    owner: ExecutionOwnerReference | None = None
    correlation_key: str | None = None
    source_event_id: str | None = None
    payload_ref: dict[str, object] | None = None
    summary_payload: dict[str, object] | None = None
    error_payload: OrchestrationErrorPayload | None = None
    created_at: datetime = field(default_factory=utcnow)
    completed_at: datetime | None = None
    updated_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise OrchestrationValidationError("Execution step item id cannot be empty.")
        if not self.step_id.strip():
            raise OrchestrationValidationError(
                "Execution step item step_id cannot be empty.",
            )
        if not self.chain_id.strip():
            raise OrchestrationValidationError(
                "Execution step item chain_id cannot be empty.",
            )
        if not self.turn_id.strip():
            raise OrchestrationValidationError(
                "Execution step item turn_id cannot be empty.",
            )
        if self.item_index < 0:
            raise OrchestrationValidationError(
                "Execution step item item_index cannot be negative.",
            )
        if not isinstance(self.kind, ExecutionStepItemKind):
            self.kind = ExecutionStepItemKind(str(self.kind))
        if not isinstance(self.status, ExecutionStepItemStatus):
            self.status = ExecutionStepItemStatus(str(self.status))
        self.correlation_key = _normalized_optional_text(self.correlation_key)
        self.source_event_id = _normalized_optional_text(self.source_event_id)
        self.payload_ref = _normalized_payload(self.payload_ref)
        self.summary_payload = _normalized_payload(self.summary_payload)

    @classmethod
    def create(
        cls,
        *,
        item_id: str,
        step_id: str,
        chain_id: str,
        turn_id: str,
        item_index: int,
        kind: ExecutionStepItemKind,
        owner: ExecutionOwnerReference | None = None,
        correlation_key: str | None = None,
    ) -> "ExecutionStepItem":
        return cls(
            id=item_id,
            step_id=step_id,
            chain_id=chain_id,
            turn_id=turn_id,
            item_index=item_index,
            kind=kind,
            owner=owner,
            correlation_key=correlation_key,
        )

    def link_owner(self, owner: ExecutionOwnerReference | None) -> None:
        self.owner = owner
        self.updated_at = utcnow()

    def start(self) -> None:
        self.status = ExecutionStepItemStatus.RUNNING
        self.updated_at = utcnow()

    def wait(self) -> None:
        self.status = ExecutionStepItemStatus.WAITING
        self.updated_at = utcnow()

    def complete(self, *, summary_payload: dict[str, object] | None = None) -> None:
        timestamp = utcnow()
        self.status = ExecutionStepItemStatus.COMPLETED
        if summary_payload is not None:
            self.summary_payload = dict(summary_payload)
        self.completed_at = timestamp
        self.updated_at = timestamp
        self.error_payload = None

    def fail(
        self,
        *,
        message: str,
        code: str = "execution_step_item_failed",
        details: dict[str, object] | None = None,
    ) -> None:
        timestamp = utcnow()
        self.status = ExecutionStepItemStatus.FAILED
        self.completed_at = timestamp
        self.updated_at = timestamp
        self.error_payload = OrchestrationErrorPayload(
            message=message,
            code=code,
            details=details or {},
        )

    def mark_late_observed(self) -> None:
        timestamp = utcnow()
        self.status = ExecutionStepItemStatus.LATE_OBSERVED
        self.completed_at = self.completed_at or timestamp
        self.updated_at = timestamp

    def mark_late_ignored(self) -> None:
        timestamp = utcnow()
        self.status = ExecutionStepItemStatus.LATE_IGNORED
        self.completed_at = self.completed_at or timestamp
        self.updated_at = timestamp


@dataclass(kw_only=True)
class OrchestrationRun(AggregateRoot[str]):
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

    def route(
        self,
        *,
        agent_id: str,
        lane_key: str | None = None,
        priority: int | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        normalized_agent_id = agent_id.strip()
        if not normalized_agent_id:
            raise OrchestrationValidationError("Orchestration run agent_id cannot be empty.")
        if priority is not None and priority < 0:
            raise OrchestrationValidationError(
                "Orchestration run priority cannot be negative.",
            )
        self.agent_id = normalized_agent_id
        self.lane_key = lane_key.strip() if lane_key is not None and lane_key.strip() else self.lane_key
        if priority is not None:
            self.priority = priority
        if metadata:
            self.metadata.update(metadata)
        self.stage = OrchestrationRunStage.ROUTED
        self.updated_at = utcnow()
        self.record_event(
            Event(
                name="orchestration.run.routed",
                payload={
                    "run_id": self.id,
                    "agent_id": self.agent_id,
                    "session_key": self.session_key,
                    "lane_key": self.lane_key,
                    "status": self.status.value,
                    "stage": self.stage.value,
                    "current_step": self.current_step,
                    "priority": self.priority,
                },
            ),
        )

    def bind_session(
        self,
        *,
        active_session_id: str,
    ) -> None:
        normalized_session_id = active_session_id.strip()
        if not normalized_session_id:
            raise OrchestrationValidationError(
                "Orchestration run active_session_id cannot be empty.",
            )
        self.active_session_id = normalized_session_id
        self.stage = OrchestrationRunStage.BULK_READY
        self.updated_at = utcnow()
        self.record_event(
            Event(
                name="orchestration.run.bulk_ready",
                payload={
                    "run_id": self.id,
                    "session_key": self.session_key,
                    "active_session_id": self.active_session_id,
                    "status": self.status.value,
                    "stage": self.stage.value,
                    "current_step": self.current_step,
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
        self.lane_lock_key = None
        self.queued_at = utcnow()
        self.updated_at = self.queued_at
        self.record_event(
            Event(
                name=ORCHESTRATION_RUN_QUEUED_EVENT,
                payload={
                    "run_id": self.id,
                    "session_key": self.session_key,
                    "active_session_id": self.active_session_id,
                    "agent_id": self.agent_id,
                    "status": self.status.value,
                    "stage": self.stage.value,
                    "current_step": self.current_step,
                    "lane_key": self.lane_key,
                    "priority": self.priority,
                    "queue_policy": self.queue_policy.value,
                },
            ),
        )

    def claim(
        self,
        *,
        worker_id: str,
        claimed_at: datetime | None = None,
        acquire_lane_lock: bool = True,
    ) -> None:
        normalized_worker_id = worker_id.strip()
        if not normalized_worker_id:
            raise OrchestrationValidationError("Orchestration worker_id cannot be empty.")
        timestamp = claimed_at or utcnow()
        self.status = OrchestrationRunStatus.RUNNING
        self.stage = OrchestrationRunStage.RUNNING
        self.worker_id = normalized_worker_id
        self.lane_lock_key = self.lane_key if acquire_lane_lock else None
        self.started_at = timestamp
        self.updated_at = timestamp
        self.record_event(
            Event(
                name=ORCHESTRATION_RUN_CLAIMED_EVENT,
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
                    "priority": self.priority,
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
            Event(
                name="orchestration.run.heartbeated",
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

    def recover_worker_lease(
        self,
        *,
        reason: str,
        happened_at: datetime | None = None,
    ) -> None:
        if self.status is not OrchestrationRunStatus.RUNNING:
            raise OrchestrationValidationError(
                "Only running orchestration runs can recover a worker lease.",
            )
        normalized_reason = reason.strip()
        if not normalized_reason:
            raise OrchestrationValidationError(
                "Orchestration run recovery reason cannot be empty.",
            )
        timestamp = happened_at or utcnow()
        previous_worker_id = self.worker_id
        previous_stage = self.stage
        self.status = OrchestrationRunStatus.QUEUED
        self.stage = OrchestrationRunStage.QUEUED
        self.worker_id = None
        self.lane_lock_key = None
        self.waiting_reason = None
        self.queued_at = timestamp
        self.updated_at = timestamp
        self.metadata["last_worker_lease_recovery"] = {
            "reason": normalized_reason,
            "previous_worker_id": previous_worker_id,
            "previous_stage": previous_stage.value,
            "recovered_at": timestamp.isoformat(),
        }
        self.record_event(
            Event(
                name=ORCHESTRATION_RUN_WORKER_LEASE_RECOVERED_EVENT,
                payload={
                    "run_id": self.id,
                    "session_key": self.session_key,
                    "active_session_id": self.active_session_id,
                    "agent_id": self.agent_id,
                    "status": self.status.value,
                    "stage": self.stage.value,
                    "current_step": self.current_step,
                    "lane_key": self.lane_key,
                    "priority": self.priority,
                    "queue_policy": self.queue_policy.value,
                    "previous_worker_id": previous_worker_id,
                    "previous_stage": previous_stage.value,
                    "reason": normalized_reason,
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
        self.lane_lock_key = None
        self.queued_at = timestamp
        self.updated_at = timestamp
        self.record_event(
            Event(
                name=ORCHESTRATION_RUN_RESUMED_EVENT,
                payload={
                    "run_id": self.id,
                    "session_key": self.session_key,
                    "active_session_id": self.active_session_id,
                    "agent_id": self.agent_id,
                    "status": self.status.value,
                    "stage": self.stage.value,
                    "current_step": self.current_step,
                    "lane_key": self.lane_key,
                    "priority": self.priority,
                    "queue_policy": self.queue_policy.value,
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
        self.lane_lock_key = None
        self.result_payload = dict(result_payload or {})
        self.completed_at = timestamp
        self.updated_at = timestamp
        self.record_event(
            Event(
                name=ORCHESTRATION_RUN_COMPLETED_EVENT,
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
        self.lane_lock_key = None
        self.error = OrchestrationErrorPayload(
            message=message,
            code=code,
            details=details or {},
        )
        self.completed_at = timestamp
        self.updated_at = timestamp
        self.record_event(
            Event(
                name=ORCHESTRATION_RUN_FAILED_EVENT,
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
                    "code": self.error.code,
                    "message": self.error.message,
                    "details": dict(self.error.details),
                },
            ),
        )

    def cancel(self, *, reason: str | None = None) -> None:
        self.status = OrchestrationRunStatus.CANCELLED
        self.stage = OrchestrationRunStage.CANCELLED
        self.lane_lock_key = None
        self.worker_id = None
        self.pending_tool_run_ids = ()
        self.pending_approval_request_payload = None
        normalized_reason = _normalized_optional_text(reason)
        self.waiting_reason = _waiting_reason(normalized_reason)
        if normalized_reason is not None:
            self.metadata["cancellation_reason"] = normalized_reason
        self.completed_at = utcnow()
        self.updated_at = self.completed_at
        self.record_event(
            Event(
                name=ORCHESTRATION_RUN_CANCELLED_EVENT,
                payload={
                    "run_id": self.id,
                    "session_key": self.session_key,
                    "active_session_id": self.active_session_id,
                    "agent_id": self.agent_id,
                    "status": self.status.value,
                    "stage": self.stage.value,
                    "current_step": self.current_step,
                    "lane_key": self.lane_key,
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


@dataclass(kw_only=True)
class OrchestrationIngressRequest(AggregateRoot[str]):
    run_id: str
    kind: OrchestrationIngressRequestKind = OrchestrationIngressRequestKind.ROUTED_TURN
    route_context_payload: dict[str, object] = field(default_factory=dict)
    bound_session_payload: dict[str, object] = field(default_factory=dict)
    requested_llm_id: str | None = None
    ensure_session: bool = True
    touch_activity: bool = True
    reset_policy_payload: dict[str, object] = field(default_factory=dict)
    prepare_metadata: dict[str, object] = field(default_factory=dict)
    queue_policy: OrchestrationQueuePolicy = OrchestrationQueuePolicy.FIFO
    priority: int | None = None
    status: OrchestrationIngressStatus = OrchestrationIngressStatus.QUEUED
    worker_id: str | None = None
    error: OrchestrationErrorPayload | None = None
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)
    claimed_at: datetime | None = None
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise OrchestrationValidationError(
                "Orchestration ingress request id cannot be empty.",
            )
        if not self.run_id.strip():
            raise OrchestrationValidationError(
                "Orchestration ingress request run_id cannot be empty.",
            )
        if not isinstance(self.kind, OrchestrationIngressRequestKind):
            self.kind = OrchestrationIngressRequestKind(str(self.kind))
        if not isinstance(self.queue_policy, OrchestrationQueuePolicy):
            self.queue_policy = OrchestrationQueuePolicy(str(self.queue_policy))
        if self.priority is not None and self.priority < 0:
            raise OrchestrationValidationError(
                "Orchestration ingress request priority cannot be negative.",
            )
        if not isinstance(self.status, OrchestrationIngressStatus):
            self.status = OrchestrationIngressStatus(str(self.status))
        self.route_context_payload = dict(self.route_context_payload)
        self.bound_session_payload = dict(self.bound_session_payload)
        self.reset_policy_payload = dict(self.reset_policy_payload)
        self.prepare_metadata = dict(self.prepare_metadata)
        if self.requested_llm_id is not None:
            self.requested_llm_id = self.requested_llm_id.strip() or None
        if self.worker_id is not None:
            self.worker_id = self.worker_id.strip() or None
        self._validate_target_payload()

    @classmethod
    def queue_turn(
        cls,
        *,
        request_id: str,
        run_id: str,
        route_context_payload: dict[str, object],
        requested_llm_id: str | None = None,
        ensure_session: bool = True,
        touch_activity: bool = True,
        reset_policy_payload: dict[str, object] | None = None,
        prepare_metadata: dict[str, object] | None = None,
        queue_policy: OrchestrationQueuePolicy = OrchestrationQueuePolicy.FIFO,
        priority: int | None = None,
    ) -> "OrchestrationIngressRequest":
        request = cls(
            id=request_id,
            run_id=run_id,
            kind=OrchestrationIngressRequestKind.ROUTED_TURN,
            route_context_payload=route_context_payload,
            requested_llm_id=requested_llm_id,
            ensure_session=ensure_session,
            touch_activity=touch_activity,
            reset_policy_payload=reset_policy_payload or {},
            prepare_metadata=prepare_metadata or {},
            queue_policy=queue_policy,
            priority=priority,
        )
        request.record_event(
            Event(
                name="orchestration.ingress.requested",
                payload={
                    "request_id": request.id,
                    "run_id": request.run_id,
                    "kind": request.kind.value,
                    "status": request.status.value,
                    "source": _optional_payload_text(
                        request.route_context_payload.get("surface"),
                    )
                    or _optional_payload_text(
                        request.route_context_payload.get("channel"),
                    ),
                    "target_lane": _optional_payload_text(
                        request.route_context_payload.get("main_key"),
                    ),
                    "priority": request.priority,
                    "queue_policy": request.queue_policy.value,
                    "requested_llm_id": request.requested_llm_id,
                },
            ),
        )
        return request

    @classmethod
    def queue_bound_turn(
        cls,
        *,
        request_id: str,
        run_id: str,
        bound_session_target: OrchestrationBoundSessionTarget,
        requested_llm_id: str | None = None,
        prepare_metadata: dict[str, object] | None = None,
        queue_policy: OrchestrationQueuePolicy = OrchestrationQueuePolicy.FIFO,
        priority: int | None = None,
    ) -> "OrchestrationIngressRequest":
        request = cls(
            id=request_id,
            run_id=run_id,
            kind=OrchestrationIngressRequestKind.BOUND_TURN,
            bound_session_payload=bound_session_target.to_payload(),
            requested_llm_id=requested_llm_id,
            ensure_session=False,
            touch_activity=False,
            prepare_metadata=prepare_metadata or {},
            queue_policy=queue_policy,
            priority=priority,
        )
        request.record_event(
            Event(
                name="orchestration.ingress.requested",
                payload={
                    "request_id": request.id,
                    "run_id": request.run_id,
                    "kind": request.kind.value,
                    "status": request.status.value,
                    "source": "bound_turn",
                    "target_lane": bound_session_target.lane_key
                    or bound_session_target.session_key,
                    "priority": request.priority,
                    "queue_policy": request.queue_policy.value,
                    "requested_llm_id": request.requested_llm_id,
                },
            ),
        )
        return request

    def claim(self, *, worker_id: str, claimed_at: datetime | None = None) -> None:
        normalized_worker_id = worker_id.strip()
        if not normalized_worker_id:
            raise OrchestrationValidationError(
                "Orchestration ingress worker_id cannot be empty.",
            )
        timestamp = claimed_at or utcnow()
        self.status = OrchestrationIngressStatus.PROCESSING
        self.worker_id = normalized_worker_id
        self.claimed_at = timestamp
        self.updated_at = timestamp
        self.record_event(
            Event(
                name="orchestration.ingress.claimed",
                payload={
                    "request_id": self.id,
                    "run_id": self.run_id,
                    "kind": self.kind.value,
                    "status": self.status.value,
                    "worker_id": self.worker_id,
                },
            ),
        )

    def complete(self, *, completed_at: datetime | None = None) -> None:
        timestamp = completed_at or utcnow()
        self.status = OrchestrationIngressStatus.COMPLETED
        self.error = None
        self.completed_at = timestamp
        self.updated_at = timestamp
        self.record_event(
            Event(
                name="orchestration.ingress.completed",
                payload={
                    "request_id": self.id,
                    "run_id": self.run_id,
                    "kind": self.kind.value,
                    "status": self.status.value,
                },
            ),
        )

    def fail(
        self,
        *,
        message: str,
        code: str = "ingress_failed",
        details: dict[str, object] | None = None,
        failed_at: datetime | None = None,
    ) -> None:
        timestamp = failed_at or utcnow()
        self.status = OrchestrationIngressStatus.FAILED
        self.error = OrchestrationErrorPayload(
            message=message,
            code=code,
            details=details or {},
        )
        self.completed_at = timestamp
        self.updated_at = timestamp
        self.record_event(
            Event(
                name="orchestration.ingress.failed",
                payload={
                    "request_id": self.id,
                    "run_id": self.run_id,
                    "kind": self.kind.value,
                    "status": self.status.value,
                    "code": code,
                    "message": message,
                    "details": dict(self.error.details),
                },
            ),
        )

    @property
    def bound_session_target(self) -> OrchestrationBoundSessionTarget | None:
        return OrchestrationBoundSessionTarget.from_payload(self.bound_session_payload)

    def _validate_target_payload(self) -> None:
        if self.kind is OrchestrationIngressRequestKind.ROUTED_TURN:
            if not self.route_context_payload:
                raise OrchestrationValidationError(
                    "Routed orchestration ingress request requires route_context_payload.",
                )
            if self.bound_session_payload:
                raise OrchestrationValidationError(
                    "Routed orchestration ingress request cannot include bound_session_payload.",
                )
            return
        if self.kind is OrchestrationIngressRequestKind.BOUND_TURN:
            if self.route_context_payload:
                raise OrchestrationValidationError(
                    "Bound orchestration ingress request cannot include route_context_payload.",
                )
            if self.bound_session_target is None:
                raise OrchestrationValidationError(
                    "Bound orchestration ingress request requires bound_session_payload.",
                )
            return
        raise OrchestrationValidationError(
            f"Unsupported orchestration ingress request kind '{self.kind.value}'.",
        )

@dataclass(kw_only=True)
class OrchestrationExecutorLease(AggregateRoot[str]):
    status: OrchestrationExecutorLeaseStatus = OrchestrationExecutorLeaseStatus.ONLINE
    max_inflight_assignments: int = 1
    inflight_assignment_count: int = 0
    metadata: dict[str, object] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)
    last_heartbeat_at: datetime = field(default_factory=utcnow)
    lease_expires_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise OrchestrationValidationError(
                "Orchestration executor lease worker id cannot be empty.",
            )
        if not isinstance(self.status, OrchestrationExecutorLeaseStatus):
            self.status = OrchestrationExecutorLeaseStatus(str(self.status))
        if self.max_inflight_assignments <= 0:
            raise OrchestrationValidationError(
                "Orchestration executor max_inflight_assignments must be positive.",
            )
        if self.inflight_assignment_count < 0:
            raise OrchestrationValidationError(
                "Orchestration executor inflight_assignment_count cannot be negative.",
            )
        if self.inflight_assignment_count > self.max_inflight_assignments:
            raise OrchestrationValidationError(
                "Orchestration executor inflight_assignment_count cannot exceed max capacity.",
            )
        self.metadata = dict(self.metadata)

    @property
    def worker_id(self) -> str:
        return self.id

    @property
    def can_accept_assignment(self) -> bool:
        return (
            self.status is OrchestrationExecutorLeaseStatus.ONLINE
            and not self.is_expired()
            and self.inflight_assignment_count < self.max_inflight_assignments
        )

    def is_expired(self, *, now: datetime | None = None) -> bool:
        if self.lease_expires_at is None:
            return False
        timestamp = now or utcnow()
        lease_expires_at = self.lease_expires_at
        if lease_expires_at.tzinfo is None and timestamp.tzinfo is not None:
            lease_expires_at = lease_expires_at.replace(tzinfo=timestamp.tzinfo)
        if timestamp.tzinfo is None and lease_expires_at.tzinfo is not None:
            timestamp = timestamp.replace(tzinfo=lease_expires_at.tzinfo)
        return lease_expires_at <= timestamp

    def effective_status(
        self,
        *,
        now: datetime | None = None,
    ) -> OrchestrationExecutorLeaseStatus:
        if self.is_expired(now=now):
            return OrchestrationExecutorLeaseStatus.OFFLINE
        return self.status

    def counts_toward_capacity(self, *, now: datetime | None = None) -> bool:
        return self.effective_status(now=now) is OrchestrationExecutorLeaseStatus.ONLINE

    def available_assignment_slots(self, *, now: datetime | None = None) -> int:
        if not self.counts_toward_capacity(now=now):
            return 0
        return max(
            self.max_inflight_assignments - self.inflight_assignment_count,
            0,
        )

    @classmethod
    def register(
        cls,
        *,
        worker_id: str,
        max_inflight_assignments: int = 1,
        inflight_assignment_count: int = 0,
        draining: bool = False,
        metadata: dict[str, object] | None = None,
        lease_seconds: int | None = None,
    ) -> "OrchestrationExecutorLease":
        timestamp = utcnow()
        lease = cls(
            id=worker_id,
            status=(
                OrchestrationExecutorLeaseStatus.DRAINING
                if draining
                else OrchestrationExecutorLeaseStatus.ONLINE
            ),
            max_inflight_assignments=max_inflight_assignments,
            inflight_assignment_count=inflight_assignment_count,
            metadata=metadata or {},
            created_at=timestamp,
            updated_at=timestamp,
            last_heartbeat_at=timestamp,
            lease_expires_at=(
                timestamp + timedelta(seconds=lease_seconds)
                if lease_seconds is not None
                else None
            ),
        )
        lease.record_event(
            Event(
                name="orchestration.executor.lease.registered",
                payload={
                    "worker_id": lease.worker_id,
                    "status": lease.status.value,
                    "max_inflight_assignments": lease.max_inflight_assignments,
                    "inflight_assignment_count": lease.inflight_assignment_count,
                    "available_assignment_slots": lease.available_assignment_slots(),
                    "active_run_ids": _active_run_ids_from_metadata(lease.metadata),
                    "last_heartbeat_at": _optional_datetime_payload(
                        lease.last_heartbeat_at,
                    ),
                    "lease_expires_at": _optional_datetime_payload(
                        lease.lease_expires_at,
                    ),
                },
            ),
        )
        return lease

    def heartbeat(
        self,
        *,
        max_inflight_assignments: int | None = None,
        inflight_assignment_count: int | None = None,
        draining: bool | None = None,
        metadata: dict[str, object] | None = None,
        lease_seconds: int | None = None,
        happened_at: datetime | None = None,
    ) -> None:
        timestamp = happened_at or utcnow()
        next_max = (
            max_inflight_assignments
            if max_inflight_assignments is not None
            else self.max_inflight_assignments
        )
        next_inflight = (
            inflight_assignment_count
            if inflight_assignment_count is not None
            else self.inflight_assignment_count
        )
        if next_max <= 0:
            raise OrchestrationValidationError(
                "Orchestration executor max_inflight_assignments must be positive.",
            )
        if next_inflight < 0:
            raise OrchestrationValidationError(
                "Orchestration executor inflight_assignment_count cannot be negative.",
            )
        if next_inflight > next_max:
            raise OrchestrationValidationError(
                "Orchestration executor inflight_assignment_count cannot exceed max capacity.",
            )
        if draining is not None:
            self.status = (
                OrchestrationExecutorLeaseStatus.DRAINING
                if draining
                else OrchestrationExecutorLeaseStatus.ONLINE
            )
        elif self.status is OrchestrationExecutorLeaseStatus.OFFLINE:
            self.status = OrchestrationExecutorLeaseStatus.ONLINE
        self.max_inflight_assignments = next_max
        self.inflight_assignment_count = next_inflight
        if metadata:
            self.metadata.update(metadata)
        self.last_heartbeat_at = timestamp
        self.updated_at = timestamp
        self.lease_expires_at = (
            timestamp + timedelta(seconds=lease_seconds)
            if lease_seconds is not None
            else self.lease_expires_at
        )
        self.record_event(
            Event(
                name="orchestration.executor.lease.heartbeated",
                payload={
                    "worker_id": self.worker_id,
                    "status": self.status.value,
                    "max_inflight_assignments": self.max_inflight_assignments,
                    "inflight_assignment_count": self.inflight_assignment_count,
                    "available_assignment_slots": self.available_assignment_slots(),
                    "active_run_ids": _active_run_ids_from_metadata(self.metadata),
                    "last_heartbeat_at": _optional_datetime_payload(
                        self.last_heartbeat_at,
                    ),
                    "lease_expires_at": _optional_datetime_payload(
                        self.lease_expires_at,
                    ),
                },
            ),
        )

    def claim_assignment_capacity(
        self,
        *,
        lease_seconds: int | None = None,
        happened_at: datetime | None = None,
    ) -> None:
        if self.status is not OrchestrationExecutorLeaseStatus.ONLINE:
            raise OrchestrationValidationError(
                "Only online orchestration executors can claim assignments.",
            )
        if self.inflight_assignment_count >= self.max_inflight_assignments:
            raise OrchestrationValidationError(
                "Orchestration executor has no free assignment capacity.",
            )
        timestamp = happened_at or utcnow()
        self.inflight_assignment_count += 1
        self.last_heartbeat_at = timestamp
        self.updated_at = timestamp
        self.lease_expires_at = (
            timestamp + timedelta(seconds=lease_seconds)
            if lease_seconds is not None
            else self.lease_expires_at
        )
        self.record_assignment_capacity_claimed()

    def record_assignment_capacity_claimed(self) -> None:
        self.record_event(
            Event(
                name="orchestration.executor.lease.assignment_claimed",
                payload={
                    "worker_id": self.worker_id,
                    "status": self.status.value,
                    "inflight_assignment_count": self.inflight_assignment_count,
                    "max_inflight_assignments": self.max_inflight_assignments,
                    "available_assignment_slots": self.available_assignment_slots(),
                    "last_heartbeat_at": _optional_datetime_payload(
                        self.last_heartbeat_at,
                    ),
                    "lease_expires_at": _optional_datetime_payload(
                        self.lease_expires_at,
                    ),
                },
            ),
        )

    def release_assignment_capacity(
        self,
        *,
        count: int = 1,
        happened_at: datetime | None = None,
    ) -> None:
        if count <= 0:
            raise OrchestrationValidationError(
                "Orchestration executor release count must be positive.",
            )
        timestamp = happened_at or utcnow()
        self.inflight_assignment_count = max(
            0,
            self.inflight_assignment_count - count,
        )
        self.updated_at = timestamp
        self.record_event(
            Event(
                name="orchestration.executor.lease.assignment_released",
                payload={
                    "worker_id": self.worker_id,
                    "status": self.status.value,
                    "inflight_assignment_count": self.inflight_assignment_count,
                    "max_inflight_assignments": self.max_inflight_assignments,
                    "available_assignment_slots": self.available_assignment_slots(),
                    "last_heartbeat_at": _optional_datetime_payload(
                        self.last_heartbeat_at,
                    ),
                    "lease_expires_at": _optional_datetime_payload(
                        self.lease_expires_at,
                    ),
                },
            ),
        )

    def mark_offline(self, *, happened_at: datetime | None = None) -> None:
        timestamp = happened_at or utcnow()
        self.status = OrchestrationExecutorLeaseStatus.OFFLINE
        self.updated_at = timestamp
        self.record_event(
            Event(
                name="orchestration.executor.lease.offline",
                payload={
                    "worker_id": self.worker_id,
                    "status": self.status.value,
                    "last_heartbeat_at": _optional_datetime_payload(
                        self.last_heartbeat_at,
                    ),
                    "lease_expires_at": _optional_datetime_payload(
                        self.lease_expires_at,
                    ),
                },
            ),
        )
