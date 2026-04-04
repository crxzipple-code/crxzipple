from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from crxzipple.modules.orchestration.application import (
    AcceptOrchestrationRunInput,
    AdvanceOrchestrationRunInput,
    CompleteOrchestrationRunInput,
    EnqueueOrchestrationRunInput,
    FailOrchestrationRunInput,
    PrepareSessionRunInput,
    RequestDueHeartbeatsInput,
    ResumeOrchestrationRunInput,
    WaitOnToolInput,
)
from crxzipple.modules.orchestration.domain import (
    OrchestrationQueuePolicy,
    OrchestrationRunStage,
)
from crxzipple.modules.orchestration.interfaces.dto import (
    DeliveryTargetDTO,
    InboundInstructionDTO,
    OrchestrationErrorDTO,
    OrchestrationRunDTO,
)
from crxzipple.modules.orchestration.interfaces.shared import (
    build_accept_run_input,
    build_delivery_target,
    build_inbound_instruction,
    build_prepare_session_run_input,
    build_reset_policy,
    build_session_route_context,
)
from crxzipple.modules.session.domain import DirectSessionScope


class InboundInstructionRequest(BaseModel):
    source: str
    content: Any | None = None
    metadata: dict[str, object] = Field(default_factory=dict)

    def to_value_object(self):
        return build_inbound_instruction(
            source=self.source,
            content=self.content,
            metadata=self.metadata,
        )


class DeliveryTargetRequest(BaseModel):
    interface_name: str
    address: str | None = None
    reply_to: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)

    def to_value_object(self):
        return build_delivery_target(
            interface_name=self.interface_name,
            address=self.address,
            reply_to=self.reply_to,
            metadata=self.metadata,
        )


class SessionRouteRequest(BaseModel):
    agent_id: str
    channel: str | None = None
    chat_type: str = "direct"
    peer_id: str | None = None
    conversation_id: str | None = None
    thread_id: str | None = None
    account_id: str | None = None
    label: str | None = None
    surface: str | None = None
    main_key: str = "main"
    direct_scope: DirectSessionScope = DirectSessionScope.MAIN
    status: str = "active"
    metadata: dict[str, object] = Field(default_factory=dict)

    def to_context(self):
        return build_session_route_context(
            agent_id=self.agent_id,
            channel=self.channel,
            chat_type=self.chat_type,
            peer_id=self.peer_id,
            conversation_id=self.conversation_id,
            thread_id=self.thread_id,
            account_id=self.account_id,
            label=self.label,
            surface=self.surface,
            main_key=self.main_key,
            direct_scope=self.direct_scope,
            status=self.status,
            metadata=self.metadata,
        )


class ResetPolicyRequest(BaseModel):
    idle_minutes: int | None = Field(default=None, ge=1)
    daily_reset_hour_utc: int | None = Field(default=None, ge=0, le=23)

    def to_value_object(self):
        return build_reset_policy(
            idle_minutes=self.idle_minutes,
            daily_reset_hour_utc=self.daily_reset_hour_utc,
        )


