from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Mapping


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


class AccessResourceKind(StrEnum):
    CREDENTIAL_BINDING = "credential_binding"
    SECRET_ASSET = "secret_asset"
    CONNECTION_ASSET = "connection_asset"
    OAUTH_PROVIDER = "oauth_provider"
    OAUTH_ACCOUNT = "oauth_account"
    PROVIDER_SCOPE = "provider_scope"
    CREDENTIAL_LEASE = "credential_lease"
    SETUP_SESSION = "setup_session"
    ACCESS_REQUIREMENT = "access_requirement"
    CONSUMER_BINDING = "consumer_binding"


class AccessGovernanceScope(StrEnum):
    GLOBAL = "global"
    WORKSPACE = "workspace"
    AGENT = "agent"
    MODULE = "module"
    CONSUMER = "consumer"
    RUNTIME = "runtime"
    USER = "user"


class AccessSecretStorageMode(StrEnum):
    NONE = "none"
    BINDING_ONLY = "binding_only"
    LOCAL_SECRET_STORE = "local_secret_store"
    EXTERNAL_VAULT = "external_vault"


class AccessRotationInterval(StrEnum):
    NONE = "none"
    MANUAL = "manual"
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"


@dataclass(frozen=True, slots=True)
class AccessSecretPolicy:
    storage_mode: AccessSecretStorageMode = AccessSecretStorageMode.BINDING_ONLY
    secret_material_allowed: bool = False
    masked_preview_required: bool = True
    checksum_required: bool = False
    exportable: bool = False
    sensitive_metadata_keys: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "sensitive_metadata_keys",
            _normalize_text_tuple(self.sensitive_metadata_keys),
        )
        if self.secret_material_allowed and self.storage_mode is AccessSecretStorageMode.NONE:
            raise ValueError("secret material requires a storage mode.")
        if self.exportable and self.secret_material_allowed:
            raise ValueError("secret material cannot be marked exportable.")


@dataclass(frozen=True, slots=True)
class AccessRotationPolicy:
    interval: AccessRotationInterval = AccessRotationInterval.NONE
    rotate_after_days: int | None = None
    warning_before_days: int | None = None
    owner: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.rotate_after_days is not None and self.rotate_after_days <= 0:
            raise ValueError("rotate_after_days must be positive.")
        if self.warning_before_days is not None and self.warning_before_days < 0:
            raise ValueError("warning_before_days cannot be negative.")
        object.__setattr__(self, "owner", _normalize_optional_text(self.owner))


@dataclass(frozen=True, slots=True)
class AccessReadinessPolicy:
    required: bool = True
    degraded_allowed: bool = False
    setup_action_required: bool = False
    readiness_checks: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        object.__setattr__(self, "readiness_checks", _normalize_text_tuple(self.readiness_checks))


@dataclass(frozen=True, slots=True)
class AccessExportPolicy:
    exportable: bool = False
    include_masked_metadata: bool = True
    include_storage_key: bool = False
    reason_required: bool = True


@dataclass(frozen=True, slots=True)
class AccessResourceDefinition:
    resource_id: str
    resource_kind: AccessResourceKind
    governance_scope: AccessGovernanceScope
    secret_policy: AccessSecretPolicy = field(default_factory=AccessSecretPolicy)
    storage_key: str | None = None
    consumer_modules: tuple[str, ...] = field(default_factory=tuple)
    readiness_policy: AccessReadinessPolicy = field(default_factory=AccessReadinessPolicy)
    rotation_policy: AccessRotationPolicy = field(default_factory=AccessRotationPolicy)
    audit_required: bool = True
    export_policy: AccessExportPolicy = field(default_factory=AccessExportPolicy)
    degraded_reason: str | None = None
    display_name: str | None = None
    masked_preview: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "resource_id",
            _normalize_text(self.resource_id, field_name="resource_id"),
        )
        object.__setattr__(self, "storage_key", _normalize_optional_text(self.storage_key))
        object.__setattr__(
            self,
            "consumer_modules",
            _normalize_text_tuple(self.consumer_modules),
        )
        object.__setattr__(self, "degraded_reason", _normalize_optional_text(self.degraded_reason))
        object.__setattr__(self, "display_name", _normalize_optional_text(self.display_name))
        object.__setattr__(self, "masked_preview", _normalize_optional_text(self.masked_preview))
        if self.resource_kind is AccessResourceKind.SECRET_ASSET and self.storage_key is None:
            raise ValueError("secret_asset resources require a storage_key binding.")
        if self.secret_policy.masked_preview_required and self.resource_kind in {
            AccessResourceKind.CREDENTIAL_BINDING,
            AccessResourceKind.SECRET_ASSET,
        } and self.masked_preview is None:
            raise ValueError("masked_preview is required for credential and secret resources.")


@dataclass(frozen=True, slots=True)
class AccessResourceRegistry:
    resources: tuple[AccessResourceDefinition, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        seen: set[str] = set()
        for resource in self.resources:
            if resource.resource_id in seen:
                raise ValueError(f"duplicate access resource '{resource.resource_id}'.")
            seen.add(resource.resource_id)

    def register(self, resource: AccessResourceDefinition) -> AccessResourceRegistry:
        if self.get(resource.resource_id) is not None:
            raise ValueError(f"duplicate access resource '{resource.resource_id}'.")
        return AccessResourceRegistry((*self.resources, resource))

    def get(self, resource_id: str) -> AccessResourceDefinition | None:
        normalized = resource_id.strip()
        if not normalized:
            return None
        for resource in self.resources:
            if resource.resource_id == normalized:
                return resource
        return None

    def require(self, resource_id: str) -> AccessResourceDefinition:
        resource = self.get(resource_id)
        if resource is None:
            raise KeyError(resource_id)
        return resource

    def by_kind(
        self,
        resource_kind: AccessResourceKind,
    ) -> tuple[AccessResourceDefinition, ...]:
        return tuple(
            resource for resource in self.resources if resource.resource_kind is resource_kind
        )

    def by_scope(
        self,
        governance_scope: AccessGovernanceScope,
    ) -> tuple[AccessResourceDefinition, ...]:
        return tuple(
            resource for resource in self.resources if resource.governance_scope is governance_scope
        )

    def by_consumer_module(self, module: str) -> tuple[AccessResourceDefinition, ...]:
        normalized = module.strip()
        if not normalized:
            return ()
        return tuple(
            resource for resource in self.resources if normalized in resource.consumer_modules
        )
