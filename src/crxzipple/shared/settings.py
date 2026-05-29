from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, fields, is_dataclass
from typing import Any, Generic, Protocol, TypeVar


JsonObject = dict[str, Any]
ConfigValueT = TypeVar("ConfigValueT")


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
    return tuple(
        dict.fromkeys(
            item.strip() for item in values if isinstance(item, str) and item.strip()
        ),
    )


def _mapping_payload(value: Mapping[str, Any] | None) -> JsonObject:
    if value is None:
        return {}
    return dict(value)


def _tuple_from_payload(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return _normalize_text_tuple((value,))
    if isinstance(value, tuple):
        return _normalize_text_tuple(tuple(str(item) for item in value))
    if isinstance(value, list):
        return _normalize_text_tuple(tuple(str(item) for item in value))
    return ()


def _bool_from_payload(value: object, *, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"0", "false", "no", "off"}:
            return False
        if normalized in {"1", "true", "yes", "on"}:
            return True
    return bool(value)


def _credential_bindings_value(
    value: object,
) -> Mapping[str, Any] | tuple[Mapping[str, Any], ...]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, (list, tuple)):
        return tuple(dict(item) for item in value if isinstance(item, Mapping))
    return {}


def _mapping_tuple_from_payload(value: object) -> tuple[Mapping[str, Any], ...]:
    if isinstance(value, Mapping):
        return (dict(value),)
    if isinstance(value, (list, tuple)):
        return tuple(dict(item) for item in value if isinstance(item, Mapping))
    return ()


def _payload_value(value: Any) -> Any:
    to_payload = getattr(value, "to_payload", None)
    if callable(to_payload):
        return to_payload()
    if is_dataclass(value):
        return {
            item.name: _payload_value(getattr(value, item.name))
            for item in fields(value)
        }
    if isinstance(value, Mapping):
        return {str(key): _payload_value(nested) for key, nested in value.items()}
    if isinstance(value, tuple):
        return [_payload_value(item) for item in value]
    if isinstance(value, list):
        return [_payload_value(item) for item in value]
    return value


def _dataclass_payload(value: object) -> JsonObject:
    return {
        item.name: _payload_value(getattr(value, item.name)) for item in fields(value)
    }


