from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from crxzipple.modules.tool.domain.exceptions import ToolValidationError
from crxzipple.modules.tool.domain.value_objects import ToolWorkerStatus
from crxzipple.shared.domain import AggregateRoot
from crxzipple.shared.domain.events import Event


def _worker_capability_signature(payload: dict[str, Any]) -> tuple[Any, Any]:
    return (
        payload.get("runtime_registry"),
        payload.get("concurrency_policy"),
    )


@dataclass(kw_only=True)
class ToolWorkerRegistration(AggregateRoot[str]):
    status: ToolWorkerStatus = ToolWorkerStatus.ONLINE
    max_in_flight: int = 1
    current_in_flight: int = 0
    capabilities_payload: dict[str, Any] = field(default_factory=dict)
    registered_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    heartbeat_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    lease_expires_at: datetime | None = None

    @classmethod
    def create(
        cls,
        *,
        worker_id: str,
        lease_seconds: int,
        max_in_flight: int = 1,
        capabilities_payload: dict[str, Any] | None = None,
    ) -> ToolWorkerRegistration:
        now = datetime.now(timezone.utc)
        worker = cls(
            id=worker_id,
            max_in_flight=max(int(max_in_flight), 1),
            capabilities_payload=dict(capabilities_payload or {}),
            registered_at=now,
            heartbeat_at=now,
            lease_expires_at=now + timedelta(seconds=lease_seconds),
        )
        worker.record_event(
            Event(
                name="tool.worker.registered",
                payload={
                    "worker_id": worker.id,
                    "max_in_flight": worker.max_in_flight,
                },
            ),
        )
        return worker

    def refresh(
        self,
        *,
        lease_seconds: int,
        max_in_flight: int | None = None,
        capabilities_payload: dict[str, Any] | None = None,
    ) -> None:
        previous_status = self.status
        previous_lease_expires_at = self.lease_expires_at
        previous_max_in_flight = self.max_in_flight
        previous_capability_signature = _worker_capability_signature(
            self.capabilities_payload,
        )
        now = datetime.now(timezone.utc)
        self.status = ToolWorkerStatus.ONLINE
        if max_in_flight is not None:
            self.max_in_flight = max(int(max_in_flight), 1)
        if capabilities_payload is not None:
            self.capabilities_payload = dict(capabilities_payload)
        self.heartbeat_at = now
        self.lease_expires_at = self.heartbeat_at + timedelta(seconds=lease_seconds)
        recovered = previous_status is not ToolWorkerStatus.ONLINE or (
            previous_lease_expires_at is not None
            and previous_lease_expires_at <= now
        )
        if recovered:
            self.record_event(
                Event(
                    name="tool.worker.recovered",
                    payload={
                        "worker_id": self.id,
                        "previous_status": previous_status.value,
                        "previous_lease_expires_at": (
                            previous_lease_expires_at.isoformat()
                            if previous_lease_expires_at is not None
                            else None
                        ),
                        "max_in_flight": self.max_in_flight,
                        "current_in_flight": self.current_in_flight,
                        "lease_expires_at": self.lease_expires_at.isoformat(),
                    },
                ),
            )
        if (
            previous_max_in_flight != self.max_in_flight
            or previous_capability_signature
            != _worker_capability_signature(self.capabilities_payload)
        ):
            self.record_event(
                Event(
                    name="tool.worker.capabilities_updated",
                    payload={
                        "worker_id": self.id,
                        "max_in_flight": self.max_in_flight,
                        "current_in_flight": self.current_in_flight,
                        "lease_expires_at": self.lease_expires_at.isoformat(),
                    },
                ),
            )

    def reserve_slot(self) -> None:
        if self.current_in_flight >= self.max_in_flight:
            raise ToolValidationError("Tool worker has no remaining execution slots.")
        self.current_in_flight += 1

    def release_slot(self) -> None:
        if self.current_in_flight > 0:
            self.current_in_flight -= 1

    def sync_current_in_flight(self, current_in_flight: int) -> None:
        self.current_in_flight = max(int(current_in_flight), 0)

    def mark_stale(self) -> None:
        self.status = ToolWorkerStatus.STALE
        self.current_in_flight = 0
        self.lease_expires_at = None
        self.record_event(
            Event(
                name="tool.worker.stale",
                payload={"worker_id": self.id},
            ),
        )
