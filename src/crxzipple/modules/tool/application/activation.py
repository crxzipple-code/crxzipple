from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

from crxzipple.core.config import OpenApiProviderSettings
from crxzipple.modules.tool.domain import Tool
from crxzipple.modules.tool.domain.exceptions import ToolValidationError
from crxzipple.shared.access import AccessCredentialRequirementSet


ToolDependencyKind = Literal[
    "service_dependency",
    "external_requirement",
    "optional_dependency",
]
ToolPackageKind = Literal["local_package", "openapi"]
ToolRuntimeKind = Literal["remote", "sandbox"]


@dataclass(frozen=True, slots=True)
class ToolDependencyRequirement:
    id: str
    kind: ToolDependencyKind
    description: str = ""
    required: bool = True
    metadata: dict[str, object] | None = None


@dataclass(frozen=True, slots=True)
class ToolDependencyBinding:
    dependency_id: str
    value: Any
    capability_ids: tuple[str, ...] = ()
    description: str = ""

    def __post_init__(self) -> None:
        dependency_id = self.dependency_id.strip()
        if not dependency_id:
            raise ToolValidationError("Tool dependency binding id cannot be empty.")
        if self.value is None:
            raise ToolValidationError(
                f"Tool dependency binding '{dependency_id}' cannot bind None.",
            )
        object.__setattr__(self, "dependency_id", dependency_id)
        object.__setattr__(
            self,
            "capability_ids",
            tuple(
                dict.fromkeys(
                    capability_id.strip()
                    for capability_id in self.capability_ids
                    if capability_id.strip()
                ),
            ),
        )
        object.__setattr__(self, "description", self.description.strip())


@dataclass(frozen=True, slots=True)
class ToolHandlerPlan:
    namespace: str
    tool: Tool
    provider_name: str
    entrypoint: str
    capability_ids: tuple[str, ...] = ()
    dependencies: tuple[ToolDependencyRequirement, ...] = ()


@dataclass(frozen=True, slots=True)
class ToolRuntimePlan:
    namespace: str
    runtime_key: str
    entrypoint: str
    runtime_kind: ToolRuntimeKind
    capability_ids: tuple[str, ...] = ()
    dependencies: tuple[ToolDependencyRequirement, ...] = ()


@dataclass(frozen=True, slots=True)
class ToolOpenApiPlan:
    namespace: str
    provider: OpenApiProviderSettings
    capability_ids: tuple[str, ...] = ()
    dependencies: tuple[ToolDependencyRequirement, ...] = ()


@dataclass(frozen=True, slots=True)
class ToolProviderBackendPlan:
    namespace: str
    backend_id: str
    capability: str
    display_name: str
    runtime_kind: str
    runtime_ref: str
    credential_requirements: tuple[AccessCredentialRequirementSet, ...] = ()
    priority: int = 100
    enabled: bool = True
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ToolPackagePlan:
    namespace: str
    root_path: str
    manifest_path: str
    package_kind: ToolPackageKind
    capability_ids: tuple[str, ...] = ()
    runtime_request: Mapping[str, Any] = field(default_factory=dict)
    local_handlers: tuple[ToolHandlerPlan, ...] = ()
    remote_runtimes: tuple[ToolRuntimePlan, ...] = ()
    sandbox_runtimes: tuple[ToolRuntimePlan, ...] = ()
    openapi: ToolOpenApiPlan | None = None
    provider_backends: tuple[ToolProviderBackendPlan, ...] = ()


