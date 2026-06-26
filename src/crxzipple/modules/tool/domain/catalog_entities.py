from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from crxzipple.modules.tool.domain.entity_normalization import (
    coerce_str_enum,
    normalize_access_requirement_sets,
    normalize_json_mapping,
    normalize_json_mapping_tuple,
    normalize_optional_text,
    normalize_text,
    normalize_text_tuple,
)
from crxzipple.modules.tool.domain.exceptions import ToolValidationError
from crxzipple.modules.tool.domain.value_objects import (
    ToolCatalogSourceKind,
    ToolDefinitionOrigin,
    ToolExecutionPolicy,
    ToolExecutionSupport,
    ToolExecutionTarget,
    ToolFunctionRuntimeKind,
    ToolFunctionStatus,
    ToolKind,
    ToolParameter,
    ToolProviderBackendStatus,
    ToolProviderCapability,
    ToolSourceStatus,
)
from crxzipple.shared.access import AccessCredentialRequirementSet
from crxzipple.shared.domain import AggregateRoot
from crxzipple.shared.domain.events import Event


@dataclass(kw_only=True)
class ToolSource(AggregateRoot[str]):
    display_name: str
    kind: ToolCatalogSourceKind = ToolCatalogSourceKind.LOCAL_PACKAGE
    description: str = ""
    config: dict[str, Any] = field(default_factory=dict)
    credential_requirements: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    runtime_requirements: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    status: ToolSourceStatus = ToolSourceStatus.ACTIVE
    revision: int = 1
    config_hash: str = ""
    last_discovered_at: datetime | None = None
    last_discovery_status: str | None = None
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    updated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc),
    )

    @property
    def source_id(self) -> str:
        return self.id

    def __post_init__(self) -> None:
        self.id = normalize_text(self.id, field_name="Tool source id")
        self.kind = coerce_str_enum(
            ToolCatalogSourceKind,
            self.kind,
            field_name="tool source kind",
        )
        self.display_name = normalize_text(
            self.display_name,
            field_name="Tool source display_name",
        )
        self.description = self.description.strip()
        self.config = normalize_json_mapping(self.config)
        self.credential_requirements = normalize_json_mapping_tuple(
            self.credential_requirements,
        )
        self.runtime_requirements = normalize_json_mapping_tuple(
            self.runtime_requirements,
        )
        self.status = coerce_str_enum(
            ToolSourceStatus,
            self.status,
            field_name="tool source status",
        )
        if self.revision < 1:
            raise ToolValidationError("Tool source revision must be at least 1.")
        self.config_hash = self.config_hash.strip()
        self.last_discovery_status = normalize_optional_text(
            self.last_discovery_status,
        )


@dataclass(kw_only=True)
class ToolFunction(AggregateRoot[str]):
    source_id: str
    stable_key: str
    name: str
    display_name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)
    runtime_kind: ToolFunctionRuntimeKind = ToolFunctionRuntimeKind.LOCAL
    handler_ref: dict[str, Any] = field(default_factory=dict)
    capability_ids: tuple[str, ...] = field(default_factory=tuple)
    credential_requirements: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    access_requirement_sets: tuple[tuple[str, ...], ...] = field(default_factory=tuple)
    runtime_requirements: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    required_effect_ids: tuple[str, ...] = field(default_factory=tuple)
    execution_support: ToolExecutionSupport = field(
        default_factory=ToolExecutionSupport,
    )
    enabled: bool = True
    trust_policy: dict[str, Any] = field(default_factory=dict)
    approval_policy: dict[str, Any] = field(default_factory=dict)
    credential_binding_overrides: dict[str, str] = field(default_factory=dict)
    required_effect_overrides: tuple[str, ...] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_hash: str = ""
    status: ToolFunctionStatus = ToolFunctionStatus.ACTIVE
    revision: int = 1
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    updated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    last_seen_at: datetime | None = None
    stale_since: datetime | None = None
    deprecated_at: datetime | None = None

    @property
    def function_id(self) -> str:
        return self.id

    def __post_init__(self) -> None:
        self.id = normalize_text(self.id, field_name="Tool function id")
        self.source_id = normalize_text(
            self.source_id,
            field_name="Tool function source_id",
        )
        self.stable_key = normalize_text(
            self.stable_key,
            field_name="Tool function stable_key",
        )
        self.name = normalize_text(self.name, field_name="Tool function name")
        self.display_name = normalize_text(
            self.display_name,
            field_name="Tool function display_name",
        )
        self.description = self.description.strip()
        self.input_schema = normalize_json_mapping(self.input_schema)
        self.runtime_kind = coerce_str_enum(
            ToolFunctionRuntimeKind,
            self.runtime_kind,
            field_name="tool function runtime kind",
        )
        self.handler_ref = normalize_json_mapping(self.handler_ref)
        self.capability_ids = normalize_text_tuple(self.capability_ids)
        self.credential_requirements = normalize_json_mapping_tuple(
            self.credential_requirements,
        )
        self.access_requirement_sets = normalize_access_requirement_sets(
            self.access_requirement_sets,
            fallback_requirements=(),
        )
        self.runtime_requirements = normalize_json_mapping_tuple(
            self.runtime_requirements,
        )
        self.required_effect_ids = normalize_text_tuple(self.required_effect_ids)
        self.trust_policy = normalize_json_mapping(self.trust_policy)
        self.approval_policy = normalize_json_mapping(self.approval_policy)
        self.credential_binding_overrides = {
            normalize_text(str(key), field_name="Tool function credential override key"): (
                normalize_text(
                    str(value),
                    field_name="Tool function credential override value",
                )
            )
            for key, value in self.credential_binding_overrides.items()
        }
        if self.required_effect_overrides is not None:
            self.required_effect_overrides = normalize_text_tuple(
                self.required_effect_overrides,
            )
        self.metadata = normalize_json_mapping(self.metadata)
        self.schema_hash = self.schema_hash.strip()
        self.status = coerce_str_enum(
            ToolFunctionStatus,
            self.status,
            field_name="tool function status",
        )
        if self.revision < 1:
            raise ToolValidationError("Tool function revision must be at least 1.")


