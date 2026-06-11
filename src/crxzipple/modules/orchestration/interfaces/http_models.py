from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from crxzipple.modules.orchestration.application import (
    AdvanceAssignmentInput,
    CompleteAssignmentInput,
    FailAssignmentInput,
    RequestDueHeartbeatsInput,
    ResumeOrchestrationRunInput,
    SubmitOrchestrationTurnInput,
    WaitAssignmentOnToolInput,
)
from crxzipple.modules.orchestration.domain import (
    OrchestrationQueuePolicy,
    OrchestrationRunStage,
)
from crxzipple.modules.orchestration.interfaces.dto import (
    InboundInstructionDTO,
    OrchestrationErrorDTO,
    OrchestrationRunDTO,
    ReplyTargetDTO,
)
from crxzipple.modules.orchestration.interfaces.shared import (
    build_inbound_instruction,
    build_reply_target,
    build_reset_policy,
    build_session_route_context,
    build_submit_turn_input,
)
from crxzipple.modules.session.domain import DirectSessionScope
from crxzipple.shared.time import (
    format_datetime_utc,
    format_optional_datetime_utc,
)


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


class ReplyTargetRequest(BaseModel):
    interface_name: str
    address: str | None = None
    reply_to: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)

    def to_value_object(self):
        return build_reply_target(
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
    reply_target: ReplyTargetRequest | None = None
    run_id: str | None = None
    queue_policy: OrchestrationQueuePolicy = OrchestrationQueuePolicy.FIFO
    priority: int = 100
    max_steps: int = 99
    metadata: dict[str, object] = Field(default_factory=dict)
    enqueue: bool = False
    touch_activity: bool = True
    reset_policy: ResetPolicyRequest | None = None

    def to_submit_input(self) -> SubmitOrchestrationTurnInput:
        return build_submit_turn_input(
            source=self.inbound_instruction.source,
            content=self.inbound_instruction.content,
            inbound_metadata=self.inbound_instruction.metadata,
            agent_id=self.session.agent_id,
            llm_id=self.llm_id,
            reply_interface=(
                self.reply_target.interface_name
                if self.reply_target is not None
                else None
            ),
            reply_address=(
                self.reply_target.address
                if self.reply_target is not None
                else None
            ),
            reply_to=(
                self.reply_target.reply_to
                if self.reply_target is not None
                else None
            ),
            reply_metadata=(
                self.reply_target.metadata
                if self.reply_target is not None
                else None
            ),
            run_id=self.run_id,
            queue_policy=self.queue_policy,
            priority=self.priority,
            max_steps=self.max_steps,
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
            metadata=self.metadata,
        )


class ClaimNextAssignmentRequest(BaseModel):
    worker_id: str


class AssignmentWorkerRequest(BaseModel):
    worker_id: str


class AdvanceAssignmentRequest(BaseModel):
    worker_id: str
    stage: OrchestrationRunStage
    step_increment: int = Field(default=0, ge=0)
    metadata: dict[str, object] = Field(default_factory=dict)
    execution_payload: dict[str, object] = Field(default_factory=dict)

    def to_input(self, *, run_id: str) -> AdvanceAssignmentInput:
        return AdvanceAssignmentInput(
            run_id=run_id,
            worker_id=self.worker_id,
            stage=self.stage,
            step_increment=self.step_increment,
            metadata=self.metadata,
            execution_payload=self.execution_payload,
        )


class HeartbeatAssignmentRequest(BaseModel):
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


class WaitAssignmentOnToolRequest(BaseModel):
    worker_id: str
    pending_tool_run_ids: list[str] = Field(default_factory=list)
    reason: str | None = None

    def to_input(self, *, run_id: str) -> WaitAssignmentOnToolInput:
        return WaitAssignmentOnToolInput(
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


class CompleteAssignmentRequest(BaseModel):
    worker_id: str
    result_payload: dict[str, object] = Field(default_factory=dict)
    execution_payload: dict[str, object] = Field(default_factory=dict)

    def to_input(self, *, run_id: str) -> CompleteAssignmentInput:
        return CompleteAssignmentInput(
            run_id=run_id,
            worker_id=self.worker_id,
            result_payload=self.result_payload,
            execution_payload=self.execution_payload,
        )


class FailAssignmentRequest(BaseModel):
    message: str
    code: str = "orchestration_failed"
    details: dict[str, object] = Field(default_factory=dict)
    worker_id: str | None = None

    def to_input(self, *, run_id: str) -> FailAssignmentInput:
        return FailAssignmentInput(
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


class ReplyTargetResponse(BaseModel):
    interface_name: str
    address: str | None = None
    reply_to: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)

    @classmethod
    def from_dto(cls, dto: ReplyTargetDTO) -> "ReplyTargetResponse":
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
    pending_approval_request: dict[str, object] | None = None
    last_approval_resolution: dict[str, object] | None = None
    recovery_contract: dict[str, object] | None = None
    inbound_instruction: InboundInstructionResponse
    reply_target: ReplyTargetResponse | None = None
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
            pending_approval_request=dto.pending_approval_request,
            last_approval_resolution=dto.last_approval_resolution,
            recovery_contract=dto.recovery_contract,
            inbound_instruction=InboundInstructionResponse.from_dto(
                dto.inbound_instruction,
            ),
            reply_target=(
                ReplyTargetResponse.from_dto(dto.reply_target)
                if dto.reply_target is not None
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
            created_at=format_datetime_utc(dto.created_at),
            updated_at=format_datetime_utc(dto.updated_at),
            queued_at=format_optional_datetime_utc(dto.queued_at),
            started_at=format_optional_datetime_utc(dto.started_at),
            completed_at=format_optional_datetime_utc(dto.completed_at),
        )