@dataclass(frozen=True, slots=True)
class ToolHandlerRegistration:
    namespace: str
    tool_id: str
    entrypoint: str
    handler: Callable[..., Any]
    provider_name: str | None = None
    runtime_key: str | None = None
    runtime_kind: ToolRuntimeKind | None = None
    capability_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ToolPackageApplyContext:
    local_runtime_registry: Any | None = None
    remote_tool_registry: Any | None = None
    sandbox_tool_registry: Any | None = None
    tool_discovery_registry: Any | None = None
    local_function_refs_by_namespace: Mapping[str, tuple[str, ...]] | None = None
    settings: Any | None = None
    dependency_bindings: Mapping[str, ToolDependencyBinding] = field(
        default_factory=dict,
    )
    config: Mapping[str, Any] = field(default_factory=dict)
    capability_ids: tuple[str, ...] | None = None
    external_requirements: tuple[str, ...] | None = None

    def validate_capabilities(
        self,
        capability_ids: tuple[str, ...],
        *,
        owner: str,
    ) -> None:
        if self.capability_ids is None:
            return
        available = set(self.capability_ids)
        missing = tuple(
            capability_id
            for capability_id in capability_ids
            if capability_id not in available
        )
        if missing:
            missing_list = ", ".join(repr(capability_id) for capability_id in missing)
            raise ToolValidationError(
                f"{owner} requires unavailable tool capability: {missing_list}.",
            )

    def dependency(
        self,
        dependency_id: str,
        *,
        declared_capability_ids: tuple[str, ...] = (),
        default: Any = None,
    ) -> Any:
        normalized_id = dependency_id.strip()
        binding = self.dependency_bindings.get(normalized_id)
        if binding is None:
            return default
        if not isinstance(binding, ToolDependencyBinding):
            raise ToolValidationError(
                f"Tool dependency '{normalized_id}' must be provided as "
                "ToolDependencyBinding.",
            )
        if binding.dependency_id != normalized_id:
            raise ToolValidationError(
                f"Tool dependency binding key '{normalized_id}' does not match "
                f"binding id '{binding.dependency_id}'.",
            )
        if binding.capability_ids and declared_capability_ids:
            declared = set(declared_capability_ids)
            if declared.isdisjoint(binding.capability_ids):
                binding_caps = ", ".join(binding.capability_ids)
                declared_caps = ", ".join(declared_capability_ids)
                raise ToolValidationError(
                    f"Tool dependency '{normalized_id}' is bound to capabilities "
                    f"[{binding_caps}] but the tool only declared [{declared_caps}].",
                )
        return binding.value

    def require_dependency(
        self,
        dependency_id: str,
        *,
        declared_capability_ids: tuple[str, ...] = (),
    ) -> Any:
        value = self.dependency(
            dependency_id,
            declared_capability_ids=declared_capability_ids,
        )
        if value is None:
            raise LookupError(
                f"Tool package apply requires dependency binding '{dependency_id}'.",
            )
        return value

    def has_external_requirement(self, requirement_id: str) -> bool:
        if self.external_requirements is None:
            return True
        return requirement_id.strip() in set(self.external_requirements)

    def local_function_refs_for_namespace(
        self,
        namespace: str,
    ) -> tuple[str, ...] | None:
        if self.local_function_refs_by_namespace is None:
            return None
        return tuple(
            str(value).strip()
            for value in self.local_function_refs_by_namespace.get(
                namespace.strip(),
                (),
            )
            if str(value).strip()
        )

    def setting(self, key: str, default: Any = None) -> Any:
        value = self.config.get(key)
        if value is not None:
            return value
        if self.settings is not None:
            return getattr(self.settings, key, default)
        return default


@dataclass(frozen=True, slots=True)
class ResolvedToolHandlerActivation:
    plan: ToolHandlerPlan
    registration: ToolHandlerRegistration
    factory_deps: ToolHandlerFactoryDeps


@dataclass(frozen=True, slots=True)
class ResolvedToolRuntimeActivation:
    plan: ToolRuntimePlan
    registration: ToolHandlerRegistration


@dataclass(frozen=True, slots=True)
class ResolvedToolPackageActivation:
    namespace: str
    package_kind: ToolPackageKind
    local_handlers: tuple[ResolvedToolHandlerActivation, ...] = ()
    remote_runtimes: tuple[ResolvedToolRuntimeActivation, ...] = ()
    sandbox_runtimes: tuple[ResolvedToolRuntimeActivation, ...] = ()
    openapi: ToolOpenApiPlan | None = None


@dataclass(frozen=True, slots=True)
class ToolPackageApplyResult:
    activations: tuple[ResolvedToolPackageActivation, ...] = ()

    @property
    def namespaces(self) -> tuple[str, ...]:
        return tuple(activation.namespace for activation in self.activations)


@dataclass(frozen=True, slots=True)
class ToolHandlerFactoryDeps:
    namespace: str
    tool_id: str
    entrypoint: str
    services: Mapping[str, Any] = field(default_factory=dict)
    config: Mapping[str, Any] = field(default_factory=dict)
    capability_ids: tuple[str, ...] = ()
    requirements: tuple[ToolDependencyRequirement, ...] = ()
