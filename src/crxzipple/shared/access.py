from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping, Protocol


def _normalize_text(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} is required.")
    return normalized


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_text_tuple(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(item.strip() for item in values if isinstance(item, str) and item.strip())


class AccessReadinessStatus(StrEnum):
    READY = "ready"
    SETUP_NEEDED = "setup_needed"
    WAITING_USER = "waiting_user"
    EXPIRED = "expired"
    DEGRADED = "degraded"
    UNSUPPORTED = "unsupported"


class AccessDecisionEffect(StrEnum):
    ALLOW = "allow"
    DENY = "deny"
    CONDITIONAL = "conditional"


@dataclass(frozen=True, slots=True)
class AccessAssetRef:
    asset_id: str
    asset_kind: str
    display_name: str | None = None
    owner_module: str = "access"
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "asset_id", _normalize_text(self.asset_id, field_name="asset_id"))
        object.__setattr__(
            self,
            "asset_kind",
            _normalize_text(self.asset_kind, field_name="asset_kind"),
        )
        object.__setattr__(self, "display_name", _normalize_optional_text(self.display_name))
        object.__setattr__(
            self,
            "owner_module",
            _normalize_text(self.owner_module, field_name="owner_module"),
        )


@dataclass(frozen=True, slots=True)
class CredentialBindingRef:
    binding_id: str
    source_type: str
    source_ref: str
    asset: AccessAssetRef | None = None
    masked_preview: str | None = None
    scopes: tuple[str, ...] = field(default_factory=tuple)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "binding_id",
            _normalize_text(self.binding_id, field_name="binding_id"),
        )
        object.__setattr__(
            self,
            "source_type",
            _normalize_text(self.source_type, field_name="source_type"),
        )
        object.__setattr__(
            self,
            "source_ref",
            _normalize_text(self.source_ref, field_name="source_ref"),
        )
        object.__setattr__(self, "masked_preview", _normalize_optional_text(self.masked_preview))
        object.__setattr__(self, "scopes", _normalize_text_tuple(self.scopes))


@dataclass(frozen=True, slots=True)
class SecretBindingRef:
    binding_id: str
    secret_asset: AccessAssetRef
    storage_key: str
    masked_preview: str | None = None
    checksum: str | None = None
    version: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "binding_id",
            _normalize_text(self.binding_id, field_name="binding_id"),
        )
        object.__setattr__(
            self,
            "storage_key",
            _normalize_text(self.storage_key, field_name="storage_key"),
        )
        object.__setattr__(self, "masked_preview", _normalize_optional_text(self.masked_preview))
        object.__setattr__(self, "checksum", _normalize_optional_text(self.checksum))
        object.__setattr__(self, "version", _normalize_optional_text(self.version))


@dataclass(frozen=True, slots=True)
class AccessRequirementRef:
    requirement_id: str
    provider: str | None = None
    kind: str | None = None
    required_scopes: tuple[str, ...] = field(default_factory=tuple)
    required_effects: tuple[str, ...] = field(default_factory=tuple)
    asset_refs: tuple[AccessAssetRef, ...] = field(default_factory=tuple)
    setup_action_metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "requirement_id",
            _normalize_text(self.requirement_id, field_name="requirement_id"),
        )
        object.__setattr__(self, "provider", _normalize_optional_text(self.provider))
        object.__setattr__(self, "kind", _normalize_optional_text(self.kind))
        object.__setattr__(self, "required_scopes", _normalize_text_tuple(self.required_scopes))
        object.__setattr__(self, "required_effects", _normalize_text_tuple(self.required_effects))


@dataclass(frozen=True, slots=True)
class AccessConsumerRef:
    consumer_id: str
    module: str
    component: str | None = None
    runtime_ref: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "consumer_id",
            _normalize_text(self.consumer_id, field_name="consumer_id"),
        )
        object.__setattr__(self, "module", _normalize_text(self.module, field_name="module"))
        object.__setattr__(self, "component", _normalize_optional_text(self.component))
        object.__setattr__(self, "runtime_ref", _normalize_optional_text(self.runtime_ref))


@dataclass(frozen=True, slots=True)
class AccessReadiness:
    requirement: AccessRequirementRef
    consumer: AccessConsumerRef
    status: AccessReadinessStatus
    reason: str
    asset_refs: tuple[AccessAssetRef, ...] = field(default_factory=tuple)
    credential_bindings: tuple[CredentialBindingRef, ...] = field(default_factory=tuple)
    secret_bindings: tuple[SecretBindingRef, ...] = field(default_factory=tuple)
    setup_action_metadata: Mapping[str, Any] = field(default_factory=dict)
    masked_preview: str | None = None
    trace_context: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "reason", _normalize_text(self.reason, field_name="reason"))
        object.__setattr__(self, "masked_preview", _normalize_optional_text(self.masked_preview))

    @property
    def ready(self) -> bool:
        return self.status is AccessReadinessStatus.READY


@dataclass(frozen=True, slots=True)
class AccessDecision:
    effect: AccessDecisionEffect
    reason: str
    code: str
    consumer: AccessConsumerRef
    asset: AccessAssetRef | None = None
    requirement: AccessRequirementRef | None = None
    obligations: tuple[str, ...] = field(default_factory=tuple)
    audit_context: Mapping[str, Any] = field(default_factory=dict)
    trace_context: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "reason", _normalize_text(self.reason, field_name="reason"))
        object.__setattr__(self, "code", _normalize_text(self.code, field_name="code"))
        object.__setattr__(self, "obligations", _normalize_text_tuple(self.obligations))

    @property
    def allowed(self) -> bool:
        return self.effect is AccessDecisionEffect.ALLOW


class EffectiveAccessProvider(Protocol):
    def readiness_for(
        self,
        requirement: AccessRequirementRef,
        *,
        consumer: AccessConsumerRef,
        trace_context: Mapping[str, Any] | None = None,
    ) -> AccessReadiness:
        ...


class CredentialProvider(Protocol):
    def resolve_credential(
        self,
        binding: CredentialBindingRef,
        *,
        consumer: AccessConsumerRef,
        trace_context: Mapping[str, Any] | None = None,
    ) -> str:
        ...