@dataclass(frozen=True, slots=True)
class SettingsResourceRef:
    resource_id: str
    resource_kind: str
    owner_module: str = "settings"
    scope: str = "global"
    display_name: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "resource_id",
            _normalize_text(self.resource_id, field_name="resource_id"),
        )
        object.__setattr__(
            self,
            "resource_kind",
            _normalize_text(self.resource_kind, field_name="resource_kind"),
        )
        object.__setattr__(
            self,
            "owner_module",
            _normalize_text(self.owner_module, field_name="owner_module"),
        )
        object.__setattr__(
            self, "scope", _normalize_text(self.scope, field_name="scope")
        )
        object.__setattr__(
            self, "display_name", _normalize_optional_text(self.display_name)
        )

    @property
    def key(self) -> tuple[str, str]:
        return (self.resource_kind, self.resource_id)

    def to_payload(self) -> JsonObject:
        return {
            "resource_id": self.resource_id,
            "resource_kind": self.resource_kind,
            "owner_module": self.owner_module,
            "scope": self.scope,
            "display_name": self.display_name,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "SettingsResourceRef":
        return cls(
            resource_id=str(payload.get("resource_id") or payload.get("id") or ""),
            resource_kind=str(
                payload.get("resource_kind") or payload.get("kind") or ""
            ),
            owner_module=str(
                payload.get("owner_module") or payload.get("module") or "settings"
            ),
            scope=str(payload.get("scope") or "global"),
            display_name=(
                str(payload["display_name"])
                if payload.get("display_name") is not None
                else None
            ),
            metadata=_mapping_payload(
                payload.get("metadata") if isinstance(payload, Mapping) else None
            ),
        )


@dataclass(frozen=True, slots=True)
class ConfigSource:
    source_id: str
    source_kind: str
    resource: SettingsResourceRef | None = None
    version_id: str | None = None
    override_id: str | None = None
    priority: int = 0
    applied: bool = True
    reason: str | None = None
    value: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_id",
            _normalize_text(self.source_id, field_name="source_id"),
        )
        object.__setattr__(
            self,
            "source_kind",
            _normalize_text(self.source_kind, field_name="source_kind"),
        )
        object.__setattr__(
            self, "version_id", _normalize_optional_text(self.version_id)
        )
        object.__setattr__(
            self, "override_id", _normalize_optional_text(self.override_id)
        )
        object.__setattr__(self, "reason", _normalize_optional_text(self.reason))

    def to_payload(self) -> JsonObject:
        return {
            "source_id": self.source_id,
            "source_kind": self.source_kind,
            "resource": (
                self.resource.to_payload() if self.resource is not None else None
            ),
            "version_id": self.version_id,
            "override_id": self.override_id,
            "priority": self.priority,
            "applied": self.applied,
            "reason": self.reason,
            "value": dict(self.value),
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "ConfigSource":
        raw_resource = payload.get("resource")
        return cls(
            source_id=str(payload.get("source_id") or payload.get("id") or ""),
            source_kind=str(payload.get("source_kind") or payload.get("kind") or ""),
            resource=(
                SettingsResourceRef.from_payload(raw_resource)
                if isinstance(raw_resource, Mapping)
                else None
            ),
            version_id=(
                str(payload["version_id"])
                if payload.get("version_id") is not None
                else None
            ),
            override_id=(
                str(payload["override_id"])
                if payload.get("override_id") is not None
                else None
            ),
            priority=int(payload.get("priority") or 0),
            applied=bool(payload.get("applied", True)),
            reason=(
                str(payload["reason"]) if payload.get("reason") is not None else None
            ),
            value=_mapping_payload(
                payload.get("value")
                if isinstance(payload.get("value"), Mapping)
                else None
            ),
            metadata=_mapping_payload(
                payload.get("metadata")
                if isinstance(payload.get("metadata"), Mapping)
                else None
            ),
        )


@dataclass(frozen=True, slots=True)
class ConfigResolution(Generic[ConfigValueT]):
    resource: SettingsResourceRef
    effective_value: ConfigValueT
    sources: tuple[ConfigSource, ...] = field(default_factory=tuple)
    overrides: tuple[ConfigSource, ...] = field(default_factory=tuple)
    snapshot_id: str | None = None
    resolved_at: str | None = None
    validation: Mapping[str, Any] = field(default_factory=dict)
    trace_context: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "sources", tuple(self.sources))
        object.__setattr__(self, "overrides", tuple(self.overrides))
        object.__setattr__(
            self, "snapshot_id", _normalize_optional_text(self.snapshot_id)
        )
        object.__setattr__(
            self, "resolved_at", _normalize_optional_text(self.resolved_at)
        )

    @property
    def value(self) -> ConfigValueT:
        return self.effective_value

    def to_payload(self) -> JsonObject:
        return {
            "resource": self.resource.to_payload(),
            "effective_value": _payload_value(self.effective_value),
            "value": _payload_value(self.effective_value),
            "sources": [source.to_payload() for source in self.sources],
            "overrides": [source.to_payload() for source in self.overrides],
            "snapshot_id": self.snapshot_id,
            "resolved_at": self.resolved_at,
            "validation": dict(self.validation),
            "trace_context": dict(self.trace_context),
        }

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "ConfigResolution[Any]":
        raw_resource = payload.get("resource")
        if not isinstance(raw_resource, Mapping):
            raise ValueError("resource is required.")
        return cls(
            resource=SettingsResourceRef.from_payload(raw_resource),
            effective_value=payload.get("effective_value", payload.get("value")),
            sources=tuple(
                ConfigSource.from_payload(item)
                for item in payload.get("sources", ())
                if isinstance(item, Mapping)
            ),
            overrides=tuple(
                ConfigSource.from_payload(item)
                for item in payload.get("overrides", ())
                if isinstance(item, Mapping)
            ),
            snapshot_id=(
                str(payload["snapshot_id"])
                if payload.get("snapshot_id") is not None
                else None
            ),
            resolved_at=(
                str(payload["resolved_at"])
                if payload.get("resolved_at") is not None
                else None
            ),
            validation=_mapping_payload(
                payload.get("validation")
                if isinstance(payload.get("validation"), Mapping)
                else None
            ),
            trace_context=_mapping_payload(
                payload.get("trace_context")
                if isinstance(payload.get("trace_context"), Mapping)
                else None
            ),
        )


