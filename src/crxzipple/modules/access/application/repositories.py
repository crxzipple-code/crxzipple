from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping, Protocol


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
    credential_bindings: Mapping[str, str] = field(default_factory=dict)
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
class AccessOAuthProviderRecord:
    provider_id: str
    display_name: str
    provider_kind: str = "oauth2"
    authorization_url: str | None = None
    token_url: str | None = None
    revocation_url: str | None = None
    device_code_url: str | None = None
    default_scopes: tuple[str, ...] = ()
    client_id: str | None = None
    client_credential_binding_id: str | None = None
    callback_url: str | None = None
    callback_mode: str = "manual_code"
    status: str = "active"
    redaction_policy: JsonObject = field(default_factory=dict)
    metadata: JsonObject = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class AccessOAuthAccountRecord:
    account_id: str
    provider_id: str
    credential_binding_id: str | None
    display_name: str | None = None
    subject: str | None = None
    granted_scopes: tuple[str, ...] = ()
    expires_at: datetime | None = None
    refresh_ready: bool = False
    status: str = "active"
    storage_key: str | None = None
    masked_preview: str | None = None
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

    def upsert_oauth_provider(
        self,
        record: AccessOAuthProviderRecord,
    ) -> AccessOAuthProviderRecord: ...

    def get_oauth_provider(self, provider_id: str) -> AccessOAuthProviderRecord | None: ...

    def list_oauth_providers(self) -> tuple[AccessOAuthProviderRecord, ...]: ...

    def upsert_oauth_account(
        self,
        record: AccessOAuthAccountRecord,
    ) -> AccessOAuthAccountRecord: ...

    def get_oauth_account(self, account_id: str) -> AccessOAuthAccountRecord | None: ...

    def list_oauth_accounts(self) -> tuple[AccessOAuthAccountRecord, ...]: ...

    def create_setup_session(
        self,
        record: AccessSetupSessionRecord,
    ) -> AccessSetupSessionRecord: ...

    def get_setup_session(self, session_id: str) -> AccessSetupSessionRecord | None: ...

    def complete_setup_session(
        self,
        session_id: str,
        *,
        status: str,
        metadata: JsonObject | None = None,
        completed_at: datetime | None = None,
    ) -> AccessSetupSessionRecord: ...


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
