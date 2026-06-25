from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import uuid4

from .exceptions import MobileValidationError
from .value_objects import _normalize_name, _normalize_optional_text

MobileDeviceLeaseStatus = str

_ALLOWED_LEASE_STATUSES = {"active", "released", "expired"}


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class MobileDeviceRuntimeState:
    device_name: str
    last_error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        normalized_name = _normalize_name(self.device_name, label="Runtime device name")
        if normalized_name is None:
            raise MobileValidationError("Runtime device name is required.")
        self.device_name = normalized_name
        self.last_error = _normalize_optional_text(self.last_error)

    def clear_error(self) -> None:
        self.last_error = None

    def mark_command_failed(self, reason: str) -> None:
        self.last_error = _normalize_optional_text(reason)

    def next_ref_generation(self) -> int:
        current = self.metadata.get("current_ref_generation")
        try:
            numeric = int(current)
        except (TypeError, ValueError):
            numeric = 0
        return max(numeric + 1, 1)

    def remember_snapshot(
        self,
        *,
        generation: int,
        ref_count: int,
        snapshot_format: str,
        package_name: str | None = None,
        activity_name: str | None = None,
        source_length: int | None = None,
    ) -> None:
        self.metadata["current_ref_generation"] = max(int(generation), 1)
        self.metadata["last_snapshot_ref_count"] = max(int(ref_count), 0)
        self.metadata["last_snapshot_format"] = snapshot_format.strip()
        if source_length is not None:
            self.metadata["last_snapshot_source_length"] = max(int(source_length), 0)
        if package_name is not None:
            self.metadata["last_known_package"] = package_name.strip()
        if activity_name is not None:
            self.metadata["last_known_activity"] = activity_name.strip()
        self.clear_error()

    @property
    def current_ref_generation(self) -> int | None:
        current = self.metadata.get("current_ref_generation")
        try:
            numeric = int(current)
        except (TypeError, ValueError):
            return None
        return max(numeric, 1)

    @property
    def last_known_package(self) -> str | None:
        raw = self.metadata.get("last_known_package")
        return raw.strip() if isinstance(raw, str) and raw.strip() else None

    @property
    def last_known_activity(self) -> str | None:
        raw = self.metadata.get("last_known_activity")
        return raw.strip() if isinstance(raw, str) and raw.strip() else None

    @property
    def last_snapshot_ref_count(self) -> int | None:
        raw = self.metadata.get("last_snapshot_ref_count")
        try:
            numeric = int(raw)
        except (TypeError, ValueError):
            return None
        return max(numeric, 0)

    @property
    def last_snapshot_source_length(self) -> int | None:
        raw = self.metadata.get("last_snapshot_source_length")
        try:
            numeric = int(raw)
        except (TypeError, ValueError):
            return None
        return max(numeric, 0)

    @property
    def metadata_copy(self) -> dict[str, Any]:
        return cast(dict[str, Any], dict(self.metadata))


@dataclass(slots=True)
class MobileDeviceLease:
    id: str
    device_name: str
    owner_kind: str
    owner_id: str
    status: MobileDeviceLeaseStatus = "active"
    acquired_at: datetime = field(default_factory=_utcnow)
    heartbeat_at: datetime | None = None
    expires_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        normalized_id = _normalize_name(self.id, label="Mobile lease id")
        normalized_device = _normalize_name(self.device_name, label="Mobile lease device name")
        normalized_owner_kind = _normalize_name(self.owner_kind, label="Mobile lease owner kind")
        normalized_owner_id = _normalize_name(self.owner_id, label="Mobile lease owner id")
        if normalized_id is None:
            raise MobileValidationError("Mobile lease id is required.")
        if normalized_device is None:
            raise MobileValidationError("Mobile lease device name is required.")
        if normalized_owner_kind is None:
            raise MobileValidationError("Mobile lease owner kind is required.")
        if normalized_owner_id is None:
            raise MobileValidationError("Mobile lease owner id is required.")
        self.id = normalized_id
        self.device_name = normalized_device
        self.owner_kind = normalized_owner_kind
        self.owner_id = normalized_owner_id
        if self.status not in _ALLOWED_LEASE_STATUSES:
            allowed = ", ".join(sorted(_ALLOWED_LEASE_STATUSES))
            raise MobileValidationError(f"Mobile lease status must be one of: {allowed}.")
        self.metadata = dict(self.metadata)
        if self.heartbeat_at is None:
            self.heartbeat_at = self.acquired_at

    @classmethod
    def create(
        cls,
        *,
        device_name: str,
        owner_kind: str,
        owner_id: str,
        ttl_seconds: int | None = None,
        metadata: dict[str, Any] | None = None,
        now: datetime | None = None,
    ) -> "MobileDeviceLease":
        timestamp = now or _utcnow()
        expires_at = (
            timestamp + timedelta(seconds=max(int(ttl_seconds), 1))
            if ttl_seconds is not None
            else None
        )
        return cls(
            id=uuid4().hex,
            device_name=device_name,
            owner_kind=owner_kind,
            owner_id=owner_id,
            acquired_at=timestamp,
            heartbeat_at=timestamp,
            expires_at=expires_at,
            metadata=metadata or {},
        )

    def is_active_at(self, now: datetime | None = None) -> bool:
        if self.status != "active":
            return False
        if self.expires_at is None:
            return True
        return self.expires_at > (now or _utcnow())

    def heartbeat(self, *, ttl_seconds: int | None = None, now: datetime | None = None) -> None:
        if self.status != "active":
            raise MobileValidationError("Only active mobile leases can be heartbeated.")
        timestamp = now or _utcnow()
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
