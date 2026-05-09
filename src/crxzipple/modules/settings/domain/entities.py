from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from crxzipple.modules.settings.domain.exceptions import SettingsValidationError
from crxzipple.modules.settings.domain.value_objects import (
    SettingsActionStatus,
    SettingsResourceStatus,
    SettingsValidationResult,
    SettingsVersionStatus,
    format_optional_datetime,
    normalize_datetime,
    utcnow,
)
from crxzipple.shared.domain import AggregateRoot
from crxzipple.shared.domain.events import Event
from crxzipple.shared.settings import ConfigResolution, ConfigSource, SettingsResourceRef


JsonObject = dict[str, Any]


def _normalize_text(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise SettingsValidationError(f"{field_name} is required.")
    return normalized


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


@dataclass(kw_only=True)
class SettingsResource(AggregateRoot[str]):
    resource_kind: str
    owner_module: str
    scope: str = "global"
    display_name: str | None = None
    status: SettingsResourceStatus = SettingsResourceStatus.ACTIVE
    active_version_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        self.id = _normalize_text(self.id, field_name="resource id")
        self.resource_kind = _normalize_text(self.resource_kind, field_name="resource kind")
        self.owner_module = _normalize_text(self.owner_module, field_name="owner module")
        self.scope = _normalize_text(self.scope, field_name="scope")
        self.status = _coerce_resource_status(self.status)
        self.display_name = _normalize_optional_text(self.display_name)
        self.active_version_id = _normalize_optional_text(self.active_version_id)
        self.created_at = normalize_datetime(self.created_at)
        self.updated_at = normalize_datetime(self.updated_at) if self.updated_at is not None else None

    @property
    def enabled(self) -> bool:
        return self.status is SettingsResourceStatus.ACTIVE

    def ref(self) -> SettingsResourceRef:
        return SettingsResourceRef(
            resource_id=self.id,
            resource_kind=self.resource_kind,
            owner_module=self.owner_module,
            scope=self.scope,
            display_name=self.display_name,
            metadata=self.metadata,
        )

    def enable(self) -> bool:
        if self.status is SettingsResourceStatus.ACTIVE:
            return False
        self.status = SettingsResourceStatus.ACTIVE
        self.updated_at = utcnow()
        self.record_event(
            Event(
                name="settings.resource_enabled",
                payload={"resource_id": self.id, "resource_kind": self.resource_kind},
            ),
        )
        return True

    def disable(self) -> bool:
        if self.status is SettingsResourceStatus.DISABLED:
            return False
        self.status = SettingsResourceStatus.DISABLED
        self.updated_at = utcnow()
        self.record_event(
            Event(
                name="settings.resource_disabled",
                payload={"resource_id": self.id, "resource_kind": self.resource_kind},
            ),
        )
        return True

    def publish(self, version_id: str) -> None:
        self.active_version_id = _normalize_text(version_id, field_name="version id")
        self.updated_at = utcnow()
        self.record_event(
            Event(
                name="settings.resource_published",
                payload={
                    "resource_id": self.id,
                    "resource_kind": self.resource_kind,
                    "version_id": self.active_version_id,
                },
            ),
        )

    def to_payload(self) -> JsonObject:
        return {
            "id": self.id,
            "resource_kind": self.resource_kind,
            "owner_module": self.owner_module,
            "scope": self.scope,
            "display_name": self.display_name,
            "status": self.status.value,
            "enabled": self.enabled,
            "active_version_id": self.active_version_id,
            "metadata": dict(self.metadata),
            "created_at": format_optional_datetime(self.created_at),
            "updated_at": format_optional_datetime(self.updated_at),
        }


@dataclass(kw_only=True)
class SettingsResourceVersion(AggregateRoot[str]):
    resource_id: str
    resource_kind: str
    payload: Mapping[str, Any]
    version_number: int
    status: SettingsVersionStatus = SettingsVersionStatus.DRAFT
    validation: SettingsValidationResult = field(default_factory=SettingsValidationResult)
    source: str = "manual"
    reason: str | None = None
    created_by: str | None = None
    created_at: datetime = field(default_factory=utcnow)
    published_at: datetime | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.id = _normalize_text(self.id, field_name="version id")
        self.resource_id = _normalize_text(self.resource_id, field_name="resource id")
        self.resource_kind = _normalize_text(self.resource_kind, field_name="resource kind")
        if self.version_number <= 0:
            raise SettingsValidationError("version_number must be positive.")
        self.payload = dict(self.payload)
        self.status = _coerce_version_status(self.status)
        self.source = _normalize_text(self.source, field_name="source")
        self.reason = _normalize_optional_text(self.reason)
        self.created_by = _normalize_optional_text(self.created_by)
        self.created_at = normalize_datetime(self.created_at)
        self.published_at = (
            normalize_datetime(self.published_at)
            if self.published_at is not None
            else None
        )

    def publish(self) -> None:
        if not self.validation.ok:
            self.status = SettingsVersionStatus.FAILED_VALIDATION
            raise SettingsValidationError("cannot publish a version with validation errors.")
        self.status = SettingsVersionStatus.PUBLISHED
        self.published_at = utcnow()
        self.record_event(
            Event(
                name="settings.version_published",
                payload={
                    "resource_id": self.resource_id,
                    "resource_kind": self.resource_kind,
                    "version_id": self.id,
                },
            ),
        )

    def supersede(self) -> None:
        if self.status is SettingsVersionStatus.PUBLISHED:
            self.status = SettingsVersionStatus.SUPERSEDED

    def to_source(self, *, resource: SettingsResourceRef) -> ConfigSource:
        return ConfigSource(
            source_id=f"version:{self.id}",
            source_kind="published_version",
            resource=resource,
            version_id=self.id,
            value=dict(self.payload),
            metadata={
                "version_number": self.version_number,
                "source": self.source,
                "reason": self.reason,
            },
        )

    def to_payload(self) -> JsonObject:
        return {
            "id": self.id,
            "resource_id": self.resource_id,
            "resource_kind": self.resource_kind,
            "payload": dict(self.payload),
            "version_number": self.version_number,
            "status": self.status.value,
            "validation": self.validation.to_payload(),
            "source": self.source,
            "reason": self.reason,
            "created_by": self.created_by,
            "created_at": format_optional_datetime(self.created_at),
            "published_at": format_optional_datetime(self.published_at),
            "metadata": dict(self.metadata),
        }


@dataclass(kw_only=True)
class SettingsOverride(AggregateRoot[str]):
    resource_id: str
    resource_kind: str
    environment: str
    values: Mapping[str, Any]
    enabled: bool = True
    priority: int = 100
    reason: str | None = None
    created_by: str | None = None
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.id = _normalize_text(self.id, field_name="override id")
        self.resource_id = _normalize_text(self.resource_id, field_name="resource id")
        self.resource_kind = _normalize_text(self.resource_kind, field_name="resource kind")
        self.environment = _normalize_text(self.environment, field_name="environment")
        self.values = dict(self.values)
        self.reason = _normalize_optional_text(self.reason)
        self.created_by = _normalize_optional_text(self.created_by)
        self.created_at = normalize_datetime(self.created_at)
        self.updated_at = normalize_datetime(self.updated_at) if self.updated_at is not None else None

    def enable(self) -> bool:
        if self.enabled:
            return False
        self.enabled = True
        self.updated_at = utcnow()
        return True

    def disable(self) -> bool:
        if not self.enabled:
            return False
        self.enabled = False
        self.updated_at = utcnow()
        return True

    def update_values(self, values: Mapping[str, Any], *, reason: str | None = None) -> None:
        self.values = dict(values)
        self.reason = _normalize_optional_text(reason) or self.reason
        self.updated_at = utcnow()

    def to_source(self, *, resource: SettingsResourceRef) -> ConfigSource:
        return ConfigSource(
            source_id=f"override:{self.id}",
            source_kind="environment_override",
            resource=resource,
            override_id=self.id,
            priority=self.priority,
            applied=self.enabled,
            reason=self.reason,
            value=dict(self.values),
            metadata={
                "environment": self.environment,
            },
        )

    def to_payload(self) -> JsonObject:
        return {
            "id": self.id,
            "resource_id": self.resource_id,
            "resource_kind": self.resource_kind,
            "environment": self.environment,
            "values": dict(self.values),
            "enabled": self.enabled,
            "priority": self.priority,
            "reason": self.reason,
            "created_by": self.created_by,
            "created_at": format_optional_datetime(self.created_at),
            "updated_at": format_optional_datetime(self.updated_at),
            "metadata": dict(self.metadata),
        }


@dataclass(kw_only=True)
class SettingsEffectiveSnapshot(AggregateRoot[str]):
    resource: SettingsResourceRef
    effective_value: Mapping[str, Any]
    sources: tuple[ConfigSource, ...] = field(default_factory=tuple)
    overrides: tuple[ConfigSource, ...] = field(default_factory=tuple)
    environment: str | None = None
    version_id: str | None = None
    validation: SettingsValidationResult = field(default_factory=SettingsValidationResult)
    created_at: datetime = field(default_factory=utcnow)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.id = _normalize_text(self.id, field_name="snapshot id")
        self.effective_value = dict(self.effective_value)
        self.sources = tuple(self.sources)
        self.overrides = tuple(self.overrides)
        self.environment = _normalize_optional_text(self.environment)
        self.version_id = _normalize_optional_text(self.version_id)
        self.created_at = normalize_datetime(self.created_at)

    def to_resolution(self) -> ConfigResolution[Mapping[str, Any]]:
        return ConfigResolution(
            resource=self.resource,
            effective_value=dict(self.effective_value),
            sources=self.sources,
            overrides=self.overrides,
            snapshot_id=self.id,
            resolved_at=format_optional_datetime(self.created_at),
            validation=self.validation.to_payload(),
            trace_context=dict(self.metadata.get("trace_context") or {}),
        )

    def to_payload(self) -> JsonObject:
        return {
            "id": self.id,
            "resource": self.resource.to_payload(),
            "effective_value": dict(self.effective_value),
            "sources": [source.to_payload() for source in self.sources],
            "overrides": [source.to_payload() for source in self.overrides],
            "environment": self.environment,
            "version_id": self.version_id,
            "validation": self.validation.to_payload(),
            "created_at": format_optional_datetime(self.created_at),
            "metadata": dict(self.metadata),
        }


@dataclass(kw_only=True)
class SettingsActionAudit(AggregateRoot[str]):
    action_type: str
    target_type: str
    target_id: str | None
    reason: str
    status: SettingsActionStatus = SettingsActionStatus.ATTEMPTED
    actor: str | None = None
    risk: str | None = None
    request_metadata: Mapping[str, Any] = field(default_factory=dict)
    result: Mapping[str, Any] | None = None
    error: Mapping[str, Any] | None = None
    created_at: datetime = field(default_factory=utcnow)
    updated_at: datetime | None = None
    redaction_policy: Mapping[str, Any] = field(default_factory=lambda: {"mode": "metadata_only"})

    def __post_init__(self) -> None:
        self.id = _normalize_text(self.id, field_name="audit id")
        self.action_type = _normalize_text(self.action_type, field_name="action type")
        self.target_type = _normalize_text(self.target_type, field_name="target type")
        self.status = _coerce_action_status(self.status)
        self.target_id = _normalize_optional_text(self.target_id)
        self.reason = _normalize_text(self.reason, field_name="reason")
        self.actor = _normalize_optional_text(self.actor)
        self.risk = _normalize_optional_text(self.risk)
        self.created_at = normalize_datetime(self.created_at)
        self.updated_at = normalize_datetime(self.updated_at) if self.updated_at is not None else None

    def mark_succeeded(self, *, result: Mapping[str, Any] | None = None) -> None:
        self.status = SettingsActionStatus.SUCCEEDED
        self.result = dict(result or {})
        self.error = None
        self.updated_at = utcnow()

    def mark_failed(self, *, error: Mapping[str, Any]) -> None:
        self.status = SettingsActionStatus.FAILED
        self.error = dict(error)
        self.updated_at = utcnow()

    def to_payload(self) -> JsonObject:
        return {
            "id": self.id,
            "action_type": self.action_type,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "reason": self.reason,
            "status": self.status.value,
            "actor": self.actor,
            "risk": self.risk,
            "request_metadata": dict(self.request_metadata),
            "result": dict(self.result or {}) if self.result is not None else None,
            "error": dict(self.error or {}) if self.error is not None else None,
            "created_at": format_optional_datetime(self.created_at),
            "updated_at": format_optional_datetime(self.updated_at),
            "redaction_policy": dict(self.redaction_policy),
        }


def _coerce_resource_status(value: SettingsResourceStatus | str) -> SettingsResourceStatus:
    if isinstance(value, SettingsResourceStatus):
        return value
    try:
        return SettingsResourceStatus(str(value))
    except ValueError as exc:
        raise SettingsValidationError(f"invalid settings resource status '{value}'.") from exc


def _coerce_version_status(value: SettingsVersionStatus | str) -> SettingsVersionStatus:
    if isinstance(value, SettingsVersionStatus):
        return value
    try:
        return SettingsVersionStatus(str(value))
    except ValueError as exc:
        raise SettingsValidationError(f"invalid settings version status '{value}'.") from exc


def _coerce_action_status(value: SettingsActionStatus | str) -> SettingsActionStatus:
    if isinstance(value, SettingsActionStatus):
        return value
    try:
        return SettingsActionStatus(str(value))
    except ValueError as exc:
        raise SettingsValidationError(f"invalid settings action status '{value}'.") from exc
