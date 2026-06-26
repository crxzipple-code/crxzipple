from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any

from crxzipple.modules.tool.application.catalog_model_helpers import (
    hash_payload,
    input_schema_from_tool_spec,
    normalize_mapping,
    normalize_text_tuple,
    required_text,
    runtime_kind_from_tool_spec,
    stable_key_from_tool_spec,
    stable_payload,
    utc_now,
)
from crxzipple.modules.tool.application.catalog_model_types import (
    ToolFunctionRequirements,
    ToolFunctionRuntimeKind,
    ToolFunctionStatus,
    ensure_tool_function_requirements,
)
from crxzipple.modules.tool.application.specifications import ToolSpec
from crxzipple.modules.tool.domain.exceptions import ToolValidationError


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
            required_text(self.stable_key, field_name="stable_key"),
        )
        object.__setattr__(
            self,
            "source_id",
            required_text(self.source_id, field_name="source_id"),
        )
        object.__setattr__(
            self,
            "function_id",
            required_text(self.function_id, field_name="function_id"),
        )
        object.__setattr__(
            self,
            "name",
            required_text(self.name, field_name="name"),
        )
        object.__setattr__(
            self,
            "description",
            required_text(self.description, field_name="description"),
        )
        object.__setattr__(
            self,
            "input_schema",
            normalize_mapping(self.input_schema, field_name="input_schema"),
        )
        object.__setattr__(
            self,
            "runtime_kind",
            ToolFunctionRuntimeKind(str(self.runtime_kind)),
        )
        object.__setattr__(
            self,
            "handler_ref",
            required_text(self.handler_ref, field_name="handler_ref"),
        )
        ensure_tool_function_requirements(
            self.requirements,
            label="Tool function candidate",
        )
        object.__setattr__(self, "capabilities", normalize_text_tuple(self.capabilities))
        object.__setattr__(
            self,
            "metadata",
            normalize_mapping(self.metadata, field_name="metadata"),
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
            else runtime_kind_from_tool_spec(spec)
        )
        resolved_handler_ref = handler_ref or spec.runtime_key or spec.id
        resolved_stable_key = stable_key or stable_key_from_tool_spec(
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
            input_schema=input_schema_from_tool_spec(spec),
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
                    "supports_parallel": spec.execution_policy.supports_parallel,
                    "resource_scope": spec.execution_policy.resource_scope,
                    "serial_group_key": spec.execution_policy.serial_group_key,
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
            required_text(self.source_id, field_name="source_id"),
        )
        object.__setattr__(
            self,
            "backend_id",
            required_text(self.backend_id, field_name="backend_id"),
        )
        object.__setattr__(
            self,
            "capability",
            required_text(self.capability, field_name="capability"),
        )
        object.__setattr__(
            self,
            "display_name",
            required_text(self.display_name, field_name="display_name"),
        )
        object.__setattr__(
            self,
            "runtime_kind",
            ToolFunctionRuntimeKind(str(self.runtime_kind)),
        )
        object.__setattr__(
            self,
            "runtime_ref",
            required_text(self.runtime_ref, field_name="runtime_ref"),
        )
        ensure_tool_function_requirements(
            self.requirements,
            label="Tool provider backend",
        )
        object.__setattr__(
            self,
            "metadata",
            normalize_mapping(self.metadata, field_name="metadata"),
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
            required_text(self.function_id, field_name="function_id"),
        )
        object.__setattr__(
            self,
            "source_id",
            required_text(self.source_id, field_name="source_id"),
        )
        object.__setattr__(
            self,
            "stable_key",
            required_text(self.stable_key, field_name="stable_key"),
        )
        object.__setattr__(
            self,
            "name",
            required_text(self.name, field_name="name"),
        )
        object.__setattr__(
            self,
            "description",
            required_text(self.description, field_name="description"),
        )
        object.__setattr__(
            self,
            "input_schema",
            normalize_mapping(self.input_schema, field_name="input_schema"),
        )
        object.__setattr__(
            self,
            "runtime_kind",
            ToolFunctionRuntimeKind(str(self.runtime_kind)),
        )
        object.__setattr__(
            self,
            "handler_ref",
            required_text(self.handler_ref, field_name="handler_ref"),
        )
        ensure_tool_function_requirements(self.requirements, label="Tool function")
        object.__setattr__(self, "capabilities", normalize_text_tuple(self.capabilities))
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
            normalize_mapping(self.trust_policy, field_name="trust_policy"),
        )
        object.__setattr__(
            self,
            "approval_policy",
            normalize_mapping(self.approval_policy, field_name="approval_policy"),
        )
        object.__setattr__(
            self,
            "credential_binding_overrides",
            {
                required_text(str(key), field_name="credential_binding_override.key"): (
                    required_text(str(value), field_name="credential_binding_override.value")
                )
                for key, value in self.credential_binding_overrides.items()
            },
        )
        if self.required_effect_overrides is not None:
            object.__setattr__(
                self,
                "required_effect_overrides",
                normalize_text_tuple(self.required_effect_overrides),
            )
        object.__setattr__(
            self,
            "metadata",
            normalize_mapping(self.metadata, field_name="metadata"),
        )

    @classmethod
    def from_candidate(
        cls,
        candidate: ToolFunctionCandidate,
        *,
        observed_at: datetime | None = None,
    ) -> "ToolFunctionCatalogRecord":
        now = observed_at or utc_now()
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
            if stable_payload(existing) != stable_payload(incoming):
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
        now = observed_at or utc_now()
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
        now = observed_at or utc_now()
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
        now = observed_at or utc_now()
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
    return hash_payload(
        {
            "schema_version": 1,
            "input_schema": input_schema,
            "runtime_kind": str(runtime_kind),
            "handler_ref": handler_ref,
            "requirements": requirements,
            "capabilities": capabilities,
        },
    )
