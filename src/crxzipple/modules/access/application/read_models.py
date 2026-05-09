from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping


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
            "asset_id": self.asset_id,
            "masked_preview": self.masked_preview,
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
class AccessConsumerBindingReadModel:
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
    metadata: Mapping[str, object] = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "requirement_sets",
            _normalize_requirement_sets(self.requirement_sets),
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
            "requirement_sets": [list(items) for items in self.requirement_sets],
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
    credential_bindings: tuple[CredentialBindingReadModel, ...] = ()
    consumer_bindings: tuple[AccessConsumerBindingReadModel, ...] = ()
    setup_sessions: tuple[AccessSetupSessionReadModel, ...] = ()
    audits: tuple[AccessAuditReadModel, ...] = ()
    generated_at: datetime | None = None

    def to_payload(self) -> JsonObject:
        payload: JsonObject = {
            "ready": self.ready,
            "counts": dict(self.counts),
            "assets": self.assets.to_payload(),
            "readiness": [item.to_payload() for item in self.readiness],
            "credential_bindings": [
                item.to_payload() for item in self.credential_bindings
            ],
            "consumer_bindings": [
                item.to_payload() for item in self.consumer_bindings
            ],
            "setup_sessions": [item.to_payload() for item in self.setup_sessions],
            "audits": [item.to_payload() for item in self.audits],
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


def _redacted_mapping(value: Mapping[str, object]) -> JsonObject:
    return {str(key): _redacted_value(str(key), item) for key, item in value.items()}


def _redacted_check_mapping(value: Mapping[str, object]) -> JsonObject:
    payload = _redacted_mapping(value)
    target_type = str(payload.get("target_type") or "")
    requirement = payload.get("requirement")
    if (
        target_type == "credential_binding"
        and isinstance(requirement, str)
        and not _is_safe_binding_reference(requirement)
    ):
        payload["requirement"] = "literal:***"
    return payload


def _safe_source_ref(source_kind: str, source_ref: str) -> str:
    normalized_kind = source_kind.strip().lower()
    if normalized_kind in {"literal", "inline", "inline_credential", "secret"}:
        return "***"
    return str(_redacted_value("source_ref", source_ref))


def _redacted_value(key: str, value: object) -> object:
    if _is_sensitive_key(key):
        if isinstance(value, str) and _is_safe_binding_reference(value):
            return value
        return "***" if value is not None else None
    if isinstance(value, Mapping):
        return _redacted_mapping(value)
    if isinstance(value, (list, tuple)):
        return [_redacted_value("", item) for item in value]
    return value


def _is_sensitive_key(key: str) -> bool:
    normalized = key.strip().lower()
    return normalized in {
        "access_token",
        "api_key",
        "authorization",
        "client_secret",
        "id_token",
        "password",
        "refresh_token",
        "secret",
        "secret_value",
        "source_ref",
        "token",
        "value",
    }


def _is_safe_binding_reference(value: str) -> bool:
    normalized = value.strip()
    return normalized.startswith(("env:", "file:", "codex_auth_json"))
