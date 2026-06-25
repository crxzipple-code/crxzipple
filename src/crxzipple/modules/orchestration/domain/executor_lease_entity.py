"""Orchestration executor lease aggregate."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from crxzipple.modules.orchestration.domain.exceptions import (
    OrchestrationValidationError,
)
from crxzipple.modules.orchestration.domain.value_objects import (
    OrchestrationExecutorLeaseStatus,
    utcnow,
)
from crxzipple.shared.domain import AggregateRoot
from crxzipple.shared.domain.events import Event

from .entity_payloads import (
    _active_run_ids_from_metadata,
    _optional_datetime_payload,
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
