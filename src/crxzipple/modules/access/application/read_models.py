from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping

from crxzipple.shared.access import AccessSetupFlowHint


JsonObject = dict[str, Any]


@dataclass(frozen=True, slots=True)
class CredentialBindingReadModel:
    binding_id: str
    binding_kind: str
    source_kind: str
    source_ref: str
    asset_id: str | None = None
    masked_preview: str | None = None
    status: str = "active"
    metadata: Mapping[str, object] = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def to_payload(self) -> JsonObject:
        payload: JsonObject = {
            "binding_id": self.binding_id,
            "binding_kind": self.binding_kind,
            "source_kind": self.source_kind,
            "source_ref": _safe_source_ref(self.source_kind, self.source_ref),
            "source_metadata": _source_metadata(self.source_kind, self.source_ref),
            "asset_id": self.asset_id,
            "masked_preview": _safe_masked_preview(
                self.source_kind,
                self.masked_preview,
            ),
            "status": self.status,
            "metadata": _redacted_mapping(self.metadata),
        }
        _add_timestamp_payload(payload, "created_at", self.created_at)
        _add_timestamp_payload(payload, "updated_at", self.updated_at)
        return payload


@dataclass(frozen=True, slots=True)
class AccessReadinessReadModel:
    target_kind: str
    target_id: str
    status: str
    ready: bool
    reason: str | None = None
    checks: tuple[Mapping[str, object], ...] = ()
    setup_available: bool = False
    metadata: Mapping[str, object] = field(default_factory=dict)
    observed_at: datetime | None = None

    def to_payload(self) -> JsonObject:
        payload: JsonObject = {
            "target_kind": self.target_kind,
            "target_id": self.target_id,
            "status": self.status,
            "ready": self.ready,
            "reason": self.reason,
            "checks": [_redacted_check_mapping(check) for check in self.checks],
            "setup_available": self.setup_available,
            "metadata": _redacted_mapping(self.metadata),
        }
        _add_timestamp_payload(payload, "observed_at", self.observed_at)
        return payload


@dataclass(frozen=True, slots=True)
class AccessCredentialRequirementReadModel:
    requirement_id: str
    consumer_module: str
    consumer_kind: str
    consumer_id: str
    slot: str
    expected_kind: str
    ready: bool
    missing: bool
    binding_id: str | None = None
    consumer_binding_id: str | None = None
    display_name: str | None = None
    provider: str | None = None
    required: bool = True
    status: str = "missing"
    reason: str | None = None
    setup_flow_hint: AccessSetupFlowHint | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)
    last_checked_at: datetime | None = None

    def to_payload(self) -> JsonObject:
        payload: JsonObject = {
            "requirement_id": self.requirement_id,
            "consumer_module": self.consumer_module,
            "consumer_kind": self.consumer_kind,
            "consumer_id": self.consumer_id,
            "slot": self.slot,
            "expected_kind": self.expected_kind,
            "binding_id": self.binding_id,
            "consumer_binding_id": self.consumer_binding_id,
            "display_name": self.display_name,
            "provider": self.provider,
            "required": self.required,
            "ready": self.ready,
            "missing": self.missing,
            "status": self.status,
            "reason": self.reason,
            "setup_flow_hint": _setup_flow_hint_payload(self.setup_flow_hint),
            "metadata": _redacted_mapping(self.metadata),
        }
        _add_timestamp_payload(payload, "last_checked_at", self.last_checked_at)
        return payload


@dataclass(frozen=True, slots=True)
class AccessConsumerBindingReadModel:
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
    metadata: Mapping[str, object] = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "requirement_sets",
            _normalize_requirement_sets(self.requirement_sets),
        )
        object.__setattr__(
            self,
            "credential_bindings",
            _normalize_slot_bindings(self.credential_bindings),
        )

    def to_payload(self) -> JsonObject:
        payload: JsonObject = {
            "binding_id": self.binding_id,
            "consumer_module": self.consumer_module,
            "consumer_kind": self.consumer_kind,
            "consumer_id": self.consumer_id,
            "display_name": self.display_name,
            "enabled": self.enabled,
            "asset_id": self.asset_id,
            "credential_binding_id": self.credential_binding_id,
            "credential_bindings": dict(self.credential_bindings),
            "requirement_sets": _safe_requirement_sets(self.requirement_sets),
            "status": self.status,
            "metadata": _redacted_mapping(self.metadata),
        }
        _add_timestamp_payload(payload, "created_at", self.created_at)
        _add_timestamp_payload(payload, "updated_at", self.updated_at)
        return payload