@dataclass(kw_only=True)
class ToolProviderBackend(AggregateRoot[str]):
    source_id: str
    display_name: str
    capability: ToolProviderCapability = ToolProviderCapability.CUSTOM
    credential_requirements: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    runtime_ref: dict[str, Any] = field(default_factory=dict)
    priority: int = 100
    enabled: bool = True
    status: ToolProviderBackendStatus = ToolProviderBackendStatus.ACTIVE
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    updated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc),
    )

    @property
    def backend_id(self) -> str:
        return self.id

    def __post_init__(self) -> None:
        self.id = normalize_text(self.id, field_name="Tool provider backend id")
        self.source_id = normalize_text(
            self.source_id,
            field_name="Tool provider backend source_id",
        )
        self.capability = coerce_str_enum(
            ToolProviderCapability,
            self.capability,
            field_name="tool provider capability",
        )
        self.display_name = normalize_text(
            self.display_name,
            field_name="Tool provider backend display_name",
        )
        self.credential_requirements = normalize_json_mapping_tuple(
            self.credential_requirements,
        )
        self.runtime_ref = normalize_json_mapping(self.runtime_ref)
        self.priority = int(self.priority)
        self.status = coerce_str_enum(
            ToolProviderBackendStatus,
            self.status,
            field_name="tool provider backend status",
        )


@dataclass(kw_only=True)
class Tool(AggregateRoot[str]):
    name: str
    description: str
    source_id: str | None = None
    kind: ToolKind = ToolKind.FUNCTION
    parameters: tuple[ToolParameter, ...] = field(default_factory=tuple)
    tags: tuple[str, ...] = field(default_factory=tuple)
    required_effect_ids: tuple[str, ...] = field(default_factory=tuple)
    access_requirements: tuple[str, ...] = field(default_factory=tuple)
    access_requirement_sets: tuple[tuple[str, ...], ...] = field(default_factory=tuple)
    runtime_requirement_sets: tuple[tuple[str, ...], ...] = field(default_factory=tuple)
    context_requirements: tuple[str, ...] = field(default_factory=tuple)
    capability_ids: tuple[str, ...] = field(default_factory=tuple)
    credential_requirements: tuple[AccessCredentialRequirementSet, ...] = (
        field(default_factory=tuple)
    )
    execution_policy: ToolExecutionPolicy = field(default_factory=ToolExecutionPolicy)
    execution_support: ToolExecutionSupport = field(
        default_factory=ToolExecutionSupport,
    )
    definition_origin: ToolDefinitionOrigin = ToolDefinitionOrigin.LOCAL_DISCOVERY
    runtime_key: str | None = None
    enabled: bool = True

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ToolValidationError("Tool name cannot be empty.")
        if not self.description.strip():
            raise ToolValidationError("Tool description cannot be empty.")
        self.source_id = normalize_optional_text(self.source_id)

        parameter_names = [parameter.name for parameter in self.parameters]
        if len(parameter_names) != len(set(parameter_names)):
            raise ToolValidationError("Tool parameter names must be unique.")

        self.tags = tuple(
            dict.fromkeys(
                tag.strip().lower()
                for tag in self.tags
                if tag is not None and tag.strip()
            ),
        )
        self.required_effect_ids = tuple(
            dict.fromkeys(
                effect_id.strip()
                for effect_id in self.required_effect_ids
                if effect_id is not None and effect_id.strip()
            ),
        )
        self.access_requirements = tuple(
            dict.fromkeys(
                requirement.strip()
                for requirement in self.access_requirements
                if requirement is not None and requirement.strip()
            ),
        )
        self.access_requirement_sets = normalize_access_requirement_sets(
            self.access_requirement_sets,
            fallback_requirements=self.access_requirements,
        )
        self.runtime_requirement_sets = normalize_access_requirement_sets(
            self.runtime_requirement_sets,
            fallback_requirements=(),
        )
        self.context_requirements = normalize_text_tuple(self.context_requirements)
        self.capability_ids = tuple(
            dict.fromkeys(
                capability_id.strip()
                for capability_id in self.capability_ids
                if capability_id is not None and capability_id.strip()
            ),
        )
        self.credential_requirements = tuple(self.credential_requirements)
        self.parameters = tuple(self.parameters)

    def supports(self, target: ToolExecutionTarget) -> bool:
        return self.execution_support.supports(target)

    def resolved_runtime_key(self) -> str:
        return self.runtime_key or self.id

    def enable(self) -> bool:
        if self.enabled:
            return False
        self.enabled = True
        self.record_event(
            Event(
                name="tool.enabled",
                payload={"tool_id": self.id, "tool_name": self.name},
            ),
        )
        return True

    def disable(self) -> bool:
        if not self.enabled:
            return False
        self.enabled = False
        self.record_event(
            Event(
                name="tool.disabled",
                payload={"tool_id": self.id, "tool_name": self.name},
            ),
        )
        return True
