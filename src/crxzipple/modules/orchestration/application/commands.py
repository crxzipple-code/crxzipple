from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from crxzipple.modules.orchestration.application.intake_commands import (
    AcceptOrchestrationRunInput as _AcceptOrchestrationRunInput,
)
from crxzipple.modules.orchestration.domain.value_objects import (
    ApprovalDecision,
    OrchestrationQueuePolicy,
    OrchestrationRunStage,
    PendingApprovalRequest,
)
from crxzipple.modules.session.domain import (
    SessionResetPolicy,
    SessionRouteContext,
)


@dataclass(frozen=True, slots=True)
class AdvanceAssignmentInput:
    run_id: str
    worker_id: str
    stage: OrchestrationRunStage
    step_increment: int = 0
    metadata: dict[str, object] = field(default_factory=dict)
    execution_payload: dict[str, object] = field(default_factory=dict)
    now: datetime | None = None


@dataclass(frozen=True, slots=True)
class WaitAssignmentOnToolInput:
    run_id: str
    worker_id: str
    pending_tool_run_ids: tuple[str, ...]
    reason: str | None = None
    now: datetime | None = None


@dataclass(frozen=True, slots=True)
class WaitForConfirmationInput:
    run_id: str
    worker_id: str
    request: PendingApprovalRequest
    llm_invocation_id: str
    metadata: dict[str, object] = field(default_factory=dict)
    execution_payload: dict[str, object] = field(default_factory=dict)
    reason: str | None = None
    now: datetime | None = None


@dataclass(frozen=True, slots=True)
class ResumeOrchestrationRunInput:
    run_id: str
    lane_key: str | None = None
    queue_policy: OrchestrationQueuePolicy | None = None
    priority: int | None = None
    reason: str | None = None
    clear_pending_tool_run_ids: bool = True
    metadata: dict[str, object] = field(default_factory=dict)
    now: datetime | None = None


@dataclass(frozen=True, slots=True)
class CompleteAssignmentInput:
    run_id: str
    worker_id: str
    result_payload: dict[str, object] = field(default_factory=dict)
    metadata: dict[str, object] = field(default_factory=dict)
    execution_payload: dict[str, object] = field(default_factory=dict)
    now: datetime | None = None


@dataclass(frozen=True, slots=True)
class FailAssignmentInput:
    run_id: str
    message: str
    code: str = "orchestration_failed"
    details: dict[str, object] = field(default_factory=dict)
    worker_id: str | None = None
    now: datetime | None = None


@dataclass(frozen=True, slots=True)
class SubmitOrchestrationTurnInput:
    accept_input: _AcceptOrchestrationRunInput
    context: SessionRouteContext
    requested_llm_id: str | None = None
    ensure_session: bool = True
    touch_activity: bool = True
    reset_policy: SessionResetPolicy | None = None
    prepare_metadata: dict[str, object] = field(default_factory=dict)
    enqueue_queue_policy: OrchestrationQueuePolicy | None = None
    enqueue_priority: int | None = None


@dataclass(frozen=True, slots=True)
class SubmitBoundOrchestrationTurnInput:
    accept_input: _AcceptOrchestrationRunInput
    agent_id: str
    session_key: str
    active_session_id: str
    lane_key: str | None = None
    requested_llm_id: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)
    enqueue_queue_policy: OrchestrationQueuePolicy | None = None
    enqueue_priority: int | None = None


@dataclass(frozen=True, slots=True)
class ResolveApprovalRequestInput:
    run_id: str
    request_id: str
    decision: ApprovalDecision
    now: datetime | None = None


@dataclass(frozen=True, slots=True)
class RequestCompactionInput:
    anchor_run_id: str
    reason: str | None = None
    preserve: str | None = None
    trigger_basis: str = "manual"
    trigger_details: dict[str, object] = field(default_factory=dict)
    queue_policy: OrchestrationQueuePolicy = OrchestrationQueuePolicy.JUMP_QUEUE
    priority: int | None = None
    max_steps: int = 1


@dataclass(frozen=True, slots=True)
class RequestHeartbeatInput:
    anchor_run_id: str
    reason: str | None = None
    idle_reply: str | None = "HEARTBEAT_OK"
    trigger_basis: str = "manual"
    trigger_details: dict[str, object] = field(default_factory=dict)
    queue_policy: OrchestrationQueuePolicy = OrchestrationQueuePolicy.JUMP_QUEUE
    priority: int | None = None
    max_steps: int = 1


@dataclass(frozen=True, slots=True)
class RequestMemoryFlushInput:
    anchor_run_id: str
    reason: str | None = None
    trigger_basis: str = "manual"
    trigger_details: dict[str, object] = field(default_factory=dict)
    queue_policy: OrchestrationQueuePolicy = OrchestrationQueuePolicy.JUMP_QUEUE
    priority: int | None = None
    max_steps: int = 1


@dataclass(frozen=True, slots=True)
class RequestDueHeartbeatsInput:
    idle_seconds: int
    agent_id: str | None = None
    limit: int | None = None
    reason: str | None = None
    idle_reply: str | None = "HEARTBEAT_OK"
    queue_policy: OrchestrationQueuePolicy = OrchestrationQueuePolicy.JUMP_QUEUE
    priority: int | None = None
    max_steps: int = 1
    now: datetime | None = None