class EffectiveSettingsProvider(Protocol[ConfigValueT]):
    def resolve_effective(
        self,
        resource: SettingsResourceRef,
        *,
        environment: str | None = None,
        trace_context: Mapping[str, Any] | None = None,
    ) -> ConfigResolution[ConfigValueT]: ...


@dataclass(frozen=True, slots=True)
class ToolProviderConfig:
    provider_id: str
    provider_kind: str
    enabled: bool = True
    display_name: str | None = None
    description: str = ""
    base_url: str | None = None
    spec_path: str | None = None
    package_ref: str | None = None
    credential_bindings: Mapping[str, Any] | tuple[Mapping[str, Any], ...] = field(
        default_factory=dict
    )
    command: tuple[str, ...] = field(default_factory=tuple)
    timeout_seconds: int = 30
    max_concurrency: int | None = None
    default_effect_ids: tuple[str, ...] = field(default_factory=tuple)
    discovery: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "provider_id",
            _normalize_text(self.provider_id, field_name="provider_id"),
        )
        object.__setattr__(
            self,
            "provider_kind",
            _normalize_text(self.provider_kind, field_name="provider_kind"),
        )
        object.__setattr__(
            self, "display_name", _normalize_optional_text(self.display_name)
        )
        object.__setattr__(self, "base_url", _normalize_optional_text(self.base_url))
        object.__setattr__(self, "spec_path", _normalize_optional_text(self.spec_path))
        object.__setattr__(
            self, "package_ref", _normalize_optional_text(self.package_ref)
        )
        object.__setattr__(
            self,
            "credential_bindings",
            _credential_bindings_value(self.credential_bindings),
        )
        object.__setattr__(self, "command", _normalize_text_tuple(self.command))
        object.__setattr__(
            self, "default_effect_ids", _normalize_text_tuple(self.default_effect_ids)
        )
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive.")
        if self.max_concurrency is not None and self.max_concurrency <= 0:
            raise ValueError("max_concurrency must be positive when provided.")

    def to_payload(self) -> JsonObject:
        return _dataclass_payload(self)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "ToolProviderConfig":
        if payload.get("credential_binding") is not None:
            raise ValueError(
                "Tool provider config must use credential_bindings with Access binding ids.",
            )
        return cls(
            provider_id=str(payload.get("provider_id") or payload.get("id") or ""),
            provider_kind=str(
                payload.get("provider_kind") or payload.get("kind") or ""
            ),
            enabled=bool(payload.get("enabled", True)),
            display_name=(
                str(payload["display_name"])
                if payload.get("display_name") is not None
                else None
            ),
            description=str(payload.get("description") or ""),
            base_url=(
                str(payload["base_url"])
                if payload.get("base_url") is not None
                else None
            ),
            spec_path=(
                str(payload.get("spec_path") or payload.get("spec_location"))
                if payload.get("spec_path") is not None
                or payload.get("spec_location") is not None
                else None
            ),
            package_ref=(
                str(payload["package_ref"])
                if payload.get("package_ref") is not None
                else None
            ),
            credential_bindings=_credential_bindings_value(
                (
                    payload.get("credential_bindings")
                    if payload.get("credential_bindings") is not None
                    else payload.get("credentials")
                ),
            ),
            command=_tuple_from_payload(payload.get("command")),
            timeout_seconds=int(payload.get("timeout_seconds") or 30),
            max_concurrency=(
                int(payload["max_concurrency"])
                if payload.get("max_concurrency") is not None
                else None
            ),
            default_effect_ids=_tuple_from_payload(payload.get("default_effect_ids")),
            discovery=_mapping_payload(
                payload.get("discovery")
                if isinstance(payload.get("discovery"), Mapping)
                else None
            ),
            metadata=_mapping_payload(
                payload.get("metadata")
                if isinstance(payload.get("metadata"), Mapping)
                else None
            ),
        )