class IntakeOrchestrationRunRequest(BaseModel):
    inbound_instruction: InboundInstructionRequest
    session: SessionRouteRequest
    llm_id: str | None = None
    delivery_target: DeliveryTargetRequest | None = None
    run_id: str | None = None
    queue_policy: OrchestrationQueuePolicy = OrchestrationQueuePolicy.FIFO
    priority: int = 100
    max_steps: int = 99
    metadata: dict[str, object] = Field(default_factory=dict)
    enqueue: bool = False
    touch_activity: bool = True
    reset_policy: ResetPolicyRequest | None = None

    def to_accept_input(self) -> AcceptOrchestrationRunInput:
        return build_accept_run_input(
            source=self.inbound_instruction.source,
            content=self.inbound_instruction.content,
            inbound_metadata=self.inbound_instruction.metadata,
            delivery_interface=(
                self.delivery_target.interface_name
                if self.delivery_target is not None
                else None
            ),
            delivery_address=(
                self.delivery_target.address
                if self.delivery_target is not None
                else None
            ),
            delivery_reply_to=(
                self.delivery_target.reply_to
                if self.delivery_target is not None
                else None
            ),
            delivery_metadata=(
                self.delivery_target.metadata
                if self.delivery_target is not None
                else None
            ),
            run_id=self.run_id,
            queue_policy=self.queue_policy,
            priority=self.priority,
            max_steps=self.max_steps,
            metadata=self.metadata,
        )

    def to_prepare_input(self, *, run_id: str) -> PrepareSessionRunInput:
        return build_prepare_session_run_input(
            run_id=run_id,
            agent_id=self.session.agent_id,
            llm_id=self.llm_id,
            channel=self.session.channel,
            chat_type=self.session.chat_type,
            peer_id=self.session.peer_id,
            conversation_id=self.session.conversation_id,
            thread_id=self.session.thread_id,
            account_id=self.session.account_id,
            label=self.session.label,
            surface=self.session.surface,
            main_key=self.session.main_key,
            direct_scope=self.session.direct_scope,
            status=self.session.status,
            session_metadata=self.session.metadata,
            touch_activity=self.touch_activity,
            reset_policy=(
                self.reset_policy.to_value_object()
                if self.reset_policy is not None
                else None
            ),
            priority=self.priority,
            metadata=self.metadata,
        )

    def to_enqueue_input(self, *, run_id: str) -> EnqueueOrchestrationRunInput:
        return EnqueueOrchestrationRunInput(
            run_id=run_id,
            queue_policy=self.queue_policy,
        )


class ClaimNextRunRequest(BaseModel):
    worker_id: str


class AdvanceRunRequest(BaseModel):
    worker_id: str
    stage: OrchestrationRunStage
    step_increment: int = Field(default=0, ge=0)
    metadata: dict[str, object] = Field(default_factory=dict)

    def to_input(self, *, run_id: str) -> AdvanceOrchestrationRunInput:
        return AdvanceOrchestrationRunInput(
            run_id=run_id,
            worker_id=self.worker_id,
            stage=self.stage,
            step_increment=self.step_increment,
            metadata=self.metadata,
        )


class HeartbeatRunRequest(BaseModel):
    worker_id: str


class RequestDueHeartbeatsRequest(BaseModel):
    idle_seconds: int = Field(..., ge=1)
    agent_id: str | None = None
    limit: int | None = Field(default=None, ge=1)
    reason: str | None = None
    idle_reply: str | None = "HEARTBEAT_OK"
    queue_policy: OrchestrationQueuePolicy = OrchestrationQueuePolicy.JUMP_QUEUE
    priority: int | None = Field(default=None, ge=0)
    max_steps: int = Field(default=1, ge=1)

    def to_input(self) -> RequestDueHeartbeatsInput:
        return RequestDueHeartbeatsInput(
            idle_seconds=self.idle_seconds,
            agent_id=self.agent_id,
            limit=self.limit,
            reason=self.reason,
            idle_reply=self.idle_reply,
            queue_policy=self.queue_policy,
            priority=self.priority,
            max_steps=self.max_steps,
        )


class WaitOnToolRequest(BaseModel):
    worker_id: str
    pending_tool_run_ids: list[str] = Field(default_factory=list)
    reason: str | None = None

    def to_input(self, *, run_id: str) -> WaitOnToolInput:
        return WaitOnToolInput(
            run_id=run_id,
            worker_id=self.worker_id,
            pending_tool_run_ids=tuple(self.pending_tool_run_ids),
            reason=self.reason,
        )


class ResumeRunRequest(BaseModel):
    lane_key: str | None = None
    queue_policy: OrchestrationQueuePolicy | None = None
    priority: int | None = Field(default=None, ge=0)
    reason: str | None = None
    clear_pending_tool_run_ids: bool = True

    def to_input(self, *, run_id: str) -> ResumeOrchestrationRunInput:
        return ResumeOrchestrationRunInput(
            run_id=run_id,
            lane_key=self.lane_key,
            queue_policy=self.queue_policy,
            priority=self.priority,
            reason=self.reason,
            clear_pending_tool_run_ids=self.clear_pending_tool_run_ids,
        )


