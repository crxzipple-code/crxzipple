from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, fields, is_dataclass, replace
from datetime import datetime, timezone
from enum import StrEnum
from hashlib import sha256
import json
from typing import Any
from uuid import uuid4

from crxzipple.modules.tool.application.specifications import ToolSpec
from crxzipple.modules.tool.domain.exceptions import ToolValidationError
from crxzipple.modules.tool.domain.value_objects import (
    ToolEnvironment,
    ToolKind,
)
from crxzipple.shared.access import AccessCredentialRequirementSet


class ToolSourceCatalogKind(StrEnum):
    LOCAL_PACKAGE = "local_package"
    MCP = "mcp"
    OPENAPI = "openapi"
    CLI = "cli"
    PROVIDER_BACKEND = "provider_backend"


class ToolSourceStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"
    ERROR = "error"
    DELETED = "deleted"


class ToolSourceDiscoveryStatus(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"


class ToolFunctionRuntimeKind(StrEnum):
    LOCAL = "local"
    REMOTE = "remote"
    SANDBOX = "sandbox"
    MCP = "mcp"
    OPENAPI = "openapi"
    CLI = "cli"
    PROVIDER_BACKEND = "provider_backend"


class ToolFunctionStatus(StrEnum):
    ACTIVE = "active"
    STALE = "stale"
    DEPRECATED = "deprecated"
    DISABLED = "disabled"
    DELETED = "deleted"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class ToolFunctionRequirements:
    credential_requirements: tuple[AccessCredentialRequirementSet, ...] = ()
    access_requirement_sets: tuple[tuple[str, ...], ...] = ()
    runtime_requirement_sets: tuple[tuple[str, ...], ...] = ()
    required_effect_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "credential_requirements",
            tuple(self.credential_requirements),
        )
        object.__setattr__(
            self,
            "access_requirement_sets",
            _normalize_text_sets(self.access_requirement_sets),
        )
        object.__setattr__(
            self,
            "runtime_requirement_sets",
            _normalize_text_sets(self.runtime_requirement_sets),
        )
        object.__setattr__(
            self,
            "required_effect_ids",
            _normalize_text_tuple(self.required_effect_ids),
        )


@dataclass(frozen=True, slots=True)
class ToolSourceCatalogRecord:
    source_id: str
    kind: ToolSourceCatalogKind | str
    display_name: str
    description: str = ""
    config: Mapping[str, Any] = field(default_factory=dict)
    credential_requirements: tuple[AccessCredentialRequirementSet, ...] = ()
    runtime_requirements: tuple[str, ...] = ()
    status: ToolSourceStatus | str = ToolSourceStatus.ACTIVE
    revision: int = 1
    config_hash: str = ""
    last_discovered_at: datetime | None = None
    last_discovery_status: ToolSourceDiscoveryStatus | str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_id",
            _required_text(self.source_id, field_name="source_id"),
        )
        object.__setattr__(self, "kind", ToolSourceCatalogKind(str(self.kind)))
        object.__setattr__(
            self,
            "display_name",
            _required_text(self.display_name, field_name="display_name"),
        )
        object.__setattr__(self, "description", str(self.description).strip())
        config = _normalize_mapping(self.config, field_name="config")
        object.__setattr__(self, "config", config)
        object.__setattr__(
            self,
            "credential_requirements",
            tuple(self.credential_requirements),
        )
        object.__setattr__(
            self,
            "runtime_requirements",
            _normalize_text_tuple(self.runtime_requirements),
        )
        object.__setattr__(self, "status", ToolSourceStatus(str(self.status)))
        if self.revision < 1:
            raise ToolValidationError("Tool source revision must be at least 1.")
        config_hash = str(self.config_hash).strip()
        if not config_hash:
            config_hash = _hash_payload({"config": config})
        object.__setattr__(self, "config_hash", config_hash)
        if self.last_discovery_status is not None:
            object.__setattr__(
                self,
                "last_discovery_status",
                ToolSourceDiscoveryStatus(str(self.last_discovery_status)),
            )