@dataclass(frozen=True, slots=True)
class ToolRootConfig:
    root_id: str
    path: str
    enabled: bool = True
    source_kind: str = "local"
    recursive: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "root_id", _normalize_text(self.root_id, field_name="root_id")
        )
        object.__setattr__(self, "path", _normalize_text(self.path, field_name="path"))
        object.__setattr__(
            self,
            "source_kind",
            _normalize_text(self.source_kind, field_name="source_kind"),
        )

    def to_payload(self) -> JsonObject:
        return _dataclass_payload(self)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "ToolRootConfig":
        return cls(
            root_id=str(payload.get("root_id") or payload.get("id") or ""),
            path=str(payload.get("path") or ""),
            enabled=bool(payload.get("enabled", True)),
            source_kind=str(payload.get("source_kind") or "local"),
            recursive=bool(payload.get("recursive", True)),
            metadata=_mapping_payload(
                payload.get("metadata")
                if isinstance(payload.get("metadata"), Mapping)
                else None
            ),
        )

@dataclass(frozen=True, slots=True)
class AccessConfig:
    config_id: str
    enabled: bool = True
    assets: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    credential_bindings: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    consumer_bindings: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    provider_scope_enablements: tuple[Mapping[str, Any], ...] = field(
        default_factory=tuple
    )
    permission_enablements: tuple[Mapping[str, Any], ...] = field(default_factory=tuple)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "config_id", _normalize_text(self.config_id, field_name="config_id")
        )
        object.__setattr__(self, "assets", tuple(dict(item) for item in self.assets))
        object.__setattr__(
            self,
            "credential_bindings",
            tuple(dict(item) for item in self.credential_bindings),
        )
        object.__setattr__(
            self,
            "consumer_bindings",
            tuple(dict(item) for item in self.consumer_bindings),
        )
        object.__setattr__(
            self,
            "provider_scope_enablements",
            tuple(dict(item) for item in self.provider_scope_enablements),
        )
        object.__setattr__(
            self,
            "permission_enablements",
            tuple(dict(item) for item in self.permission_enablements),
        )

    def to_payload(self) -> JsonObject:
        return _dataclass_payload(self)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "AccessConfig":
        return cls(
            config_id=str(payload.get("config_id") or payload.get("id") or ""),
            enabled=bool(payload.get("enabled", True)),
            assets=_mapping_tuple_from_payload(payload.get("assets")),
            credential_bindings=_mapping_tuple_from_payload(
                payload.get("credential_bindings"),
            ),
            consumer_bindings=_mapping_tuple_from_payload(
                payload.get("consumer_bindings"),
            ),
            provider_scope_enablements=_mapping_tuple_from_payload(
                payload.get("provider_scope_enablements"),
            ),
            permission_enablements=_mapping_tuple_from_payload(
                payload.get("permission_enablements"),
            ),
            metadata=_mapping_payload(
                payload.get("metadata")
                if isinstance(payload.get("metadata"), Mapping)
                else None
            ),
        )