class CompleteRunRequest(BaseModel):
    worker_id: str
    result_payload: dict[str, object] = Field(default_factory=dict)

    def to_input(self, *, run_id: str) -> CompleteOrchestrationRunInput:
        return CompleteOrchestrationRunInput(
            run_id=run_id,
            worker_id=self.worker_id,
            result_payload=self.result_payload,
        )


class FailRunRequest(BaseModel):
    message: str
    code: str = "orchestration_failed"
    details: dict[str, object] = Field(default_factory=dict)
    worker_id: str | None = None

    def to_input(self, *, run_id: str) -> FailOrchestrationRunInput:
        return FailOrchestrationRunInput(
            run_id=run_id,
            message=self.message,
            code=self.code,
            details=self.details,
            worker_id=self.worker_id,
        )


class InboundInstructionResponse(BaseModel):
    source: str
    content: Any | None = None
    metadata: dict[str, object] = Field(default_factory=dict)

    @classmethod
    def from_dto(cls, dto: InboundInstructionDTO) -> "InboundInstructionResponse":
        return cls(source=dto.source, content=dto.content, metadata=dto.metadata)


class DeliveryTargetResponse(BaseModel):
    interface_name: str
    address: str | None = None
    reply_to: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)

    @classmethod
    def from_dto(cls, dto: DeliveryTargetDTO) -> "DeliveryTargetResponse":
        return cls(
            interface_name=dto.interface_name,
            address=dto.address,
            reply_to=dto.reply_to,
            metadata=dto.metadata,
        )


class OrchestrationErrorResponse(BaseModel):
    message: str
    code: str
    details: dict[str, object] = Field(default_factory=dict)

    @classmethod
    def from_dto(cls, dto: OrchestrationErrorDTO) -> "OrchestrationErrorResponse":
        return cls(message=dto.message, code=dto.code, details=dto.details)


class OrchestrationRunResponse(BaseModel):
    id: str
    status: str
    stage: str
    session_key: str | None = None
    active_session_id: str | None = None
    agent_id: str | None = None
    lane_key: str | None = None
    queue_policy: str
    priority: int
    current_step: int
    max_steps: int
    pending_tool_run_ids: list[str] = Field(default_factory=list)
    waiting_reason: str | None = None
    inbound_instruction: InboundInstructionResponse
    delivery_target: DeliveryTargetResponse | None = None
    result_payload: dict[str, object] | None = None
    error: OrchestrationErrorResponse | None = None
    worker_id: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: str
    updated_at: str
    queued_at: str | None = None
    started_at: str | None = None
    completed_at: str | None = None

    @classmethod
    def from_dto(cls, dto: OrchestrationRunDTO) -> "OrchestrationRunResponse":
        return cls(
            id=dto.id,
            status=dto.status,
            stage=dto.stage,
            session_key=dto.session_key,
            active_session_id=dto.active_session_id,
            agent_id=dto.agent_id,
            lane_key=dto.lane_key,
            queue_policy=dto.queue_policy,
            priority=dto.priority,
            current_step=dto.current_step,
            max_steps=dto.max_steps,
            pending_tool_run_ids=list(dto.pending_tool_run_ids),
            waiting_reason=dto.waiting_reason,
            inbound_instruction=InboundInstructionResponse.from_dto(
                dto.inbound_instruction,
            ),
            delivery_target=(
                DeliveryTargetResponse.from_dto(dto.delivery_target)
                if dto.delivery_target is not None
                else None
            ),
            result_payload=dto.result_payload,
            error=(
                OrchestrationErrorResponse.from_dto(dto.error)
                if dto.error is not None
                else None
            ),
            worker_id=dto.worker_id,
            metadata=dto.metadata,
            created_at=dto.created_at.isoformat(),
            updated_at=dto.updated_at.isoformat(),
            queued_at=dto.queued_at.isoformat() if dto.queued_at is not None else None,
            started_at=dto.started_at.isoformat() if dto.started_at is not None else None,
            completed_at=(
                dto.completed_at.isoformat()
                if dto.completed_at is not None
                else None
            ),
        )