@dataclass(frozen=True, slots=True)
class AccessAssetSummaryReadModel:
    asset_id: str
    asset_kind: str
    display_name: str
    governance_scope: str
    status: str = "active"
    readiness: AccessReadinessReadModel | None = None
    consumer_modules: tuple[str, ...] = ()
    credential_binding_count: int = 0
    metadata: Mapping[str, object] = field(default_factory=dict)

    def to_payload(self) -> JsonObject:
        return {
            "asset_id": self.asset_id,
            "asset_kind": self.asset_kind,
            "display_name": self.display_name,
            "governance_scope": self.governance_scope,
            "status": self.status,
            "readiness": (
                self.readiness.to_payload() if self.readiness is not None else None
            ),
            "consumer_modules": list(self.consumer_modules),
            "credential_binding_count": self.credential_binding_count,
            "metadata": _redacted_mapping(self.metadata),
        }


@dataclass(frozen=True, slots=True)
class AccessAssetListReadModel:
    assets: tuple[AccessAssetSummaryReadModel, ...] = ()
    counts: Mapping[str, int] = field(default_factory=dict)
    generated_at: datetime | None = None

    def to_payload(self) -> JsonObject:
        payload: JsonObject = {
            "assets": [asset.to_payload() for asset in self.assets],
            "counts": dict(self.counts),
        }
        _add_timestamp_payload(payload, "generated_at", self.generated_at)
        return payload


@dataclass(frozen=True, slots=True)
class AccessAssetDetailReadModel:
    asset_id: str
    asset_kind: str
    display_name: str
    governance_scope: str
    status: str = "active"
    secret_policy: Mapping[str, object] = field(default_factory=dict)
    storage_key: str | None = None
    consumer_modules: tuple[str, ...] = ()
    readiness_policy: Mapping[str, object] = field(default_factory=dict)
    rotation_policy: Mapping[str, object] = field(default_factory=dict)
    audit_required: bool = True
    export_policy: Mapping[str, object] = field(default_factory=dict)
    degraded_reason: str | None = None
    readiness: AccessReadinessReadModel | None = None
    credential_bindings: tuple[CredentialBindingReadModel, ...] = ()
    consumer_bindings: tuple[AccessConsumerBindingReadModel, ...] = ()
    metadata: Mapping[str, object] = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def to_payload(self) -> JsonObject:
        payload: JsonObject = {
            "asset_id": self.asset_id,
            "asset_kind": self.asset_kind,
            "display_name": self.display_name,
            "governance_scope": self.governance_scope,
            "status": self.status,
            "secret_policy": dict(self.secret_policy),
            "storage_key": self.storage_key,
            "consumer_modules": list(self.consumer_modules),
            "readiness_policy": dict(self.readiness_policy),
            "rotation_policy": dict(self.rotation_policy),
            "audit_required": self.audit_required,
            "export_policy": dict(self.export_policy),
            "degraded_reason": self.degraded_reason,
            "readiness": (
                self.readiness.to_payload() if self.readiness is not None else None
            ),
            "credential_bindings": [
                binding.to_payload() for binding in self.credential_bindings
            ],
            "consumer_bindings": [
                binding.to_payload() for binding in self.consumer_bindings
            ],
            "metadata": _redacted_mapping(self.metadata),
        }
        _add_timestamp_payload(payload, "created_at", self.created_at)
        _add_timestamp_payload(payload, "updated_at", self.updated_at)
        return payload


