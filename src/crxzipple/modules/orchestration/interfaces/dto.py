from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from crxzipple.modules.llm.interfaces.dto import LlmMessageDTO, ToolSchemaDTO
from crxzipple.modules.orchestration.application import PromptSurfacePreview
from crxzipple.modules.orchestration.domain import (
    InboundInstruction,
    OrchestrationErrorPayload,
    OrchestrationExecutorLease,
    OrchestrationRun,
    ReplyTarget,
)


@dataclass(frozen=True, slots=True)
class InboundInstructionDTO:
    source: str
    content: Any | None
    metadata: dict[str, object]

    @classmethod
    def from_value_object(
        cls,
        instruction: InboundInstruction,
    ) -> "InboundInstructionDTO":
        return cls(
            source=instruction.source,
            content=instruction.content,
            metadata=dict(instruction.metadata),
        )


@dataclass(frozen=True, slots=True)
class ReplyTargetDTO:
    interface_name: str
    address: str | None
    reply_to: str | None
    metadata: dict[str, object]

    @classmethod
    def from_value_object(cls, target: ReplyTarget) -> "ReplyTargetDTO":
        return cls(
            interface_name=target.interface_name,
            address=target.address,
            reply_to=target.reply_to,
            metadata=dict(target.metadata),
        )

@dataclass(frozen=True, slots=True)
class OrchestrationErrorDTO:
    message: str
    code: str
    details: dict[str, object]

    @classmethod
    def from_value_object(
        cls,
        payload: OrchestrationErrorPayload,
    ) -> "OrchestrationErrorDTO":
        return cls(
            message=payload.message,
            code=payload.code,
            details=dict(payload.details),
        )


@dataclass(frozen=True, slots=True)
class OrchestrationRunDTO:
    id: str
    status: str
    stage: str
    session_key: str | None
    active_session_id: str | None
    agent_id: str | None
    lane_key: str | None
    queue_policy: str
    priority: int
    current_step: int
    max_steps: int
    pending_tool_run_ids: tuple[str, ...]
    waiting_reason: str | None
    inbound_instruction: InboundInstructionDTO
    reply_target: ReplyTargetDTO | None
    result_payload: dict[str, object] | None
    error: OrchestrationErrorDTO | None
    worker_id: str | None
    metadata: dict[str, object]
    created_at: datetime
    updated_at: datetime
    queued_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None

    @classmethod
    def from_entity(cls, run: OrchestrationRun) -> "OrchestrationRunDTO":
        return cls(
            id=run.id,
            status=run.status.value,
            stage=run.stage.value,
            session_key=run.session_key,
            active_session_id=run.active_session_id,
            agent_id=run.agent_id,
            lane_key=run.lane_key,
            queue_policy=run.queue_policy.value,
            priority=run.priority,
            current_step=run.current_step,
            max_steps=run.max_steps,
            pending_tool_run_ids=tuple(run.pending_tool_run_ids),
            waiting_reason=run.waiting_reason,
            inbound_instruction=InboundInstructionDTO.from_value_object(
                run.inbound_instruction,
            ),
            reply_target=(
                ReplyTargetDTO.from_value_object(run.reply_target)
                if run.reply_target is not None
                else None
            ),
            result_payload=(
                dict(run.result_payload)
                if run.result_payload is not None
                else None
            ),
            error=(
                OrchestrationErrorDTO.from_value_object(run.error)
                if run.error is not None
                else None
            ),
            worker_id=run.worker_id,
            metadata=dict(run.metadata),
            created_at=run.created_at,
            updated_at=run.updated_at,
            queued_at=run.queued_at,
            started_at=run.started_at,
            completed_at=run.completed_at,
        )


@dataclass(frozen=True, slots=True)
class OrchestrationExecutorLeaseDTO:
    worker_id: str
    status: str
    effective_status: str
    expired: bool
    counts_toward_capacity: bool
    max_inflight_assignments: int
    inflight_assignment_count: int
    available_assignment_slots: int
    metadata: dict[str, object]
    created_at: datetime
    updated_at: datetime
    last_heartbeat_at: datetime
    lease_expires_at: datetime | None

    @classmethod
    def from_entity(
        cls,
        lease: OrchestrationExecutorLease,
    ) -> "OrchestrationExecutorLeaseDTO":
        expired = lease.is_expired()
        effective_status = lease.effective_status().value
        counts_toward_capacity = lease.counts_toward_capacity()
        return cls(
            worker_id=lease.worker_id,
            status=lease.status.value,
            effective_status=effective_status,
            expired=expired,
            counts_toward_capacity=counts_toward_capacity,
            max_inflight_assignments=lease.max_inflight_assignments,
            inflight_assignment_count=lease.inflight_assignment_count,
            available_assignment_slots=lease.available_assignment_slots(),
            metadata=dict(lease.metadata),
            created_at=lease.created_at,
            updated_at=lease.updated_at,
            last_heartbeat_at=lease.last_heartbeat_at,
            lease_expires_at=lease.lease_expires_at,
        )


@dataclass(frozen=True, slots=True)
class PromptSurfacePreviewDTO:
    run_id: str
    llm_id: str
    mode: str
    messages: tuple[LlmMessageDTO, ...]
    tool_schemas: tuple[ToolSchemaDTO, ...]
    prompt_report: dict[str, object] | None

    @classmethod
    def from_value(
        cls,
        *,
        run_id: str,
        preview: PromptSurfacePreview,
    ) -> "PromptSurfacePreviewDTO":
        return cls(
            run_id=run_id,
            llm_id=preview.llm_id,
            mode=preview.mode.value,
            messages=tuple(
                LlmMessageDTO.from_value(message)
                for message in preview.messages
            ),
            tool_schemas=tuple(
                ToolSchemaDTO.from_value(schema)
                for schema in preview.tool_schemas
            ),
            prompt_report=(
                preview.prompt_report.to_payload()
                if preview.prompt_report is not None
                else None
            ),
        )