@dataclass(frozen=True, slots=True)
class ToolFunctionCandidate:
    stable_key: str
    source_id: str
    function_id: str
    name: str
    description: str
    input_schema: Mapping[str, Any]
    runtime_kind: ToolFunctionRuntimeKind | str
    handler_ref: str
    requirements: ToolFunctionRequirements = field(
        default_factory=ToolFunctionRequirements,
    )
    capabilities: tuple[str, ...] = ()
    schema_hash: str = ""
    enabled: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "stable_key",
            _required_text(self.stable_key, field_name="stable_key"),
        )
        object.__setattr__(
            self,
            "source_id",
            _required_text(self.source_id, field_name="source_id"),
        )
        object.__setattr__(
            self,
            "function_id",
            _required_text(self.function_id, field_name="function_id"),
        )
        object.__setattr__(
            self,
            "name",
            _required_text(self.name, field_name="name"),
        )
        object.__setattr__(
            self,
            "description",
            _required_text(self.description, field_name="description"),
        )
        object.__setattr__(
            self,
            "input_schema",
            _normalize_mapping(self.input_schema, field_name="input_schema"),
        )
        object.__setattr__(
            self,
            "runtime_kind",
            ToolFunctionRuntimeKind(str(self.runtime_kind)),
        )
        object.__setattr__(
            self,
            "handler_ref",
            _required_text(self.handler_ref, field_name="handler_ref"),
        )
        if not isinstance(self.requirements, ToolFunctionRequirements):
            raise ToolValidationError("Tool function candidate requirements are invalid.")
        object.__setattr__(self, "capabilities", _normalize_text_tuple(self.capabilities))
        object.__setattr__(
            self,
            "metadata",
            _normalize_mapping(self.metadata, field_name="metadata"),
        )
        schema_hash = str(self.schema_hash).strip()
        if not schema_hash:
            schema_hash = compute_tool_function_schema_hash(
                input_schema=self.input_schema,
                runtime_kind=self.runtime_kind,
                handler_ref=self.handler_ref,
                requirements=self.requirements,
                capabilities=self.capabilities,
            )
        object.__setattr__(self, "schema_hash", schema_hash)

    @property
    def capability_ids(self) -> tuple[str, ...]:
        return self.capabilities

    @classmethod
    def from_tool_spec(
        cls,
        spec: ToolSpec,
        *,
        source_id: str | None = None,
        stable_key: str | None = None,
        runtime_kind: ToolFunctionRuntimeKind | str | None = None,
        handler_ref: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> "ToolFunctionCandidate":
        resolved_source_id = source_id or spec.provider_name
        resolved_runtime_kind = (
            ToolFunctionRuntimeKind(str(runtime_kind))
            if runtime_kind is not None
            else _runtime_kind_from_tool_spec(spec)
        )
        resolved_handler_ref = handler_ref or spec.runtime_key or spec.id
        resolved_stable_key = stable_key or _stable_key_from_tool_spec(
            spec,
            source_id=resolved_source_id,
            runtime_kind=resolved_runtime_kind,
        )
        return cls(
            stable_key=resolved_stable_key,
            source_id=resolved_source_id,
            function_id=spec.id,
            name=spec.name,
            description=spec.description,
            input_schema=_input_schema_from_tool_spec(spec),
            runtime_kind=resolved_runtime_kind,
            handler_ref=resolved_handler_ref,
            requirements=ToolFunctionRequirements(
                credential_requirements=spec.credential_requirements,
                access_requirement_sets=spec.access_requirement_sets,
                runtime_requirement_sets=spec.runtime_requirement_sets,
                required_effect_ids=spec.required_effect_ids,
            ),
            capabilities=spec.capability_ids,
            enabled=spec.enabled,
            metadata={
                "tool_kind": spec.kind.value,
                "definition_origin": spec.definition_origin.value,
                "tags": spec.tags,
                "runtime_key": spec.runtime_key,
                "execution_policy": {
                    "timeout_seconds": spec.execution_policy.timeout_seconds,
                    "requires_confirmation": (
                        spec.execution_policy.requires_confirmation
                    ),
                    "mutates_state": spec.execution_policy.mutates_state,
                },
                "execution_support": {
                    "supported_modes": tuple(
                        mode.value for mode in spec.execution_support.supported_modes
                    ),
                    "supported_strategies": tuple(
                        strategy.value
                        for strategy in spec.execution_support.supported_strategies
                    ),
                    "supported_environments": tuple(
                        environment.value
                        for environment in spec.execution_support.supported_environments
                    ),
                },
                "context_requirements": spec.context_requirements,
                **dict(metadata or {}),
            },
        )


@dataclass(frozen=True, slots=True)
class ToolProviderBackendCandidate:
    source_id: str
    backend_id: str
    capability: str
    display_name: str
    runtime_kind: ToolFunctionRuntimeKind | str
    runtime_ref: str
    requirements: ToolFunctionRequirements = field(
        default_factory=ToolFunctionRequirements,
    )
    priority: int = 100
    enabled: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_id",
            _required_text(self.source_id, field_name="source_id"),
        )
        object.__setattr__(
            self,
            "backend_id",
            _required_text(self.backend_id, field_name="backend_id"),
        )
        object.__setattr__(
            self,
            "capability",
            _required_text(self.capability, field_name="capability"),
        )
        object.__setattr__(
            self,
            "display_name",
            _required_text(self.display_name, field_name="display_name"),
        )
        object.__setattr__(
            self,
            "runtime_kind",
            ToolFunctionRuntimeKind(str(self.runtime_kind)),
        )
        object.__setattr__(
            self,
            "runtime_ref",
            _required_text(self.runtime_ref, field_name="runtime_ref"),
        )
        if not isinstance(self.requirements, ToolFunctionRequirements):
            raise ToolValidationError("Tool provider backend requirements are invalid.")
        object.__setattr__(
            self,
            "metadata",
            _normalize_mapping(self.metadata, field_name="metadata"),
        )