@dataclass(frozen=True, slots=True)
class MemoryConfig:
    config_id: str
    enabled: bool = True
    storage_root: str | None = None
    retrieval_backend: str = "keyword"
    vector_provider: str = "local"
    vector_model: str | None = None
    vector_base_url: str | None = None
    vector_credential_binding_id: str | None = None
    vector_timeout_seconds: int = 30
    watch_interval_seconds: float | None = None
    defaults: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "config_id", _normalize_text(self.config_id, field_name="config_id")
        )
        object.__setattr__(
            self, "storage_root", _normalize_optional_text(self.storage_root)
        )
        object.__setattr__(
            self,
            "retrieval_backend",
            _normalize_text(self.retrieval_backend, field_name="retrieval_backend"),
        )
        object.__setattr__(
            self,
            "vector_provider",
            _normalize_text(self.vector_provider, field_name="vector_provider"),
        )
        object.__setattr__(
            self, "vector_model", _normalize_optional_text(self.vector_model)
        )
        object.__setattr__(
            self, "vector_base_url", _normalize_optional_text(self.vector_base_url)
        )
        object.__setattr__(
            self,
            "vector_credential_binding_id",
            _normalize_optional_text(self.vector_credential_binding_id),
        )
        if self.vector_timeout_seconds <= 0:
            raise ValueError("vector_timeout_seconds must be positive.")
        if self.watch_interval_seconds is not None and self.watch_interval_seconds < 0:
            raise ValueError("watch_interval_seconds cannot be negative.")

    def to_payload(self) -> JsonObject:
        return _dataclass_payload(self)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "MemoryConfig":
        if payload.get("vector_credential_binding") is not None:
            raise ValueError(
                "Memory config must use vector_credential_binding_id.",
            )
        return cls(
            config_id=str(payload.get("config_id") or payload.get("id") or ""),
            enabled=bool(payload.get("enabled", True)),
            storage_root=(
                str(payload["storage_root"])
                if payload.get("storage_root") is not None
                else None
            ),
            retrieval_backend=str(payload.get("retrieval_backend") or "keyword"),
            vector_provider=str(payload.get("vector_provider") or "local"),
            vector_model=(
                str(payload["vector_model"])
                if payload.get("vector_model") is not None
                else None
            ),
            vector_base_url=(
                str(payload["vector_base_url"])
                if payload.get("vector_base_url") is not None
                else None
            ),
            vector_credential_binding_id=(
                str(payload["vector_credential_binding_id"])
                if payload.get("vector_credential_binding_id") is not None
                else None
            ),
            vector_timeout_seconds=int(payload.get("vector_timeout_seconds") or 30),
            watch_interval_seconds=(
                float(payload["watch_interval_seconds"])
                if payload.get("watch_interval_seconds") is not None
                else None
            ),
            defaults=_mapping_payload(
                payload.get("defaults")
                if isinstance(payload.get("defaults"), Mapping)
                else None
            ),
            metadata=_mapping_payload(
                payload.get("metadata")
                if isinstance(payload.get("metadata"), Mapping)
                else None
            ),
        )


@dataclass(frozen=True, slots=True)
class RuntimeDefaultsConfig:
    config_id: str
    enabled: bool = True
    orchestration: Mapping[str, Any] = field(default_factory=dict)
    tool_worker: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "config_id", _normalize_text(self.config_id, field_name="config_id")
        )

    def to_payload(self) -> JsonObject:
        return _dataclass_payload(self)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "RuntimeDefaultsConfig":
        return cls(
            config_id=str(payload.get("config_id") or payload.get("id") or ""),
            enabled=bool(payload.get("enabled", True)),
            orchestration=_mapping_payload(
                payload.get("orchestration")
                if isinstance(payload.get("orchestration"), Mapping)
                else None
            ),
            tool_worker=_mapping_payload(
                payload.get("tool_worker")
                if isinstance(payload.get("tool_worker"), Mapping)
                else None
            ),
            metadata=_mapping_payload(
                payload.get("metadata")
                if isinstance(payload.get("metadata"), Mapping)
                else None
            ),
        )


@dataclass(frozen=True, slots=True)
class EnvironmentOverrideConfig:
    override_id: str
    environment: str
    target: SettingsResourceRef
    values: Mapping[str, Any]
    enabled: bool = True
    priority: int = 100
    reason: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "override_id",
            _normalize_text(self.override_id, field_name="override_id"),
        )
        object.__setattr__(
            self,
            "environment",
            _normalize_text(self.environment, field_name="environment"),
        )
        object.__setattr__(self, "reason", _normalize_optional_text(self.reason))

    def to_payload(self) -> JsonObject:
        return _dataclass_payload(self)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> "EnvironmentOverrideConfig":
        raw_target = payload.get("target")
        if not isinstance(raw_target, Mapping):
            raise ValueError("target is required.")
        return cls(
            override_id=str(payload.get("override_id") or payload.get("id") or ""),
            environment=str(payload.get("environment") or ""),
            target=SettingsResourceRef.from_payload(raw_target),
            values=_mapping_payload(
                payload.get("values")
                if isinstance(payload.get("values"), Mapping)
                else None
            ),
            enabled=bool(payload.get("enabled", True)),
            priority=int(payload.get("priority") or 100),
            reason=(
                str(payload["reason"]) if payload.get("reason") is not None else None
            ),
            metadata=_mapping_payload(
                payload.get("metadata")
                if isinstance(payload.get("metadata"), Mapping)
                else None
            ),
        )
