from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from crxzipple.modules.dispatch.domain.exceptions import DispatchValidationError
from crxzipple.modules.dispatch.domain.value_objects import (
    DispatchErrorPayload,
    DispatchPolicy,
    DispatchTaskStatus,
    utcnow,
    validate_lease_seconds,
)
from crxzipple.shared.domain import AggregateRoot
from crxzipple.shared.domain.events import Event


@dataclass(kw_only=True)
class DispatchTask(AggregateRoot[str]):
    owner_kind: str
    owner_id: str
    lane_key: str | None = None
    status: DispatchTaskStatus = DispatchTaskStatus.CREATED
    policy: DispatchPolicy = DispatchPolicy.FIFO
    priority: int = 100
    payload_ref: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)
    waiting_reason: str | None = None
    error: DispatchErrorPayload | None = None
    claimed_by: str | None = None
    claim_token: str | None = None
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime = field(default_factory=utcnow)
    queued_at: datetime | None = None
    claimed_at: datetime | None = None
    heartbeat_at: datetime | None = None
    lease_expires_at: datetime | None = None
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise DispatchValidationError("Dispatch task id cannot be empty.")
        self.owner_kind = self.owner_kind.strip()
        if not self.owner_kind:
            raise DispatchValidationError("Dispatch task owner_kind cannot be empty.")
        self.owner_id = self.owner_id.strip()
        if not self.owner_id:
            raise DispatchValidationError("Dispatch task owner_id cannot be empty.")
        if self.lane_key is not None:
            self.lane_key = self.lane_key.strip() or None
        if self.payload_ref is not None:
            self.payload_ref = self.payload_ref.strip() or None
        if self.waiting_reason is not None:
            self.waiting_reason = self.waiting_reason.strip() or None
        if self.claimed_by is not None:
            self.claimed_by = self.claimed_by.strip() or None
        if self.claim_token is not None:
            self.claim_token = self.claim_token.strip() or None
        if self.priority < 0:
            raise DispatchValidationError("Dispatch task priority cannot be negative.")
        if not isinstance(self.status, DispatchTaskStatus):
            self.status = DispatchTaskStatus(str(self.status))
        if not isinstance(self.policy, DispatchPolicy):
            self.policy = DispatchPolicy(str(self.policy))
        self.metadata = dict(self.metadata)

    @classmethod
    def create(
        cls,
        *,
        task_id: str,
        owner_kind: str,
        owner_id: str,
        lane_key: str | None = None,
        policy: DispatchPolicy = DispatchPolicy.FIFO,
        priority: int = 100,
        payload_ref: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> "DispatchTask":
        task = cls(
            id=task_id,
            owner_kind=owner_kind,
            owner_id=owner_id,
            lane_key=lane_key,
            policy=policy,
            priority=priority,
            payload_ref=payload_ref,
            metadata=metadata or {},
        )
        task.record_event(
            Event(
                name="dispatch.task.created",
                payload={
                    "task_id": task.id,
                    "owner_kind": task.owner_kind,
                    "owner_id": task.owner_id,
                    "lane_key": task.lane_key,
                },
            ),
        )
        return task

    def enqueue(
        self,
        *,
        lane_key: str | None = None,
        policy: DispatchPolicy | None = None,
        priority: int | None = None,
        queued_at: datetime | None = None,
    ) -> None:
        if priority is not None and priority < 0:
            raise DispatchValidationError("Dispatch task priority cannot be negative.")
        if lane_key is not None:
            normalized_lane_key = lane_key.strip()
            if not normalized_lane_key:
                raise DispatchValidationError("Dispatch task lane_key cannot be empty.")
            self.lane_key = normalized_lane_key
        if policy is not None:
            self.policy = policy
        if priority is not None:
            self.priority = priority
        timestamp = queued_at or utcnow()
        self.status = DispatchTaskStatus.QUEUED
        self.waiting_reason = None
        self.error = None
        self._clear_claim_state()
        self.queued_at = timestamp
        self.updated_at = timestamp
        self.completed_at = None
        self.record_event(
            Event(
                name="dispatch.task.queued",
                payload={
                    "task_id": self.id,
                    "owner_kind": self.owner_kind,
                    "owner_id": self.owner_id,
                    "lane_key": self.lane_key,
                    "priority": self.priority,
                    "policy": self.policy.value,
                },
            ),
        )

    def claim(
        self,
        *,
        worker_id: str,
        claim_token: str,
        lease_seconds: int | None = None,
        claimed_at: datetime | None = None,
    ) -> None:
        normalized_worker_id = worker_id.strip()
        if not normalized_worker_id:
            raise DispatchValidationError("Dispatch worker_id cannot be empty.")
        normalized_claim_token = claim_token.strip()
        if not normalized_claim_token:
            raise DispatchValidationError("Dispatch claim_token cannot be empty.")
        timestamp = claimed_at or utcnow()
        self.status = DispatchTaskStatus.CLAIMED
        self.claimed_by = normalized_worker_id
        self.claim_token = normalized_claim_token
        self.claimed_at = timestamp
        self.heartbeat_at = timestamp
        self.lease_expires_at = (
            timestamp + timedelta(seconds=validate_lease_seconds(lease_seconds))
            if lease_seconds is not None
            else None
        )
        self.updated_at = timestamp
        self.waiting_reason = None
        self.error = None
        self.completed_at = None
        self.record_event(
            Event(
                name="dispatch.task.claimed",
                payload={
                    "task_id": self.id,
                    "worker_id": self.claimed_by,
                    "claim_token": self.claim_token,
                    "lane_key": self.lane_key,
                    "lease_expires_at": (
                        self.lease_expires_at.isoformat()
                        if self.lease_expires_at is not None
                        else None
                    ),
                },
            ),
        )

    def heartbeat(
        self,
        *,
        worker_id: str,
        lease_seconds: int,
        claim_token: str | None = None,
        now: datetime | None = None,
    ) -> None:
        if self.status is not DispatchTaskStatus.CLAIMED:
            raise DispatchValidationError(
                "Only claimed dispatch tasks can be heartbeated.",
            )
        normalized_worker_id = worker_id.strip()
        if not normalized_worker_id:
            raise DispatchValidationError("Dispatch worker_id cannot be empty.")
        if self.claimed_by != normalized_worker_id:
            raise DispatchValidationError(
                "Dispatch task is already owned by a different worker.",
            )
        if claim_token is not None:
            normalized_claim_token = claim_token.strip()
            if not normalized_claim_token:
                raise DispatchValidationError("Dispatch claim_token cannot be empty.")
            if self.claim_token is not None and self.claim_token != normalized_claim_token:
                raise DispatchValidationError(
                    "Dispatch task claim_token does not match the current owner.",
                )
        timestamp = now or utcnow()
        validated_lease_seconds = validate_lease_seconds(lease_seconds)
        self.heartbeat_at = timestamp
        self.lease_expires_at = timestamp + timedelta(seconds=validated_lease_seconds)
        self.updated_at = timestamp
        self.record_event(
            Event(
                name="dispatch.task.heartbeated",
                payload={
                    "task_id": self.id,
                    "worker_id": self.claimed_by,
                    "lease_expires_at": self.lease_expires_at.isoformat(),
                },
            ),
        )

    def wait(self, *, reason: str | None = None, now: datetime | None = None) -> None:
        timestamp = now or utcnow()
        self.status = DispatchTaskStatus.WAITING
        self.waiting_reason = reason.strip() if reason is not None and reason.strip() else None
        self.error = None
        self._clear_claim_state()
        self.updated_at = timestamp
        self.record_event(
            Event(
                name="dispatch.task.waiting",
                payload={
                    "task_id": self.id,
                    "lane_key": self.lane_key,
                    "reason": self.waiting_reason,
                },
            ),
        )

    def requeue(
        self,
        *,
        policy: DispatchPolicy | None = None,
        priority: int | None = None,
        reason: str | None = None,
        now: datetime | None = None,
    ) -> None:
        if priority is not None and priority < 0:
            raise DispatchValidationError("Dispatch task priority cannot be negative.")
        if policy is not None:
            self.policy = policy
        if priority is not None:
            self.priority = priority
        timestamp = now or utcnow()
        self.status = DispatchTaskStatus.QUEUED
        self.waiting_reason = None
        self.error = None
        self._clear_claim_state()
        self.queued_at = timestamp
        self.updated_at = timestamp
        self.record_event(
            Event(
                name="dispatch.task.requeued",
                payload={
                    "task_id": self.id,
                    "owner_kind": self.owner_kind,
                    "owner_id": self.owner_id,
                    "lane_key": self.lane_key,
                    "policy": self.policy.value,
                    "priority": self.priority,
                    "reason": reason.strip() if reason is not None and reason.strip() else None,
                },
            ),
        )

    def recover_abandoned(
        self,
        *,
        reason: str,
        now: datetime | None = None,
    ) -> None:
        normalized_reason = reason.strip()
        if not normalized_reason:
            raise DispatchValidationError("Dispatch recovery reason cannot be empty.")
        timestamp = now or utcnow()
        self.status = DispatchTaskStatus.QUEUED
        self.waiting_reason = None
        self.error = None
        self._clear_claim_state()
        self.queued_at = timestamp
        self.updated_at = timestamp
        self.record_event(
            Event(
                name="dispatch.task.recovered",
                payload={
                    "task_id": self.id,
                    "owner_kind": self.owner_kind,
                    "owner_id": self.owner_id,
                    "lane_key": self.lane_key,
                    "reason": normalized_reason,
                },
            ),
        )

    def complete(self, *, now: datetime | None = None) -> None:
        timestamp = now or utcnow()
        self.status = DispatchTaskStatus.COMPLETED
        self.updated_at = timestamp
        self.completed_at = timestamp
        self.waiting_reason = None
        self.error = None
        self._clear_claim_state()
        self.record_event(
            Event(
                name="dispatch.task.completed",
                payload={
                    "task_id": self.id,
                    "lane_key": self.lane_key,
                },
            ),
        )

    def cancel(self, *, reason: str | None = None, now: datetime | None = None) -> None:
        timestamp = now or utcnow()
        self.status = DispatchTaskStatus.CANCELLED
        self.updated_at = timestamp
        self.completed_at = timestamp
        self.waiting_reason = reason.strip() if reason is not None and reason.strip() else None
        self.error = None
        self._clear_claim_state()
        self.record_event(
            Event(
                name="dispatch.task.cancelled",
                payload={
                    "task_id": self.id,
                    "lane_key": self.lane_key,
                    "reason": self.waiting_reason,
                },
            ),
        )

    def fail(
        self,
        *,
        message: str,
        code: str = "dispatch_failed",
        details: dict[str, object] | None = None,
        now: datetime | None = None,
    ) -> None:
        timestamp = now or utcnow()
        self.status = DispatchTaskStatus.FAILED
        self.error = DispatchErrorPayload(
            message=message,
            code=code,
            details=details or {},
        )
        self.updated_at = timestamp
        self.completed_at = timestamp
        self._clear_claim_state()
        self.record_event(
            Event(
                name="dispatch.task.failed",
                payload={
                    "task_id": self.id,
                    "lane_key": self.lane_key,
                    "code": self.error.code,
                },
            ),
        )

    def _clear_claim_state(self) -> None:
        self.claimed_by = None
        self.claim_token = None
        self.claimed_at = None
        self.heartbeat_at = None
        self.lease_expires_at = None