@dataclass(frozen=True, slots=True)
class AccessSetupSessionReadModel:
    session_id: str
    target_kind: str
    target_id: str
    status: str
    flow_kind: str
    requested_by: str | None = None
    expires_at: datetime | None = None
    completed_at: datetime | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def to_payload(self) -> JsonObject:
        payload: JsonObject = {
            "session_id": self.session_id,
            "target_kind": self.target_kind,
            "target_id": self.target_id,
            "status": self.status,
            "flow_kind": self.flow_kind,
            "requested_by": self.requested_by,
            "metadata": _redacted_mapping(self.metadata),
        }
        for key, value in (
            ("expires_at", self.expires_at),
            ("completed_at", self.completed_at),
            ("created_at", self.created_at),
            ("updated_at", self.updated_at),
        ):
            _add_timestamp_payload(payload, key, value)
        return payload


@dataclass(frozen=True, slots=True)
class AccessOAuthProviderReadModel:
    provider_id: str
    display_name: str
    provider_kind: str = "oauth2"
    status: str = "active"
    default_scopes: tuple[str, ...] = ()
    authorization_url: str | None = None
    token_url: str | None = None
    revocation_url: str | None = None
    device_code_url: str | None = None
    callback_url: str | None = None
    callback_mode: str | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def to_payload(self) -> JsonObject:
        payload: JsonObject = {
            "provider_id": self.provider_id,
            "display_name": self.display_name,
            "provider_kind": self.provider_kind,
            "status": self.status,
            "default_scopes": list(self.default_scopes),
            "authorization_url": self.authorization_url,
            "token_url": self.token_url,
            "revocation_url": self.revocation_url,
            "device_code_url": self.device_code_url,
            "callback_url": self.callback_url,
            "callback_mode": self.callback_mode,
            "metadata": _redacted_mapping(self.metadata),
        }
        _add_timestamp_payload(payload, "created_at", self.created_at)
        _add_timestamp_payload(payload, "updated_at", self.updated_at)
        return payload


@dataclass(frozen=True, slots=True)
class AccessOAuthAccountReadModel:
    account_id: str
    provider_id: str
    credential_binding_id: str | None
    display_name: str | None = None
    subject: str | None = None
    granted_scopes: tuple[str, ...] = ()
    expires_at: datetime | None = None
    refresh_ready: bool = False
    status: str = "active"
    masked_preview: str | None = None
    metadata: Mapping[str, object] = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def to_payload(self) -> JsonObject:
        payload: JsonObject = {
            "account_id": self.account_id,
            "provider_id": self.provider_id,
            "credential_binding_id": self.credential_binding_id,
            "display_name": self.display_name,
            "subject": self.subject,
            "granted_scopes": list(self.granted_scopes),
            "refresh_ready": self.refresh_ready,
            "status": self.status,
            "masked_preview": self.masked_preview,
            "metadata": _redacted_mapping(self.metadata),
        }
        _add_timestamp_payload(payload, "expires_at", self.expires_at)
        _add_timestamp_payload(payload, "created_at", self.created_at)
        _add_timestamp_payload(payload, "updated_at", self.updated_at)
        return payload


@dataclass(frozen=True, slots=True)
class AccessAuditReadModel:
    audit_id: str
    action_type: str
    target_type: str
    target_id: str | None
    status: str
    operator: str | None
    source: str
    reason: str
    request_metadata: Mapping[str, object] = field(default_factory=dict)
    result: Mapping[str, object] | None = None
    error: Mapping[str, object] | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def to_payload(self) -> JsonObject:
        payload: JsonObject = {
            "audit_id": self.audit_id,
            "action_type": self.action_type,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "status": self.status,
            "operator": self.operator,
            "source": self.source,
            "reason": self.reason,
            "request_metadata": _redacted_mapping(self.request_metadata),
            "result": (
                _redacted_mapping(self.result) if self.result is not None else None
            ),
            "error": _redacted_mapping(self.error) if self.error is not None else None,
        }
        _add_timestamp_payload(payload, "created_at", self.created_at)
        _add_timestamp_payload(payload, "updated_at", self.updated_at)
        return payload


