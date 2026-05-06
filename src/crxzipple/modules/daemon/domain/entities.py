from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, TypeAlias
from uuid import uuid4

from .exceptions import DaemonValidationError
from .value_objects import _normalize_key, _normalize_optional_text

DaemonStatus: TypeAlias = Literal[
    "stopped",
    "starting",
    "ready",
    "degraded",
    "stopping",
    "failed",
]
DaemonLeaseStatus: TypeAlias = Literal["active", "released", "expired"]

_ALLOWED_DAEMON_STATUSES = {
    "stopped",
    "starting",
    "ready",
    "degraded",
    "stopping",
    "failed",
}
_ALLOWED_LEASE_STATUSES = {"active", "released", "expired"}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class DaemonInstance:
    id: str
    service_key: str
    status: DaemonStatus = "stopped"
    worker_id: str | None = None
    pid: int | None = None
    endpoint: str | None = None
    started_at: datetime | None = None
    last_healthcheck_at: datetime | None = None
    last_error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.id = _normalize_key(self.id, label="Daemon instance id")
        self.service_key = _normalize_key(self.service_key, label="Daemon service key")
        self.worker_id = _normalize_optional_text(self.worker_id)
        self.endpoint = _normalize_optional_text(self.endpoint)
        self.last_error = _normalize_optional_text(self.last_error)
        if self.pid is not None and int(self.pid) < 1:
            raise DaemonValidationError("Daemon pid must be greater than or equal to 1.")
        if self.status not in _ALLOWED_DAEMON_STATUSES:
            allowed = ", ".join(sorted(_ALLOWED_DAEMON_STATUSES))
            raise DaemonValidationError(f"Daemon status must be one of: {allowed}.")
        self.metadata = dict(self.metadata)

    @classmethod
    def create(
        cls,
        *,
        service_key: str,
        worker_id: str | None = None,
        pid: int | None = None,
        endpoint: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "DaemonInstance":
        return cls(
            id=uuid4().hex,
            service_key=service_key,
            status="starting",
            worker_id=worker_id,
            pid=pid,
            endpoint=endpoint,
            started_at=utcnow(),
            metadata=metadata or {},
        )

    def mark_ready(
        self,
        *,
        pid: int | None = None,
        endpoint: str | None = None,
        now: datetime | None = None,
    ) -> None:
        self.status = "ready"
        if pid is not None:
            self.pid = int(pid)
        if endpoint is not None:
            self.endpoint = _normalize_optional_text(endpoint)
        timestamp = now or utcnow()
        self.started_at = self.started_at or timestamp
        self.last_healthcheck_at = timestamp
        self.last_error = None

    def mark_degraded(self, reason: str, *, now: datetime | None = None) -> None:
        self.status = "degraded"
        self.last_error = _normalize_optional_text(reason)
        self.last_healthcheck_at = now or utcnow()

    def mark_failed(self, reason: str, *, now: datetime | None = None) -> None:
        self.status = "failed"
        self.last_error = _normalize_optional_text(reason)
        self.last_healthcheck_at = now or utcnow()

    def mark_stopping(self) -> None:
        self.status = "stopping"

    def mark_stopped(self, *, now: datetime | None = None) -> None:
        self.status = "stopped"
        self.last_healthcheck_at = now or utcnow()


@dataclass(slots=True)
class DaemonLease:
    id: str
    service_key: str
    instance_id: str
    owner_kind: str
    owner_id: str
    status: DaemonLeaseStatus = "active"
    acquired_at: datetime = field(default_factory=utcnow)
    heartbeat_at: datetime | None = None
    expires_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.id = _normalize_key(self.id, label="Daemon lease id")
        self.service_key = _normalize_key(self.service_key, label="Daemon service key")
        self.instance_id = _normalize_key(self.instance_id, label="Daemon instance id")
        self.owner_kind = _normalize_key(self.owner_kind, label="Daemon lease owner_kind")
        self.owner_id = _normalize_key(self.owner_id, label="Daemon lease owner_id")
        if self.status not in _ALLOWED_LEASE_STATUSES:
            allowed = ", ".join(sorted(_ALLOWED_LEASE_STATUSES))
            raise DaemonValidationError(f"Daemon lease status must be one of: {allowed}.")
        self.metadata = dict(self.metadata)
        if self.heartbeat_at is None:
            self.heartbeat_at = self.acquired_at

    @classmethod
    def create(
        cls,
        *,
        service_key: str,
        instance_id: str,
        owner_kind: str,
        owner_id: str,
        ttl_seconds: int | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "DaemonLease":
        timestamp = utcnow()
        expires_at = (
            timestamp + timedelta(seconds=max(int(ttl_seconds), 1))
            if ttl_seconds is not None
            else None
        )
        return cls(
            id=uuid4().hex,
            service_key=service_key,
            instance_id=instance_id,
            owner_kind=owner_kind,
            owner_id=owner_id,
            acquired_at=timestamp,
            heartbeat_at=timestamp,
            expires_at=expires_at,
            metadata=metadata or {},
        )

    def heartbeat(self, *, ttl_seconds: int | None = None, now: datetime | None = None) -> None:
        if self.status != "active":
            raise DaemonValidationError("Only active daemon leases can be heartbeated.")
        timestamp = now or utcnow()
        self.heartbeat_at = timestamp
        if ttl_seconds is not None:
            self.expires_at = timestamp + timedelta(seconds=max(int(ttl_seconds), 1))

    def release(self) -> None:
        if self.status != "active":
            return
        self.status = "released"

    def expire(self) -> None:
        if self.status != "active":
            return
        self.status = "expired"