@dataclass(frozen=True, slots=True)
class ToolSourceDiscoveryResult:
    source_id: str
    candidates: tuple[ToolFunctionCandidate, ...] = ()
    provider_backend_candidates: tuple[ToolProviderBackendCandidate, ...] = ()
    discovered_at: datetime = field(default_factory=_utc_now)
    status: ToolSourceDiscoveryStatus | str = ToolSourceDiscoveryStatus.COMPLETED
    error_message: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        source_id = _required_text(self.source_id, field_name="source_id")
        object.__setattr__(self, "source_id", source_id)
        object.__setattr__(self, "candidates", tuple(self.candidates))
        object.__setattr__(
            self,
            "provider_backend_candidates",
            tuple(self.provider_backend_candidates),
        )
        object.__setattr__(self, "status", ToolSourceDiscoveryStatus(str(self.status)))
        error_message = (
            str(self.error_message).strip()
            if self.error_message is not None
            else None
        )
        object.__setattr__(self, "error_message", error_message or None)
        object.__setattr__(
            self,
            "metadata",
            _normalize_mapping(self.metadata, field_name="metadata"),
        )
        for candidate in self.candidates:
            if candidate.source_id != source_id:
                raise ToolValidationError(
                    "Tool discovery result candidate source_id must match result source_id.",
                )
        for candidate in self.provider_backend_candidates:
            if candidate.source_id != source_id:
                raise ToolValidationError(
                    "Tool discovery result backend source_id must match result source_id.",
                )

    @classmethod
    def completed(
        cls,
        *,
        source_id: str,
        candidates: tuple[ToolFunctionCandidate, ...] = (),
        provider_backend_candidates: tuple[ToolProviderBackendCandidate, ...] = (),
        discovered_at: datetime | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> "ToolSourceDiscoveryResult":
        return cls(
            source_id=source_id,
            candidates=candidates,
            provider_backend_candidates=provider_backend_candidates,
            discovered_at=discovered_at or _utc_now(),
            status=ToolSourceDiscoveryStatus.COMPLETED,
            metadata=dict(metadata or {}),
        )

    @classmethod
    def failed(
        cls,
        *,
        source_id: str,
        error_message: str,
        discovered_at: datetime | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> "ToolSourceDiscoveryResult":
        return cls(
            source_id=source_id,
            discovered_at=discovered_at or _utc_now(),
            status=ToolSourceDiscoveryStatus.FAILED,
            error_message=error_message,
            metadata=dict(metadata or {}),
        )


@dataclass(frozen=True, slots=True)
class ToolSourceDiscoveryRunRecord:
    discovery_run_id: str
    source_id: str
    source_revision: int
    config_hash: str
    status: ToolSourceDiscoveryStatus | str
    discovered_at: datetime
    function_count: int = 0
    provider_backend_count: int = 0
    error_message: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        discovery_run_id = str(self.discovery_run_id or "").strip() or uuid4().hex
        object.__setattr__(self, "discovery_run_id", discovery_run_id)
        object.__setattr__(
            self,
            "source_id",
            _required_text(self.source_id, field_name="source_id"),
        )
        if self.source_revision < 1:
            raise ToolValidationError("Tool source discovery source_revision must be at least 1.")
        object.__setattr__(
            self,
            "config_hash",
            _required_text(self.config_hash, field_name="config_hash"),
        )
        object.__setattr__(
            self,
            "status",
            ToolSourceDiscoveryStatus(str(self.status)),
        )
        if self.function_count < 0:
            raise ToolValidationError("Tool source discovery function_count must not be negative.")
        if self.provider_backend_count < 0:
            raise ToolValidationError(
                "Tool source discovery provider_backend_count must not be negative.",
            )
        error_message = (
            str(self.error_message).strip()
            if self.error_message is not None
            else None
        )
        object.__setattr__(self, "error_message", error_message or None)
        object.__setattr__(
            self,
            "metadata",
            _normalize_mapping(self.metadata, field_name="metadata"),
        )

    @classmethod
    def from_result(
        cls,
        *,
        source: ToolSourceCatalogRecord,
        discovery: ToolSourceDiscoveryResult,
        discovery_run_id: str | None = None,
    ) -> "ToolSourceDiscoveryRunRecord":
        return cls(
            discovery_run_id=discovery_run_id or uuid4().hex,
            source_id=source.source_id,
            source_revision=source.revision,
            config_hash=source.config_hash,
            status=discovery.status,
            discovered_at=discovery.discovered_at,
            function_count=len(discovery.candidates),
            provider_backend_count=len(discovery.provider_backend_candidates),
            error_message=discovery.error_message,
            metadata=discovery.metadata,
        )


@dataclass(frozen=True, slots=True)
class ToolFunctionCatalogRecord:
    function_id: str
    source_id: str
    stable_key: str
    name: str
    description: str
    input_schema: Mapping[str, Any]
    runtime_kind: ToolFunctionRuntimeKind | str
    handler_ref: str
    requirements: ToolFunctionRequirements = field(
        default_factory=ToolFunctionRequirements,
    )
    capabilities: tuple[str, ...] = ()
    schema_hash: str = ""
    status: ToolFunctionStatus | str = ToolFunctionStatus.ACTIVE
    revision: int = 1
    enabled: bool = True
    trust_policy: Mapping[str, Any] = field(default_factory=dict)
    approval_policy: Mapping[str, Any] = field(default_factory=dict)
    credential_binding_overrides: Mapping[str, str] = field(default_factory=dict)
    required_effect_overrides: tuple[str, ...] | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    last_seen_at: datetime | None = None
    stale_since: datetime | None = None
    deprecated_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "function_id",
            _required_text(self.function_id, field_name="function_id"),
        )
        object.__setattr__(
            self,
            "source_id",
            _required_text(self.source_id, field_name="source_id"),
        )
        object.__setattr__(
            self,
            "stable_key",
            _required_text(self.stable_key, field_name="stable_key"),
        )
        object.__setattr__(
            self,
            "name",
            _required_text(self.name, field_name="name"),
        )
        object.__setattr__(
            self,
            "description",
            _required_text(self.description, field_name="description"),
        )
        object.__setattr__(
            self,
            "input_schema",
            _normalize_mapping(self.input_schema, field_name="input_schema"),
        )
        object.__setattr__(
            self,
            "runtime_kind",
            ToolFunctionRuntimeKind(str(self.runtime_kind)),
        )
        object.__setattr__(
            self,
            "handler_ref",
            _required_text(self.handler_ref, field_name="handler_ref"),
        )
        if not isinstance(self.requirements, ToolFunctionRequirements):
            raise ToolValidationError("Tool function requirements are invalid.")
        object.__setattr__(self, "capabilities", _normalize_text_tuple(self.capabilities))
        schema_hash = str(self.schema_hash).strip()
        if not schema_hash:
            schema_hash = compute_tool_function_schema_hash(
                input_schema=self.input_schema,
                runtime_kind=self.runtime_kind,
                handler_ref=self.handler_ref,
                requirements=self.requirements,
                capabilities=self.capabilities,
            )
        object.__setattr__(self, "schema_hash", schema_hash)
        object.__setattr__(self, "status", ToolFunctionStatus(str(self.status)))
        if self.revision < 1:
            raise ToolValidationError("Tool function revision must be at least 1.")
        object.__setattr__(
            self,
            "trust_policy",
            _normalize_mapping(self.trust_policy, field_name="trust_policy"),
        )
        object.__setattr__(
            self,
            "approval_policy",
            _normalize_mapping(self.approval_policy, field_name="approval_policy"),
        )
        object.__setattr__(
            self,
            "credential_binding_overrides",
            {
                _required_text(str(key), field_name="credential_binding_override.key"): (
                    _required_text(str(value), field_name="credential_binding_override.value")
                )
                for key, value in self.credential_binding_overrides.items()
            },
        )
        if self.required_effect_overrides is not None:
            object.__setattr__(
                self,
                "required_effect_overrides",
                _normalize_text_tuple(self.required_effect_overrides),
            )
        object.__setattr__(
            self,
            "metadata",
            _normalize_mapping(self.metadata, field_name="metadata"),
        )

    @classmethod
    def from_candidate(
        cls,
        candidate: ToolFunctionCandidate,
        *,
        observed_at: datetime | None = None,
    ) -> "ToolFunctionCatalogRecord":
        now = observed_at or _utc_now()
        return cls(
            function_id=candidate.function_id,
            source_id=candidate.source_id,
            stable_key=candidate.stable_key,
            name=candidate.name,
            description=candidate.description,
            input_schema=candidate.input_schema,
            runtime_kind=candidate.runtime_kind,
            handler_ref=candidate.handler_ref,
            requirements=candidate.requirements,
            capabilities=candidate.capabilities,
            schema_hash=candidate.schema_hash,
            status=ToolFunctionStatus.ACTIVE,
            revision=1,
            enabled=candidate.enabled,
            metadata=candidate.metadata,
            created_at=now,
            updated_at=now,
            last_seen_at=now,
        )

    def changed_fields_from_candidate(
        self,
        candidate: ToolFunctionCandidate,
    ) -> tuple[str, ...]:
        changed: list[str] = []
        comparisons: tuple[tuple[str, Any, Any], ...] = (
            ("name", self.name, candidate.name),
            ("description", self.description, candidate.description),
            ("input_schema", self.input_schema, candidate.input_schema),
            ("runtime_kind", self.runtime_kind, candidate.runtime_kind),
            ("handler_ref", self.handler_ref, candidate.handler_ref),
            ("requirements", self.requirements, candidate.requirements),
            ("capabilities", self.capabilities, candidate.capabilities),
            ("schema_hash", self.schema_hash, candidate.schema_hash),
            ("metadata", self.metadata, candidate.metadata),
        )
        for field_name, existing, incoming in comparisons:
            if _stable_payload(existing) != _stable_payload(incoming):
                changed.append(field_name)
        if self.status is not ToolFunctionStatus.ACTIVE:
            changed.append("status")
        return tuple(changed)

    def seen_from_candidate(
        self,
        candidate: ToolFunctionCandidate,
        *,
        observed_at: datetime | None = None,
    ) -> "ToolFunctionCatalogRecord":
        changed_fields = self.changed_fields_from_candidate(candidate)
        if not changed_fields:
            return self
        now = observed_at or _utc_now()
        return replace(
            self,
            name=candidate.name,
            description=candidate.description,
            input_schema=candidate.input_schema,
            runtime_kind=candidate.runtime_kind,
            handler_ref=candidate.handler_ref,
            requirements=candidate.requirements,
            capabilities=candidate.capabilities,
            schema_hash=candidate.schema_hash,
            status=ToolFunctionStatus.ACTIVE,
            revision=self.revision + 1,
            metadata=candidate.metadata,
            updated_at=now,
            last_seen_at=now,
            stale_since=None,
            deprecated_at=None,
        )

    def mark_stale(
        self,
        *,
        observed_at: datetime | None = None,
    ) -> "ToolFunctionCatalogRecord":
        if self.status is not ToolFunctionStatus.ACTIVE:
            return self
        now = observed_at or _utc_now()
        return replace(
            self,
            status=ToolFunctionStatus.STALE,
            revision=self.revision + 1,
            updated_at=now,
            stale_since=now,
        )

    def mark_deprecated(
        self,
        *,
        observed_at: datetime | None = None,
    ) -> "ToolFunctionCatalogRecord":
        if self.status is ToolFunctionStatus.DEPRECATED:
            return self
        now = observed_at or _utc_now()
        return replace(
            self,
            status=ToolFunctionStatus.DEPRECATED,
            revision=self.revision + 1,
            updated_at=now,
            stale_since=self.stale_since or now,
            deprecated_at=now,
        )


def compute_tool_function_schema_hash(
    *,
    input_schema: Mapping[str, Any],
    runtime_kind: ToolFunctionRuntimeKind | str,
    handler_ref: str,
    requirements: ToolFunctionRequirements,
    capabilities: tuple[str, ...],
) -> str:
    return _hash_payload(
        {
            "schema_version": 1,
            "input_schema": input_schema,
            "runtime_kind": str(runtime_kind),
            "handler_ref": handler_ref,
            "requirements": requirements,
            "capabilities": capabilities,
        },
    )


def _required_text(value: str, *, field_name: str) -> str:
    normalized = value.strip() if isinstance(value, str) else ""
    if not normalized:
        raise ToolValidationError(f"Tool catalog {field_name} cannot be empty.")
    return normalized


def _normalize_text_tuple(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            value.strip()
            for value in values
            if isinstance(value, str) and value.strip()
        ),
    )