@dataclass(frozen=True, slots=True)
class AccessOverviewReadModel:
    ready: bool
    counts: Mapping[str, int] = field(default_factory=dict)
    assets: AccessAssetListReadModel = field(default_factory=AccessAssetListReadModel)
    readiness: tuple[AccessReadinessReadModel, ...] = ()
    credential_requirements: tuple[AccessCredentialRequirementReadModel, ...] = ()
    credential_bindings: tuple[CredentialBindingReadModel, ...] = ()
    consumer_bindings: tuple[AccessConsumerBindingReadModel, ...] = ()
    setup_sessions: tuple[AccessSetupSessionReadModel, ...] = ()
    oauth_providers: tuple[AccessOAuthProviderReadModel, ...] = ()
    oauth_accounts: tuple[AccessOAuthAccountReadModel, ...] = ()
    generated_at: datetime | None = None

    def to_payload(self) -> JsonObject:
        payload: JsonObject = {
            "ready": self.ready,
            "counts": dict(self.counts),
            "assets": self.assets.to_payload(),
            "readiness": [item.to_payload() for item in self.readiness],
            "credential_requirements": [
                item.to_payload() for item in self.credential_requirements
            ],
            "requirements_by_consumer": _requirements_by_consumer(
                self.credential_requirements,
            ),
            "missing_requirements": [
                item.to_payload()
                for item in self.credential_requirements
                if item.missing or not item.ready
            ],
            "ready_requirements": [
                item.to_payload()
                for item in self.credential_requirements
                if item.ready
            ],
            "oauth_requirements": [
                item.to_payload()
                for item in self.credential_requirements
                if item.expected_kind in {"oauth2_account", "openid_connect"}
            ],
            "credential_bindings": [
                item.to_payload() for item in self.credential_bindings
            ],
            "consumer_bindings": [
                item.to_payload() for item in self.consumer_bindings
            ],
            "setup_sessions": [item.to_payload() for item in self.setup_sessions],
            "oauth_providers": [item.to_payload() for item in self.oauth_providers],
            "oauth_accounts": [item.to_payload() for item in self.oauth_accounts],
        }
        _add_timestamp_payload(payload, "generated_at", self.generated_at)
        return payload


def _add_timestamp_payload(
    payload: JsonObject,
    key: str,
    value: datetime | None,
) -> None:
    if value is not None:
        payload[key] = value.isoformat()


def _normalize_requirement_sets(
    requirement_sets: tuple[tuple[str, ...], ...],
) -> tuple[tuple[str, ...], ...]:
    resolved: list[tuple[str, ...]] = []
    for requirement_set in requirement_sets:
        normalized = tuple(
            dict.fromkeys(
                str(item).strip()
                for item in requirement_set
                if item is not None and str(item).strip()
            ),
        )
        if normalized and normalized not in resolved:
            resolved.append(normalized)
    return tuple(resolved)


def _normalize_slot_bindings(value: Mapping[str, str]) -> JsonObject:
    normalized: dict[str, str] = {}
    for slot, binding_id in value.items():
        slot_text = str(slot).strip()
        binding_text = str(binding_id).strip()
        if slot_text and binding_text:
            normalized[slot_text] = binding_text
    return normalized


def _redacted_mapping(value: Mapping[str, object]) -> JsonObject:
    return {str(key): _redacted_value(str(key), item) for key, item in value.items()}


def _redacted_check_mapping(value: Mapping[str, object]) -> JsonObject:
    payload = _redacted_mapping(value)
    target_type = str(payload.get("target_type") or "")
    requirement = payload.get("requirement")
    if (
        target_type == "credential_binding"
        and isinstance(requirement, str)
    ):
        payload["requirement"] = (
            _masked_binding_reference(requirement)
            if _is_safe_binding_reference(requirement)
            else "literal:***"
        )
    return payload


