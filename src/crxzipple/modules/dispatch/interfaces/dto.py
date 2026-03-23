from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from crxzipple.modules.dispatch.domain import DispatchErrorPayload, DispatchTask


@dataclass(frozen=True, slots=True)
class DispatchErrorDTO:
    message: str
    code: str
    details: dict[str, object]

    @classmethod
    def from_value_object(cls, payload: DispatchErrorPayload) -> "DispatchErrorDTO":
        return cls(
            message=payload.message,
            code=payload.code,
            details=dict(payload.details),
        )


@dataclass(frozen=True, slots=True)
class DispatchTaskDTO:
    id: str
    owner_kind: str
    owner_id: str
    lane_key: str | None
    status: str
    policy: str
    priority: int
    payload_ref: str | None
    metadata: dict[str, object]
    waiting_reason: str | None
    error: DispatchErrorDTO | None
    claimed_by: str | None
    claim_token: str | None
    created_at: datetime
    updated_at: datetime
    queued_at: datetime | None
    claimed_at: datetime | None
    heartbeat_at: datetime | None
    lease_expires_at: datetime | None
    completed_at: datetime | None

    @classmethod
    def from_entity(cls, task: DispatchTask) -> "DispatchTaskDTO":
        return cls(
            id=task.id,
            owner_kind=task.owner_kind,
            owner_id=task.owner_id,
            lane_key=task.lane_key,
            status=task.status.value,
            policy=task.policy.value,
            priority=task.priority,
            payload_ref=task.payload_ref,
            metadata=dict(task.metadata),
            waiting_reason=task.waiting_reason,
            error=(
                DispatchErrorDTO.from_value_object(task.error)
                if task.error is not None
                else None
            ),
            claimed_by=task.claimed_by,
            claim_token=task.claim_token,
            created_at=task.created_at,
            updated_at=task.updated_at,
            queued_at=task.queued_at,
            claimed_at=task.claimed_at,
            heartbeat_at=task.heartbeat_at,
            lease_expires_at=task.lease_expires_at,
            completed_at=task.completed_at,
        )
