from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, TypeAlias

from .exceptions import DaemonValidationError

DaemonRole: TypeAlias = Literal["worker", "capability", "host"]
DaemonManagedBy: TypeAlias = Literal["internal", "external"]
DaemonTransport: TypeAlias = Literal["process", "endpoint", "session"]
DaemonReplicaMode: TypeAlias = Literal["singleton", "replicated"]
DaemonStartPolicy: TypeAlias = Literal["eager", "lazy", "attach-only", "ensure"]
DaemonRestartPolicy: TypeAlias = Literal["never", "on-failure", "manual"]

_ALLOWED_ROLES = {"worker", "capability", "host"}
_ALLOWED_MANAGED_BY = {"internal", "external"}
_ALLOWED_TRANSPORTS = {"process", "endpoint", "session"}
_ALLOWED_REPLICA_MODES = {"singleton", "replicated"}
_ALLOWED_START_POLICIES = {"eager", "lazy", "attach-only", "ensure"}
_ALLOWED_RESTART_POLICIES = {"never", "on-failure", "manual"}


def _normalize_key(value: str, *, label: str) -> str:
    normalized = value.strip().lower()
    if not normalized:
        raise DaemonValidationError(f"{label} cannot be empty.")
    return normalized


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_optional_key(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    return normalized or None


def _validate_literal(value: str, *, allowed: set[str], label: str) -> str:
    normalized = value.strip().lower()
    if normalized not in allowed:
        allowed_values = ", ".join(sorted(allowed))
        raise DaemonValidationError(f"{label} must be one of: {allowed_values}.")
    return normalized


def _normalize_keys_tuple(values: tuple[str, ...]) -> tuple[str, ...]:
    normalized: list[str] = []
    for value in values:
        item = value.strip().lower()
        if not item or item in normalized:
            continue
        normalized.append(item)
    return tuple(normalized)


@dataclass(frozen=True, slots=True)
class DaemonServiceSpec:
    key: str
    role: DaemonRole
    managed_by: DaemonManagedBy
    transport: DaemonTransport
    replica_mode: DaemonReplicaMode = "singleton"
    desired_replicas: int = 1
    start_policy: DaemonStartPolicy = "lazy"
    restart_policy: DaemonRestartPolicy = "manual"
    display_name: str | None = None
    service_group: str | None = None
    healthcheck_policy: str | None = None
    match_policy: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "key", _normalize_key(self.key, label="Daemon key"))
        object.__setattr__(
            self,
            "role",
            _validate_literal(self.role, allowed=_ALLOWED_ROLES, label="Daemon role"),
        )
        object.__setattr__(
            self,
            "managed_by",
            _validate_literal(
                self.managed_by,
                allowed=_ALLOWED_MANAGED_BY,
                label="Daemon managed_by",
            ),
        )
        object.__setattr__(
            self,
            "transport",
            _validate_literal(
                self.transport,
                allowed=_ALLOWED_TRANSPORTS,
                label="Daemon transport",
            ),
        )
        object.__setattr__(
            self,
            "replica_mode",
            _validate_literal(
                self.replica_mode,
                allowed=_ALLOWED_REPLICA_MODES,
                label="Daemon replica_mode",
            ),
        )
        object.__setattr__(
            self,
            "start_policy",
            _validate_literal(
                self.start_policy,
                allowed=_ALLOWED_START_POLICIES,
                label="Daemon start_policy",
            ),
        )
        object.__setattr__(
            self,
            "restart_policy",
            _validate_literal(
                self.restart_policy,
                allowed=_ALLOWED_RESTART_POLICIES,
                label="Daemon restart_policy",
            ),
        )
        desired_replicas = max(int(self.desired_replicas), 1)
        if self.replica_mode == "singleton" and desired_replicas != 1:
            raise DaemonValidationError(
                "Singleton daemon services must use desired_replicas=1.",
            )
        object.__setattr__(self, "desired_replicas", desired_replicas)
        object.__setattr__(self, "display_name", _normalize_optional_text(self.display_name))
        object.__setattr__(self, "service_group", _normalize_optional_key(self.service_group))
        object.__setattr__(
            self,
            "healthcheck_policy",
            _normalize_optional_text(self.healthcheck_policy),
        )
        object.__setattr__(self, "match_policy", _normalize_optional_text(self.match_policy))
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True, slots=True)
class DaemonServiceSetSpec:
    key: str
    display_name: str | None = None
    description: str | None = None
    service_keys: tuple[str, ...] = ()
    service_roles: tuple[str, ...] = ()
    service_groups: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "key", _normalize_key(self.key, label="Daemon service set key"))
        object.__setattr__(self, "display_name", _normalize_optional_text(self.display_name))
        object.__setattr__(self, "description", _normalize_optional_text(self.description))
        object.__setattr__(self, "service_keys", _normalize_keys_tuple(self.service_keys))
        object.__setattr__(self, "service_roles", _normalize_keys_tuple(self.service_roles))
        object.__setattr__(self, "service_groups", _normalize_keys_tuple(self.service_groups))
        if not self.service_keys and not self.service_roles and not self.service_groups:
            raise DaemonValidationError(
                "Daemon service sets must target at least one service key, role, or group.",
            )
