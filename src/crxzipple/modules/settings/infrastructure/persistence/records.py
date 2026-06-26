from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any


JsonObject = dict[str, Any]


@dataclass(frozen=True, slots=True)
class SettingsResourceRecord:
    resource_id: str
    resource_kind: str
    governance_scope: str
    config_contract: JsonObject
    storage_key: str
    display_name: str | None = None
    contract_version: str | None = None
    consumer_modules: tuple[str, ...] = ()
    resolution_policy: JsonObject = field(default_factory=dict)
    supports_create: bool = True
    supports_update: bool = True
    supports_delete: bool = True
    supports_enable: bool = True
    supports_disable: bool = True
    supports_import: bool = True
    supports_export: bool = True
    validation_policy: JsonObject = field(default_factory=dict)
    dry_run_policy: JsonObject = field(default_factory=dict)
    audit_required: bool = True
    secret_policy: JsonObject = field(default_factory=dict)
    status: str = "active"
    latest_version_number: int | None = None
    published_version_id: str | None = None
    published_version_number: int | None = None
    degraded_reason: str | None = None
    metadata: JsonObject = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class SettingsResourceVersionRecord:
    version_id: str
    resource_id: str
    resource_kind: str
    version_number: int
    payload: JsonObject
    status: str = "draft"
    source_kind: str = "manual"
    source_ref: str | None = None
    source_metadata: JsonObject = field(default_factory=dict)
    contract_version: str | None = None
    redaction_policy: JsonObject = field(default_factory=dict)
    validation_result_id: str | None = None
    created_by: str | None = None
    reason: str | None = None
    published_at: datetime | None = None
    metadata: JsonObject = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class SettingsEffectiveSnapshotRecord:
    snapshot_id: str
    resource_id: str
    resource_kind: str
    effective_payload: JsonObject
    scope_key: str = "default"
    version_id: str | None = None
    version_number: int | None = None
    resolution_trace: tuple[JsonObject, ...] = ()
    sources: tuple[JsonObject, ...] = ()
    overrides_applied: tuple[JsonObject, ...] = ()
    status: str = "active"
    is_current: bool = True
    generated_at: datetime | None = None
    metadata: JsonObject = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class SettingsOverrideRecord:
    override_id: str
    resource_id: str
    resource_kind: str
    override_kind: str
    scope_key: str
    override_payload: JsonObject
    priority: int = 100
    status: str = "active"
    source_kind: str = "manual"
    source_ref: str | None = None
    reason: str | None = None
    actor: str | None = None
    expires_at: datetime | None = None
    redaction_policy: JsonObject = field(default_factory=dict)
    metadata: JsonObject = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class SettingsValidationResultRecord:
    validation_id: str
    resource_id: str
    resource_kind: str
    validator: str
    status: str
    valid: bool
    version_id: str | None = None
    audit_id: str | None = None
    issues: tuple[JsonObject, ...] = ()
    checked_payload_digest: str | None = None
    redaction_policy: JsonObject = field(default_factory=dict)
    metadata: JsonObject = field(default_factory=dict)
    created_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class SettingsActionAuditRecord:
    audit_id: str
    action_type: str
    target_type: str
    target_id: str | None
    status: str
    reason: str
    actor: str | None = None
    action_id: str | None = None
    resource_id: str | None = None
    resource_kind: str | None = None
    source: str = "settings"
    risk: str = "normal"
    confirmation: bool = False
    risk_acknowledged: bool = False
    request_metadata: JsonObject = field(default_factory=dict)
    result: JsonObject | None = None
    error: JsonObject | None = None
    redaction_policy: JsonObject = field(default_factory=dict)
    trace_context: JsonObject = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None