def _normalize_text_sets(
    values: tuple[tuple[str, ...], ...],
) -> tuple[tuple[str, ...], ...]:
    resolved: list[tuple[str, ...]] = []
    for value in values:
        normalized = _normalize_text_tuple(tuple(value))
        if normalized not in resolved:
            resolved.append(normalized)
    return tuple(resolved)


def _normalize_mapping(value: Mapping[str, Any], *, field_name: str) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ToolValidationError(f"Tool catalog {field_name} must be a mapping.")
    normalized = _stable_payload(value)
    assert isinstance(normalized, dict)
    return normalized


def _runtime_kind_from_tool_spec(spec: ToolSpec) -> ToolFunctionRuntimeKind:
    runtime_key = spec.runtime_key or ""
    runtime_prefix = runtime_key.split(".", 1)[0]
    if runtime_prefix in {kind.value for kind in ToolFunctionRuntimeKind}:
        return ToolFunctionRuntimeKind(runtime_prefix)
    if spec.kind is ToolKind.MCP:
        return ToolFunctionRuntimeKind.MCP
    if ToolEnvironment.SANDBOX in spec.execution_support.supported_environments:
        return ToolFunctionRuntimeKind.SANDBOX
    if ToolEnvironment.REMOTE in spec.execution_support.supported_environments:
        return ToolFunctionRuntimeKind.REMOTE
    return ToolFunctionRuntimeKind.LOCAL