def _setup_flow_hint_payload(
    value: AccessSetupFlowHint | None,
) -> JsonObject | None:
    if value is None:
        return None
    return {
        "flow_kind": str(value.flow_kind),
        "provider": value.provider,
        "authorization_url": value.authorization_url,
        "token_url": value.token_url,
        "device_code_url": value.device_code_url,
        "callback_url": value.callback_url,
        "metadata": _redacted_mapping(value.metadata),
    }


def _requirements_by_consumer(
    requirements: tuple[AccessCredentialRequirementReadModel, ...],
) -> JsonObject:
    grouped: dict[str, list[JsonObject]] = {}
    for requirement in requirements:
        key = ":".join(
            (
                requirement.consumer_module,
                requirement.consumer_kind,
                requirement.consumer_id,
            ),
        )
        grouped.setdefault(key, []).append(requirement.to_payload())
    return grouped


def _safe_requirement_sets(
    requirement_sets: tuple[tuple[str, ...], ...],
) -> list[list[str]]:
    return [
        [_safe_requirement_ref(item) for item in requirement_set]
        for requirement_set in requirement_sets
    ]


def _safe_requirement_ref(value: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        return ""
    if normalized.startswith(("env:", "file:", "literal:", "inline:")):
        return f"{normalized.split(':', 1)[0]}:***"
    if "(" in normalized and normalized.endswith(")"):
        prefix = normalized.split("(", 1)[0].strip()
        return f"{prefix}(***)"
    return normalized


def _safe_source_ref(source_kind: str, source_ref: str) -> str:
    normalized_kind = source_kind.strip().lower()
    if normalized_kind in {"env", "file"}:
        return f"{normalized_kind}:***"
    if normalized_kind in {"literal", "inline", "inline_credential", "secret"}:
        return "***"
    return str(_redacted_value("source_ref", source_ref))


def _source_metadata(source_kind: str, source_ref: str) -> JsonObject:
    normalized_kind = source_kind.strip().lower()
    normalized_ref = source_ref.strip()
    metadata: JsonObject = {
        "source_kind": normalized_kind,
        "configured": bool(normalized_ref),
        "source_ref_redacted": bool(normalized_ref),
    }
    if normalized_kind == "env" and normalized_ref:
        metadata["reference_kind"] = "environment_variable"
    elif normalized_kind == "file" and normalized_ref:
        metadata["reference_kind"] = "file_path"
    elif normalized_kind == "oauth_account" and normalized_ref:
        metadata["source_ref_redacted"] = False
    return metadata


def _safe_masked_preview(source_kind: str, masked_preview: str | None) -> str | None:
    if masked_preview is None:
        return None
    normalized_kind = source_kind.strip().lower()
    if normalized_kind in {"env", "file"}:
        return f"{normalized_kind}:***"
    if normalized_kind in {"literal", "inline", "inline_credential", "secret"}:
        return "***"
    return str(_redacted_value("masked_preview", masked_preview))


def _redacted_value(key: str, value: object) -> object:
    if _is_sensitive_key(key):
        if isinstance(value, str) and _is_safe_binding_reference(value):
            return _masked_binding_reference(value)
        return "***" if value is not None else None
    if isinstance(value, Mapping):
        return _redacted_mapping(value)
    if isinstance(value, (list, tuple)):
        return [_redacted_value("", item) for item in value]
    if isinstance(value, str) and _is_safe_binding_reference(value):
        return _masked_binding_reference(value)
    return value


def _is_sensitive_key(key: str) -> bool:
    normalized = key.strip().lower()
    return normalized in {
        "access_token",
        "api_key",
        "authorization",
        "canonical_ref",
        "client_secret",
        "code",
        "code_verifier",
        "device_code",
        "id_token",
        "password",
        "refresh_token",
        "secret",
        "secret_value",
        "source_ref",
        "state",
        "token",
        "value",
    }


def _is_safe_binding_reference(value: str) -> bool:
    normalized = value.strip()
    return normalized.startswith(("env:", "file:"))


def _masked_binding_reference(value: str) -> str:
    normalized = value.strip()
    if normalized.startswith("env:"):
        return "env:***"
    if normalized.startswith("file:"):
        return "file:***"
    return "***"
