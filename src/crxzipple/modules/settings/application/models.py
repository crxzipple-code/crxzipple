from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from crxzipple.modules.settings.domain.entities import (
    SettingsActionAudit,
    SettingsEffectiveSnapshot,
    SettingsOverride,
    SettingsResource,
    SettingsResourceVersion,
)
from crxzipple.modules.settings.domain.value_objects import SettingsValidationResult
from crxzipple.shared.settings import ConfigResolution


JsonObject = dict[str, Any]


@dataclass(frozen=True, slots=True)
class CreateSettingsResourceInput:
    resource_id: str
    resource_kind: str
    owner_module: str
    payload: Mapping[str, Any]
    scope: str = "global"
    display_name: str | None = None
    actor: str | None = None
    reason: str = "create settings resource"
    publish: bool = False
    source: str = "manual"
    metadata: Mapping[str, Any] = field(default_factory=dict)
    trace_context: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class UpdateSettingsResourceInput:
    resource_id: str
    payload: Mapping[str, Any]
    actor: str | None = None
    reason: str = "update settings resource"
    publish: bool = False
    source: str = "manual"
    expected_active_version_id: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    trace_context: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PublishSettingsVersionInput:
    resource_id: str
    version_id: str | None = None
    actor: str | None = None
    reason: str = "publish settings version"
    expected_active_version_id: str | None = None
    environment: str | None = None
    trace_context: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RollbackSettingsResourceInput:
    resource_id: str
    target_version_id: str
    actor: str | None = None
    reason: str = "rollback settings resource"
    expected_active_version_id: str | None = None
    environment: str | None = None
    trace_context: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SetSettingsResourceEnabledInput:
    resource_id: str
    enabled: bool
    actor: str | None = None
    reason: str = "set settings resource enablement"
    trace_context: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class UpsertSettingsOverrideInput:
    resource_id: str
    environment: str
    values: Mapping[str, Any]
    override_id: str | None = None
    actor: str | None = None
    reason: str = "upsert settings override"
    enabled: bool = True
    priority: int = 100
    metadata: Mapping[str, Any] = field(default_factory=dict)
    trace_context: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SetSettingsOverrideEnabledInput:
    override_id: str
    enabled: bool
    actor: str | None = None
    reason: str = "set settings override enablement"
    trace_context: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SettingsActionResult:
    status: str
    audit: SettingsActionAudit
    resource: SettingsResource | None = None
    version: SettingsResourceVersion | None = None
    override: SettingsOverride | None = None
    snapshot: SettingsEffectiveSnapshot | None = None
    resolution: ConfigResolution[Mapping[str, Any]] | None = None
    validation: SettingsValidationResult = field(default_factory=SettingsValidationResult)
    warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def audit_ref(self) -> str:
        return self.audit.id