def _stable_key_from_tool_spec(
    spec: ToolSpec,
    *,
    source_id: str,
    runtime_kind: ToolFunctionRuntimeKind,
) -> str:
    runtime_key = spec.runtime_key or ""
    runtime_prefix = runtime_key.split(".", 1)[0]
    if runtime_prefix in {
        ToolFunctionRuntimeKind.MCP.value,
        ToolFunctionRuntimeKind.OPENAPI.value,
        ToolFunctionRuntimeKind.CLI.value,
        ToolFunctionRuntimeKind.PROVIDER_BACKEND.value,
    }:
        return runtime_key
    source_prefix = (
        ToolSourceCatalogKind.LOCAL_PACKAGE.value
        if runtime_kind is ToolFunctionRuntimeKind.LOCAL
        else runtime_kind.value
    )
    return f"{source_prefix}.{source_id}.{spec.id}"


def _input_schema_from_tool_spec(spec: ToolSpec) -> dict[str, Any]:
    properties: dict[str, Any] = {}
    required: list[str] = []
    for parameter in spec.parameters:
        parameter_schema = _json_schema_for_data_type(parameter.data_type)
        if parameter.description:
            parameter_schema["description"] = parameter.description
        properties[parameter.name] = parameter_schema
        if parameter.required:
            required.append(parameter.name)
    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        schema["required"] = required
    return schema


