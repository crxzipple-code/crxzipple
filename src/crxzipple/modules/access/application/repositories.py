from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol


JsonObject = dict[str, Any]


@dataclass(frozen=True, slots=True)
class AccessAssetRecord:
    asset_id: str
    asset_kind: str
    display_name: str
    governance_scope: str
    status: str = "active"
    secret_policy: JsonObject = field(default_factory=dict)
    storage_key: str | None = None
    consumer_modules: tuple[str, ...] = ()
    readiness_policy: JsonObject = field(default_factory=dict)
    rotation_policy: JsonObject = field(default_factory=dict)
    audit_required: bool = True
    export_policy: JsonObject = field(default_factory=dict)
    degraded_reason: str | None = None
    redaction_policy: JsonObject = field(default_factory=dict)
    metadata: JsonObject = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class AccessCredentialBindingRecord:
    binding_id: str
    asset_id: str | None
    binding_kind: str
    source_kind: str
    source_ref: str
    masked_preview: str | None = None
    status: str = "active"
    redaction_policy: JsonObject = field(default_factory=dict)
    metadata: JsonObject = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class AccessConsumerBindingRecord:
    binding_id: str
    consumer_module: str
    consumer_kind: str
    consumer_id: str
    display_name: str | None = None
    enabled: bool = True
    asset_id: str | None = None
    credential_binding_id: str | None = None
    requirement_sets: tuple[tuple[str, ...], ...] = ()
    status: str = "active"
    redaction_policy: JsonObject = field(default_factory=dict)
    metadata: JsonObject = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class AccessSecretBindingRecord:
    binding_id: str
    credential_binding_id: str | None
    storage_key: str
    source_kind: str
    source_ref: str | None = None
    masked_preview: str | None = None
    status: str = "active"
    redaction_policy: JsonObject = field(default_factory=dict)
    metadata: JsonObject = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class AccessConnectionProfileRecord:
    profile_id: str
    asset_id: str | None
    provider: str
    profile_kind: str
    endpoint_ref: str | None = None
    credential_binding_id: str | None = None
    status: str = "active"
    redaction_policy: JsonObject = field(default_factory=dict)
    metadata: JsonObject = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class AccessSetupSessionRecord:
    session_id: str
    target_kind: str
    target_id: str
    status: str
    flow_kind: str
    requested_by: str | None = None
    expires_at: datetime | None = None
    completed_at: datetime | None = None
    redaction_policy: JsonObject = field(default_factory=dict)
    metadata: JsonObject = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class AccessReadinessSnapshotRecord:
    snapshot_id: str
    target_kind: str
    target_id: str
    status: str
    ready: bool
    reason: str | None = None
    checks: tuple[JsonObject, ...] = ()
    redaction_policy: JsonObject = field(default_factory=dict)
    metadata: JsonObject = field(default_factory=dict)
    created_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class AccessActionAuditRecord:
    audit_id: str
    action_type: str
    target_type: str
    target_id: str | None
    status: str
    operator: str | None
    source: str
    reason: str
    request_metadata: JsonObject = field(default_factory=dict)
    result: JsonObject | None = None
    error: JsonObject | None = None
    redaction_policy: JsonObject = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class AccessGovernanceRepository(Protocol):
    def create_asset(self, record: AccessAssetRecord) -> AccessAssetRecord: ...

    def get_asset(self, asset_id: str) -> AccessAssetRecord | None: ...

    def list_assets(self) -> tuple[AccessAssetRecord, ...]: ...

    def create_credential_binding(
        self,
        record: AccessCredentialBindingRecord,
    ) -> AccessCredentialBindingRecord: ...

    def get_credential_binding(
        self,
        binding_id: str,
    ) -> AccessCredentialBindingRecord | None: ...

    def list_credential_bindings(self) -> tuple[AccessCredentialBindingRecord, ...]: ...

    def create_consumer_binding(
        self,
        record: AccessConsumerBindingRecord,
    ) -> AccessConsumerBindingRecord: ...

    def get_consumer_binding(
        self,
        binding_id: str,
    ) -> AccessConsumerBindingRecord | None: ...

    def list_consumer_bindings(self) -> tuple[AccessConsumerBindingRecord, ...]: ...


class AccessActionAuditRepository(Protocol):
    def record_attempt(
        self,
        *,
        action_type: str,
        target_type: str,
        target_id: str | None,
        reason: str,
        operator: str | None = None,
        source: str = "access",
        request_metadata: JsonObject | None = None,
        redaction_policy: JsonObject | None = None,
        created_at: datetime | None = None,
    ) -> AccessActionAuditRecord: ...

    def mark_succeeded(
        self,
        audit_id: str,
        *,
        result: JsonObject | None = None,
        updated_at: datetime | None = None,
    ) -> AccessActionAuditRecord: ...

    def mark_failed(
        self,
        audit_id: str,
        *,
        error: JsonObject,
        updated_at: datetime | None = None,
    ) -> AccessActionAuditRecord: ...
