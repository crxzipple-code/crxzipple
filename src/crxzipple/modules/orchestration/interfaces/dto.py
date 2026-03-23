from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from crxzipple.modules.orchestration.domain import (
    DeliveryTarget,
    InboundInstruction,
    OrchestrationErrorPayload,
    OrchestrationRun,
)


@dataclass(frozen=True, slots=True)
class InboundInstructionDTO:
    source: str
    content: str | None
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
class DeliveryTargetDTO:
    interface_name: str
    address: str | None
    reply_to: str | None
    metadata: dict[str, object]

    @classmethod
    def from_value_object(cls, target: DeliveryTarget) -> "DeliveryTargetDTO":
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
    bulk_key: str | None
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
    delivery_target: DeliveryTargetDTO | None
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
            bulk_key=run.bulk_key,
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
            delivery_target=(
                DeliveryTargetDTO.from_value_object(run.delivery_target)
                if run.delivery_target is not None
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