def _json_schema_for_data_type(data_type: str) -> dict[str, Any]:
    normalized = data_type.strip().lower()
    if normalized.startswith("array[") and normalized.endswith("]"):
        item_type = normalized.removeprefix("array[").removesuffix("]")
        return {
            "type": "array",
            "items": _json_schema_for_data_type(item_type),
        }
    if normalized in {"string", "integer", "number", "boolean", "object", "array"}:
        return {"type": normalized}
    return {"type": "string", "x-crxzipple-data-type": data_type}


def _hash_payload(payload: Mapping[str, Any]) -> str:
    digest = sha256(_canonical_json(payload).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _canonical_json(payload: Any) -> str:
    return json.dumps(
        _stable_payload(payload),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )


def _stable_payload(value: Any) -> Any:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field_info.name: _stable_payload(getattr(value, field_info.name))
            for field_info in fields(value)
        }
    if isinstance(value, Mapping):
        return {
            str(key): _stable_payload(value[key])
            for key in sorted(value, key=lambda item: str(item))
        }
    if isinstance(value, tuple | list):
        return [_stable_payload(item) for item in value]
    if value is None or isinstance(value, bool | int | float | str):
        return value
    return str(value)


__all__ = [
    "ToolFunctionCandidate",
    "ToolFunctionCatalogRecord",
    "ToolFunctionRequirements",
    "ToolFunctionRuntimeKind",
    "ToolFunctionStatus",
    "ToolProviderBackendCandidate",
    "ToolSourceCatalogKind",
    "ToolSourceCatalogRecord",
    "ToolSourceDiscoveryRunRecord",
    "ToolSourceDiscoveryResult",
    "ToolSourceDiscoveryStatus",
    "ToolSourceStatus",
    "compute_tool_function_schema_hash",
]
