from __future__ import annotations

from dataclasses import MISSING, fields, is_dataclass
from enum import Enum
import importlib
from inspect import Parameter, signature
from pathlib import Path
from types import UnionType
from typing import Any, Union, get_args, get_origin, get_type_hints

import yaml

from crxzipple.core.config import (
    PROJECT_ROOT,
    OpenApiCredentialBinding,
    OpenApiProviderSettings,
)
from crxzipple.modules.tool.application.capabilities import (
    DEFAULT_TOOL_CAPABILITY_CATALOG,
)
from crxzipple.modules.tool.application.activation import (
    ResolvedToolHandlerActivation,
    ResolvedToolPackageActivation,
    ResolvedToolRuntimeActivation,
    ToolDependencyBinding,  # noqa: F401 - re-exported by tool.infrastructure
    ToolDependencyKind,
    ToolDependencyRequirement,
    ToolHandlerFactoryDeps,
    ToolHandlerPlan,
    ToolHandlerRegistration,
    ToolOpenApiPlan,
    ToolPackageApplyContext,
    ToolPackageApplyResult,
    ToolPackagePlan,
    ToolProviderBackendPlan,
    ToolRuntimeKind,
    ToolRuntimePlan,
)
from crxzipple.modules.tool.domain import (
    Tool,
    ToolEnvironment,
    ToolExecutionPolicy,
    ToolExecutionSupport,
    ToolExecutionStrategy,
    ToolKind,
    ToolMode,
    ToolParameter,
    ToolDefinitionOrigin,
)
from crxzipple.modules.tool.domain.exceptions import ToolValidationError
from crxzipple.modules.tool.infrastructure.discovery.local_runtime_registry import (
    LocalToolRuntimeRegistry,
    LocalToolHandler,
)
from crxzipple.modules.tool.infrastructure.discovery.openapi import (
    OpenApiDiscoveryProvider,
)
from crxzipple.modules.tool.infrastructure.discovery.providers import (
    ToolDiscoveryRegistry,
)
from crxzipple.modules.tool.infrastructure.runtimes.openapi_remote import (
    register_openapi_remote_handlers,
)
from crxzipple.modules.tool.infrastructure.runtimes.registry import (
    AsyncToolHandler,
    ToolRuntimeRegistry,
)
from crxzipple.shared.access import (
    AccessConsumerRef,
    AccessCredentialKind,
    AccessCredentialRequirementDeclaration,
    AccessCredentialRequirementSet,
    AccessCredentialSlotRef,
    AccessCredentialTransport,
    AccessSetupFlowHint,
    AccessSetupFlowKind,
)


_forbidden_openapi_credential_source_prefixes = (
    "env:",  # forbidden direct source
    "file:",  # forbidden direct source
    "codex_auth_json",  # forbidden direct source
    "codex-cli",  # forbidden direct source
    "auth_ref",  # forbidden legacy credential field
)
DEFAULT_TOOL_ROOT = PROJECT_ROOT / "tools"


LocalToolBinding = ToolHandlerPlan


RuntimeToolBinding = ToolRuntimePlan


class ToolNamespaceDefinition(ToolPackagePlan):
    @property
    def name(self) -> str:
        return self.namespace

    @property
    def kind(self) -> str:
        return self.package_kind

    @property
    def local_bindings(self) -> tuple[ToolHandlerPlan, ...]:
        return self.local_handlers

    @property
    def remote_bindings(self) -> tuple[ToolRuntimePlan, ...]:
        return self.remote_runtimes

    @property
    def sandbox_bindings(self) -> tuple[ToolRuntimePlan, ...]:
        return self.sandbox_runtimes

    @property
    def openapi_provider(self) -> OpenApiProviderSettings | None:
        return self.openapi.provider if self.openapi is not None else None


def discover_tool_namespaces(
    root_dir: str | Path = DEFAULT_TOOL_ROOT,
) -> tuple[ToolNamespaceDefinition, ...]:
    return discover_tool_package_plans(root_dir=root_dir)


def discover_tool_package_plans(
    root_dir: str | Path = DEFAULT_TOOL_ROOT,
) -> tuple[ToolNamespaceDefinition, ...]:
    root = Path(root_dir).expanduser().resolve()
    if not root.exists():
        return ()

    plans: list[ToolNamespaceDefinition] = []
    for manifest_path in sorted(root.glob("*/tool.yaml")):
        plans.append(load_tool_package_plan(manifest_path))
    return tuple(plans)


def load_tool_package_plan(manifest_path: str | Path) -> ToolNamespaceDefinition:
    return _load_namespace(Path(manifest_path).expanduser().resolve())


def apply_tool_package_plans(
    context: ToolPackageApplyContext,
    namespaces: tuple[ToolPackagePlan, ...],
    *,
    include_openapi: bool = True,
    include_local: bool = True,
    include_runtimes: bool = True,
) -> ToolPackageApplyResult:
    resolved = resolve_tool_package_activations(
        context,
        namespaces,
        include_openapi=include_openapi,
        include_local=include_local,
        include_runtimes=include_runtimes,
    )
    for activation in resolved:
        if activation.local_handlers:
            local_runtime_registry = context.local_runtime_registry
            assert isinstance(local_runtime_registry, LocalToolRuntimeRegistry)
            for item in activation.local_handlers:
                local_runtime_registry.register(
                    item.plan.tool,
                    item.registration.handler,
                    provider_name=item.plan.provider_name,
                )
        if activation.remote_runtimes:
            remote_tool_registry = context.remote_tool_registry
            assert isinstance(remote_tool_registry, ToolRuntimeRegistry)
            for item in activation.remote_runtimes:
                remote_tool_registry.register(
                    item.plan.runtime_key,
                    item.registration.handler,
                )
        if activation.sandbox_runtimes:
            sandbox_tool_registry = context.sandbox_tool_registry
            assert isinstance(sandbox_tool_registry, ToolRuntimeRegistry)
            for item in activation.sandbox_runtimes:
                sandbox_tool_registry.register(
                    item.plan.runtime_key,
                    item.registration.handler,
                )
        if activation.openapi is not None:
            tool_discovery_registry = context.tool_discovery_registry
            remote_tool_registry = context.remote_tool_registry
            assert isinstance(tool_discovery_registry, ToolDiscoveryRegistry)
            assert isinstance(remote_tool_registry, ToolRuntimeRegistry)
            openapi_provider = activation.openapi.provider
            if openapi_provider.credential_bindings:
                try:
                    credential_provider = context.require_dependency(
                        "credential_provider",
                        declared_capability_ids=activation.openapi.capability_ids,
                    )
                except LookupError as exc:
                    raise ToolValidationError(
                        f"OpenAPI tool namespace '{activation.namespace}' requires "
                        "credential dependency binding 'credential_provider'.",
                    ) from exc
            else:
                credential_provider = (
                    context.dependency("credential_provider")
                    or _UnavailableCredentialProvider()
                )
            provider = OpenApiDiscoveryProvider(
                openapi_provider,
                capability_ids=activation.openapi.capability_ids,
            )
            tool_discovery_registry.register(provider)
            register_openapi_remote_handlers(
                remote_tool_registry,
                provider.operations(),
                credential_provider=credential_provider,
                max_concurrency=(
                    openapi_provider.max_concurrency
                    or context.setting("tool_remote_default_max_concurrency")
                ),
            )
    return ToolPackageApplyResult(activations=resolved)


class _UnavailableCredentialProvider:
    def resolve_credential(self, *_args, **_kwargs) -> str:
        raise ToolValidationError(
            "OpenAPI operation requires credentials, but no credential provider "
            "binding was available during tool package activation.",
        )


def resolve_tool_package_activations(
    context: ToolPackageApplyContext,
    namespaces: tuple[ToolPackagePlan, ...],
    *,
    include_openapi: bool = True,
    include_local: bool = True,
    include_runtimes: bool = True,
) -> tuple[ResolvedToolPackageActivation, ...]:
    _validate_unique_package_plans(
        namespaces,
        include_local=include_local,
        include_runtimes=include_runtimes,
    )
    activations: list[ResolvedToolPackageActivation] = []
    for namespace in namespaces:
        namespace_name = _package_namespace(namespace)
        package_kind = _package_kind(namespace)
        context.validate_capabilities(
            getattr(namespace, "capability_ids", ()),
            owner=f"Tool namespace '{namespace_name}'",
        )
        if package_kind == "local_package":
            local_handlers: tuple[ResolvedToolHandlerActivation, ...] = ()
            remote_runtimes: tuple[ResolvedToolRuntimeActivation, ...] = ()
            sandbox_runtimes: tuple[ResolvedToolRuntimeActivation, ...] = ()
            if include_local and isinstance(
                context.local_runtime_registry,
                LocalToolRuntimeRegistry,
            ):
                active_handler_refs = context.local_function_refs_for_namespace(
                    namespace_name,
                )
                local_handlers = tuple(
                    item
                    for item in (
                        _resolve_local_handler_activation(binding, context)
                        for binding in _local_handler_plans(namespace)
                        if _local_handler_enabled_by_catalog(
                            binding,
                            active_handler_refs,
                        )
                    )
                    if item is not None
                )
            if include_runtimes and isinstance(
                context.remote_tool_registry,
                ToolRuntimeRegistry,
            ):
                remote_runtimes = tuple(
                    item
                    for item in (
                        _resolve_runtime_activation(binding, context)
                        for binding in _remote_runtime_plans(namespace)
                    )
                    if item is not None
                )
            if include_runtimes and isinstance(
                context.sandbox_tool_registry,
                ToolRuntimeRegistry,
            ):
                sandbox_runtimes = tuple(
                    item
                    for item in (
                        _resolve_runtime_activation(binding, context)
                        for binding in _sandbox_runtime_plans(namespace)
                    )
                    if item is not None
                )
            activations.append(
                ResolvedToolPackageActivation(
                    namespace=namespace_name,
                    package_kind="local_package",
                    local_handlers=local_handlers,
                    remote_runtimes=remote_runtimes,
                    sandbox_runtimes=sandbox_runtimes,
                ),
            )
        elif (
            package_kind == "openapi"
            and include_openapi
            and _openapi_provider(namespace) is not None
            and isinstance(context.tool_discovery_registry, ToolDiscoveryRegistry)
            and isinstance(context.remote_tool_registry, ToolRuntimeRegistry)
        ):
            openapi_plan = getattr(namespace, "openapi", None)
            if openapi_plan is None:
                openapi_provider = _openapi_provider(namespace)
                assert openapi_provider is not None
                openapi_plan = ToolOpenApiPlan(
                    namespace=namespace_name,
                    provider=openapi_provider,
                )
            context.validate_capabilities(
                openapi_plan.capability_ids,
                owner=f"OpenAPI tool namespace '{namespace_name}'",
            )
            activations.append(
                ResolvedToolPackageActivation(
                    namespace=namespace_name,
                    package_kind="openapi",
                    openapi=openapi_plan,
                ),
            )
        else:
            activations.append(
                ResolvedToolPackageActivation(
                    namespace=namespace_name,
                    package_kind=package_kind,
                ),
            )
    return tuple(activations)


def _validate_unique_package_plans(
    namespaces: tuple[ToolPackagePlan, ...],
    *,
    include_local: bool,
    include_runtimes: bool,
) -> None:
    namespace_names: set[str] = set()
    tool_ids: set[str] = set()
    runtime_keys: set[str] = set()
    for namespace in namespaces:
        DEFAULT_TOOL_CAPABILITY_CATALOG.validate_capability_ids(
            getattr(namespace, "capability_ids", ()),
        )
        namespace_name = _package_namespace(namespace)
        if namespace_name in namespace_names:
            raise ToolValidationError(
                f"Duplicate tool namespace '{namespace_name}' in package apply plan.",
            )
        namespace_names.add(namespace_name)
        if include_local:
            for handler in _local_handler_plans(namespace):
                DEFAULT_TOOL_CAPABILITY_CATALOG.validate_capability_ids(
                    handler.capability_ids,
                )
                tool_id = handler.tool.id
                if tool_id in tool_ids:
                    raise ToolValidationError(
                        f"Duplicate tool id '{tool_id}' in package apply plan.",
                    )
                tool_ids.add(tool_id)
        if include_runtimes:
            for runtime in (
                *_remote_runtime_plans(namespace),
                *_sandbox_runtime_plans(namespace),
            ):
                DEFAULT_TOOL_CAPABILITY_CATALOG.validate_capability_ids(
                    runtime.capability_ids,
                )
                runtime_key = runtime.runtime_key
                if runtime_key in runtime_keys:
                    raise ToolValidationError(
                        f"Duplicate tool runtime '{runtime_key}' in package apply plan.",
                    )
                runtime_keys.add(runtime_key)


def _package_namespace(namespace: ToolPackagePlan) -> str:
    return getattr(namespace, "namespace", getattr(namespace, "name", ""))


def _package_kind(namespace: ToolPackagePlan) -> str:
    return getattr(namespace, "package_kind", getattr(namespace, "kind", ""))


def _local_handler_plans(namespace: ToolPackagePlan) -> tuple[ToolHandlerPlan, ...]:
    return getattr(namespace, "local_handlers", getattr(namespace, "local_bindings", ()))


def _local_handler_enabled_by_catalog(
    binding: ToolHandlerPlan,
    active_handler_refs: tuple[str, ...] | None,
) -> bool:
    if active_handler_refs is None:
        return True
    return binding.tool.resolved_runtime_key() in set(active_handler_refs)


def _remote_runtime_plans(namespace: ToolPackagePlan) -> tuple[ToolRuntimePlan, ...]:
    return getattr(namespace, "remote_runtimes", getattr(namespace, "remote_bindings", ()))


def _sandbox_runtime_plans(namespace: ToolPackagePlan) -> tuple[ToolRuntimePlan, ...]:
    return getattr(
        namespace,
        "sandbox_runtimes",
        getattr(namespace, "sandbox_bindings", ()),
    )


def _openapi_provider(namespace: ToolPackagePlan) -> OpenApiProviderSettings | None:
    openapi = getattr(namespace, "openapi", None)
    if openapi is not None:
        return openapi.provider
    return getattr(namespace, "openapi_provider", None)


def _registration_for_local_handler(
    binding: ToolHandlerPlan,
    handler: LocalToolHandler,
) -> ToolHandlerRegistration:
    return ToolHandlerRegistration(
        namespace=binding.namespace,
        tool_id=binding.tool.id,
        entrypoint=binding.entrypoint,
        handler=handler,
        provider_name=binding.provider_name,
        capability_ids=binding.capability_ids,
    )


def _load_namespace(manifest_path: Path) -> ToolNamespaceDefinition:
    payload = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' must decode to a mapping.",
        )

    namespace_name = str(payload.get("namespace", "")).strip()
    if not namespace_name:
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' must define namespace.",
        )
    if manifest_path.parent.name != namespace_name:
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' namespace '{namespace_name}' "
            f"must match directory name '{manifest_path.parent.name}'.",
        )

    kind = str(payload.get("kind", "")).strip()
    package_dependencies = _load_dependency_requirements(
        payload.get("dependencies", []),
        manifest_path,
    )
    package_capability_ids = _load_capability_ids(payload, manifest_path)
    if kind == "local_package":
        return ToolNamespaceDefinition(
            namespace=namespace_name,
            root_path=str(manifest_path.parent),
            manifest_path=str(manifest_path),
            package_kind=kind,
            capability_ids=package_capability_ids,
            prompt=_load_prompt_metadata(payload.get("prompt"), manifest_path),
            local_handlers=_load_local_bindings(
                payload,
                manifest_path,
                namespace=namespace_name,
                package_dependencies=package_dependencies,
                package_capability_ids=package_capability_ids,
            ),
            remote_runtimes=_load_runtime_bindings(
                payload.get("remote_runtimes", []),
                manifest_path,
                namespace=namespace_name,
                runtime_kind="remote",
                package_dependencies=package_dependencies,
                package_capability_ids=package_capability_ids,
            ),
            sandbox_runtimes=_load_runtime_bindings(
                payload.get("sandbox_runtimes", []),
                manifest_path,
                namespace=namespace_name,
                runtime_kind="sandbox",
                package_dependencies=package_dependencies,
                package_capability_ids=package_capability_ids,
            ),
            provider_backends=_load_provider_backend_plans(
                payload.get("provider_backends", []),
                manifest_path,
                namespace=namespace_name,
            ),
        )
    if kind == "openapi":
        return ToolNamespaceDefinition(
            namespace=namespace_name,
            root_path=str(manifest_path.parent),
            manifest_path=str(manifest_path),
            package_kind=kind,
            capability_ids=package_capability_ids,
            prompt=_load_prompt_metadata(payload.get("prompt"), manifest_path),
            openapi=ToolOpenApiPlan(
                namespace=namespace_name,
                provider=_load_openapi_provider(payload, manifest_path),
                capability_ids=package_capability_ids,
                dependencies=package_dependencies,
            ),
            provider_backends=_load_provider_backend_plans(
                payload.get("provider_backends", []),
                manifest_path,
                namespace=namespace_name,
            ),
        )

    raise ToolValidationError(
        f"Tool namespace manifest '{manifest_path}' declares unsupported kind '{kind}'.",
    )


def _load_local_bindings(
    payload: dict[str, Any],
    manifest_path: Path,
    *,
    namespace: str,
    package_dependencies: tuple[ToolDependencyRequirement, ...],
    package_capability_ids: tuple[str, ...],
) -> tuple[LocalToolBinding, ...]:
    raw_tools = payload.get("local_tools", [])
    if not isinstance(raw_tools, list):
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' field 'local_tools' must be a list.",
        )
    bindings: list[LocalToolBinding] = []
    for item in raw_tools:
        if not isinstance(item, dict):
            raise ToolValidationError(
                f"Tool namespace manifest '{manifest_path}' local_tools entries must be mappings.",
            )
        dependencies = (
            package_dependencies
            + _load_dependency_requirements(
                item.get("dependencies", []),
                manifest_path,
            )
        )
        capability_ids = _combined_capability_ids(
            package_capability_ids,
            _load_capability_ids(item, manifest_path),
        )
        bindings.append(
            LocalToolBinding(
                namespace=namespace,
                tool=_build_tool(
                    item,
                    manifest_path,
                    dependency_requirements=dependencies,
                    capability_ids=capability_ids,
                ),
                provider_name=str(item.get("provider_name", "local_system")).strip()
                or "local_system",
                entrypoint=_required_string(item, "entrypoint", manifest_path),
                capability_ids=capability_ids,
                dependencies=dependencies,
            ),
        )
    return tuple(bindings)


def _load_runtime_bindings(
    raw_bindings: object,
    manifest_path: Path,
    *,
    namespace: str,
    runtime_kind: ToolRuntimeKind,
    package_dependencies: tuple[ToolDependencyRequirement, ...],
    package_capability_ids: tuple[str, ...],
) -> tuple[RuntimeToolBinding, ...]:
    if not isinstance(raw_bindings, list):
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' runtime binding lists must be arrays.",
        )
    bindings: list[RuntimeToolBinding] = []
    for item in raw_bindings:
        if not isinstance(item, dict):
            raise ToolValidationError(
                f"Tool namespace manifest '{manifest_path}' runtime entries must be mappings.",
            )
        bindings.append(
            RuntimeToolBinding(
                namespace=namespace,
                runtime_key=_required_string(item, "runtime_key", manifest_path),
                entrypoint=_required_string(item, "entrypoint", manifest_path),
                runtime_kind=runtime_kind,
                capability_ids=_combined_capability_ids(
                    package_capability_ids,
                    _load_capability_ids(item, manifest_path),
                ),
                dependencies=(
                    package_dependencies
                    + _load_dependency_requirements(
                        item.get("dependencies", []),
                        manifest_path,
                    )
                ),
            ),
        )
    return tuple(bindings)


def _load_provider_backend_plans(
    raw_backends: object,
    manifest_path: Path,
    *,
    namespace: str,
) -> tuple[ToolProviderBackendPlan, ...]:
    if raw_backends in (None, []):
        return ()
    if not isinstance(raw_backends, list):
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' field 'provider_backends' must be a list.",
        )
    backends: list[ToolProviderBackendPlan] = []
    for item in raw_backends:
        if not isinstance(item, dict):
            raise ToolValidationError(
                f"Tool namespace manifest '{manifest_path}' provider_backends entries must be mappings.",
            )
        backend_id = _required_string(item, "id", manifest_path)
        runtime_ref = _required_string(item, "runtime_ref", manifest_path)
        runtime_kind = str(item.get("runtime_kind", "local")).strip() or "local"
        if runtime_kind not in {
            "local",
            "remote",
            "sandbox",
            "mcp",
            "openapi",
            "cli",
            "provider_backend",
        }:
            raise ToolValidationError(
                f"Tool namespace manifest '{manifest_path}' provider backend runtime_kind "
                f"'{runtime_kind}' is unsupported.",
            )
        backends.append(
            ToolProviderBackendPlan(
                namespace=namespace,
                backend_id=backend_id,
                capability=str(item.get("capability", "custom")).strip()
                or "custom",
                display_name=(
                    str(item.get("display_name") or item.get("name") or backend_id)
                    .strip()
                    or backend_id
                ),
                runtime_kind=runtime_kind,
                runtime_ref=runtime_ref,
                credential_requirements=_parse_credential_requirement_sets(
                    item.get("credential_requirements", []),
                    manifest_path,
                    tool_id=backend_id,
                    runtime_key=runtime_ref,
                ),
                priority=max(int(item.get("priority", 100)), 0),
                enabled=bool(item.get("enabled", True)),
                metadata=_mapping_payload(item.get("metadata")),
            ),
        )
    return tuple(backends)


def _load_prompt_metadata(
    raw_prompt: object,
    manifest_path: Path,
) -> dict[str, object]:
    if raw_prompt in (None, {}):
        return {}
    if not isinstance(raw_prompt, dict):
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' field 'prompt' must be a mapping.",
        )
    prompt: dict[str, object] = _stable_payload(raw_prompt)
    for key in ("title", "summary"):
        raw_value = raw_prompt.get(key)
        if raw_value is None:
            prompt.pop(key, None)
            continue
        value = str(raw_value).strip()
        if value:
            prompt[key] = value
        else:
            prompt.pop(key, None)
    raw_groups = raw_prompt.get("groups")
    if raw_groups is not None:
        if not isinstance(raw_groups, dict):
            raise ToolValidationError(
                f"Tool namespace manifest '{manifest_path}' field 'prompt.groups' must be a mapping.",
            )
        groups: dict[str, object] = {}
        for raw_group_key, raw_group in raw_groups.items():
            group_key = str(raw_group_key).strip()
            if not group_key:
                raise ToolValidationError(
                    f"Tool namespace manifest '{manifest_path}' prompt group keys cannot be empty.",
                )
            if not isinstance(raw_group, dict):
                raise ToolValidationError(
                    f"Tool namespace manifest '{manifest_path}' prompt group '{group_key}' must be a mapping.",
                )
            group_payload: dict[str, object] = _stable_payload(raw_group)
            for key in ("title", "summary"):
                raw_value = raw_group.get(key)
                if raw_value is None:
                    group_payload.pop(key, None)
                    continue
                value = str(raw_value).strip()
                if value:
                    group_payload[key] = value
                else:
                    group_payload.pop(key, None)
            function_ids = _parse_string_list(
                raw_group.get("function_ids", []),
                "prompt.groups.function_ids",
                manifest_path,
            )
            raw_order = raw_group.get("order")
            if raw_order is not None:
                try:
                    group_payload["order"] = int(raw_order)
                except (TypeError, ValueError) as exc:
                    raise ToolValidationError(
                        f"Tool namespace manifest '{manifest_path}' prompt group '{group_key}' order must be an integer.",
                    ) from exc
            if function_ids:
                group_payload["function_ids"] = function_ids
            else:
                group_payload.pop("function_ids", None)
            groups[group_key] = group_payload
        if groups:
            prompt["groups"] = groups
        else:
            prompt.pop("groups", None)
    return prompt


def _load_dependency_requirements(
    raw_requirements: object,
    manifest_path: Path,
) -> tuple[ToolDependencyRequirement, ...]:
    if raw_requirements in (None, []):
        return ()
    if not isinstance(raw_requirements, list):
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' field 'dependencies' must be a list.",
        )
    requirements: list[ToolDependencyRequirement] = []
    for item in raw_requirements:
        if isinstance(item, str):
            dependency_id = item.strip()
            if not dependency_id:
                continue
            requirements.append(
                ToolDependencyRequirement(
                    id=dependency_id,
                    kind="service_dependency",
                ),
            )
            continue
        if not isinstance(item, dict):
            raise ToolValidationError(
                f"Tool namespace manifest '{manifest_path}' dependency entries must be strings or mappings.",
            )
        dependency_id = _required_string(item, "id", manifest_path)
        dependency_kind = _parse_dependency_kind(
            item.get("kind", "service_dependency"),
            manifest_path=manifest_path,
        )
        requirements.append(
            ToolDependencyRequirement(
                id=dependency_id,
                kind=dependency_kind,
                description=str(item.get("description", "")).strip(),
                required=bool(
                    item.get(
                        "required",
                        dependency_kind != "optional_dependency",
                    ),
                ),
                metadata=_mapping_payload(item.get("metadata")),
            ),
        )
    return tuple(requirements)


def _load_capability_ids(
    payload: dict[str, Any],
    manifest_path: Path,
) -> tuple[str, ...]:
    raw_capabilities = payload.get("capabilities")
    if raw_capabilities is None:
        raw_capabilities = payload.get("capability_ids", [])
    if raw_capabilities in (None, []):
        return ()
    capability_ids = _parse_string_list(
        raw_capabilities,
        "capabilities",
        manifest_path,
    )
    return DEFAULT_TOOL_CAPABILITY_CATALOG.validate_capability_ids(capability_ids)


def _combined_capability_ids(
    *capability_groups: tuple[str, ...],
) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            capability_id
            for capability_group in capability_groups
            for capability_id in capability_group
        ),
    )


def _parse_dependency_kind(
    raw_value: object,
    *,
    manifest_path: Path,
) -> ToolDependencyKind:
    normalized = str(raw_value or "service_dependency").strip()
    if normalized in (
        "service_dependency",
        "external_requirement",
        "optional_dependency",
    ):
        return normalized
    raise ToolValidationError(
        f"Tool namespace manifest '{manifest_path}' dependency kind '{normalized}' is unsupported.",
    )


def _build_tool(
    payload: dict[str, Any],
    manifest_path: Path,
    *,
    dependency_requirements: tuple[ToolDependencyRequirement, ...] = (),
    capability_ids: tuple[str, ...] = (),
) -> Tool:
    tool_id = _required_string(payload, "id", manifest_path)
    runtime_key = (
        str(payload["runtime_key"]).strip()
        if payload.get("runtime_key") is not None
        else None
    )
    return Tool(
        id=tool_id,
        name=_required_string(payload, "name", manifest_path),
        description=_required_string(payload, "description", manifest_path),
        kind=_parse_enum(
            payload.get("tool_kind", ToolKind.FUNCTION.value),
            enum_type=ToolKind,
            field_name="tool_kind",
            manifest_path=manifest_path,
        ),
        parameters=_parse_parameters(payload.get("parameters", []), manifest_path),
        tags=_parse_string_list(payload.get("tags", []), "tags", manifest_path),
        required_effect_ids=_parse_string_list(
            payload.get("required_effect_ids", []),
            "required_effect_ids",
            manifest_path,
        ),
        access_requirements=_parse_string_list(
            payload.get("access_requirements", []),
            "access_requirements",
            manifest_path,
        ),
        access_requirement_sets=_parse_string_sets(
            payload.get("access_requirement_sets", []),
            "access_requirement_sets",
            manifest_path,
        ),
        runtime_requirement_sets=_runtime_requirement_sets(
            payload.get("runtime_requirement_sets", []),
            dependency_requirements=dependency_requirements,
            manifest_path=manifest_path,
        ),
        context_requirements=_parse_string_list(
            payload.get("context_requirements", []),
            "context_requirements",
            manifest_path,
        ),
        capability_ids=capability_ids,
        credential_requirements=_parse_credential_requirement_sets(
            payload.get("credential_requirements", []),
            manifest_path,
            tool_id=tool_id,
            runtime_key=runtime_key,
        ),
        execution_policy=ToolExecutionPolicy(
            timeout_seconds=max(int(payload.get("timeout_seconds", 30)), 1),
            requires_confirmation=bool(payload.get("requires_confirmation", False)),
            mutates_state=bool(payload.get("mutates_state", False)),
            supports_parallel=bool(payload.get("supports_parallel", True)),
            resource_scope=_optional_manifest_text(payload.get("resource_scope")),
            serial_group_key=_optional_manifest_text(payload.get("serial_group_key")),
        ),
        execution_support=ToolExecutionSupport(
            supported_modes=_parse_enum_list(
                payload.get("supported_modes", [ToolMode.INLINE.value]),
                enum_type=ToolMode,
                field_name="supported_modes",
                manifest_path=manifest_path,
            ),
            supported_strategies=_parse_enum_list(
                payload.get(
                    "supported_strategies",
                    [ToolExecutionStrategy.ASYNC.value],
                ),
                enum_type=ToolExecutionStrategy,
                field_name="supported_strategies",
                manifest_path=manifest_path,
            ),
            supported_environments=_parse_enum_list(
                payload.get(
                    "supported_environments",
                    [ToolEnvironment.LOCAL.value],
                ),
                enum_type=ToolEnvironment,
                field_name="supported_environments",
                manifest_path=manifest_path,
            ),
        ),
        definition_origin=_parse_enum(
            payload.get("definition_origin", ToolDefinitionOrigin.LOCAL_DISCOVERY.value),
            enum_type=ToolDefinitionOrigin,
            field_name="definition_origin",
            manifest_path=manifest_path,
        ),
        runtime_key=runtime_key,
        enabled=bool(payload.get("enabled", True)),
    )


def _load_openapi_provider(
    payload: dict[str, Any],
    manifest_path: Path,
) -> OpenApiProviderSettings:
    spec_raw = str(payload.get("spec", "")).strip()
    if not spec_raw:
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' kind openapi must define spec.",
        )
    spec_path = (manifest_path.parent / spec_raw).resolve()
    if not spec_path.is_file():
        raise ToolValidationError(
            f"OpenAPI spec '{spec_raw}' referenced by '{manifest_path}' was not found.",
        )
    return OpenApiProviderSettings(
        name=_required_string(payload, "namespace", manifest_path),
        spec_location=str(spec_path),
        base_url=(
            str(payload["base_url"]).strip()
            if payload.get("base_url") is not None
            else None
        ),
        description=str(payload.get("description", "")).strip(),
        timeout_seconds=max(int(payload.get("timeout_seconds", 30)), 1),
        max_concurrency=_parse_optional_positive_int(
            payload.get("max_concurrency"),
            field_name="max_concurrency",
            manifest_path=manifest_path,
        ),
        credential_bindings=_parse_openapi_credentials(
            payload.get("credentials", {}),
            manifest_path,
        ),
        default_effect_ids=_parse_string_list(
            payload.get("default_effect_ids", []),
            "default_effect_ids",
            manifest_path,
        ),
        runtime_requirements=tuple(
            _parse_string_list(
                payload.get("runtime_requirements", []),
                "runtime_requirements",
                manifest_path,
            ),
        ),
    )


def _parse_optional_positive_int(
    raw_value: object,
    *,
    field_name: str,
    manifest_path: Path,
) -> int | None:
    if raw_value is None:
        return None
    if isinstance(raw_value, str) and not raw_value.strip():
        return None
    try:
        parsed = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' field '{field_name}' must be a positive integer.",
        ) from exc
    if parsed < 1:
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' field '{field_name}' must be a positive integer.",
        )
    return parsed


def _parse_openapi_credentials(
    raw_credentials: object,
    manifest_path: Path,
) -> tuple[OpenApiCredentialBinding, ...]:
    if raw_credentials in (None, {}):
        return ()
    if not isinstance(raw_credentials, dict):
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' field 'credentials' must be a mapping.",
        )
    bindings: list[OpenApiCredentialBinding] = []
    for raw_scheme_name, raw_binding in raw_credentials.items():
        scheme_name = str(raw_scheme_name).strip()
        if not scheme_name:
            raise ToolValidationError(
                f"Tool namespace manifest '{manifest_path}' credentials require non-empty scheme names.",
            )
        if isinstance(raw_binding, str):
            value = raw_binding.strip()
            if not value:
                raise ToolValidationError(
                    f"Tool namespace manifest '{manifest_path}' credential binding '{scheme_name}' cannot be empty.",
                )
            _reject_direct_openapi_credential_source(
                value,
                manifest_path=manifest_path,
                scheme_name=scheme_name,
                field_name="credential_binding_id",
            )
            bindings.append(
                OpenApiCredentialBinding(
                    scheme_name=scheme_name,
                    credential_binding_id=value,
                ),
            )
            continue
        if not isinstance(raw_binding, dict):
            raise ToolValidationError(
                f"Tool namespace manifest '{manifest_path}' credential binding '{scheme_name}' must be a string or mapping.",
            )
        _reject_legacy_openapi_credential_fields(
            raw_binding,
            manifest_path=manifest_path,
            scheme_name=scheme_name,
        )
        binding = OpenApiCredentialBinding(
            scheme_name=scheme_name,
            credential_binding_id=_optional_mapping_text(
                raw_binding,
                "credential_binding_id",
            ),
            username_binding_id=_optional_mapping_text(
                raw_binding,
                "username_binding_id",
            ),
            password_binding_id=_optional_mapping_text(
                raw_binding,
                "password_binding_id",
            ),
        )
        _ensure_openapi_credential_binding(
            binding,
            manifest_path=manifest_path,
            scheme_name=scheme_name,
        )
        bindings.append(binding)
    return tuple(bindings)


def _optional_mapping_text(
    value: dict[str, object],
    *keys: str,
) -> str | None:
    for key in keys:
        raw = value.get(key)
        if raw is None:
            continue
        normalized = str(raw).strip()
        if normalized:
            return normalized
    return None


def _reject_legacy_openapi_credential_fields(
    value: dict[str, object],
    *,
    manifest_path: Path,
    scheme_name: str,
) -> None:
    for field_name in (
        "source",
        "username_source",
        "password_source",
        "username",
        "password",
        "auth_ref",  # forbidden legacy credential field
        "credential_binding",
        "credential_binding_ref",
        "binding_id",
        "username_binding",
        "password_binding",
    ):
        if value.get(field_name) is not None:
            raise ToolValidationError(
                f"Tool namespace manifest '{manifest_path}' credential binding "
                f"'{scheme_name}' must use Access credential binding ids; "
                f"field '{field_name}' is no longer accepted.",
            )
    for field_name in (
        "credential_binding_id",
        "username_binding_id",
        "password_binding_id",
    ):
        candidate = value.get(field_name)
        if candidate is None:
            continue
        _reject_direct_openapi_credential_source(
            str(candidate),
            manifest_path=manifest_path,
            scheme_name=scheme_name,
            field_name=field_name,
        )


def _ensure_openapi_credential_binding(
    binding: OpenApiCredentialBinding,
    *,
    manifest_path: Path,
    scheme_name: str,
) -> None:
    if binding.credential_binding_id is not None:
        return
    if binding.username_binding_id is not None and binding.password_binding_id is not None:
        return
    raise ToolValidationError(
        f"Tool namespace manifest '{manifest_path}' credential binding "
        f"'{scheme_name}' must define credential_binding_id or username/password "
        "binding ids.",
    )


def _reject_direct_openapi_credential_source(
    value: str,
    *,
    manifest_path: Path,
    scheme_name: str,
    field_name: str,
) -> None:
    normalized = value.strip()
    if normalized.startswith(_forbidden_openapi_credential_source_prefixes):
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' credential binding "
            f"'{scheme_name}' field '{field_name}' must reference an Access "
            "credential binding id, not a direct credential source.",
        )


def _parse_parameters(
    raw_parameters: object,
    manifest_path: Path,
) -> tuple[ToolParameter, ...]:
    if not isinstance(raw_parameters, list):
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' field 'parameters' must be a list.",
        )
    parameters: list[ToolParameter] = []
    for item in raw_parameters:
        if not isinstance(item, dict):
            raise ToolValidationError(
                f"Tool namespace manifest '{manifest_path}' parameter entries must be mappings.",
            )
        parameters.append(
            ToolParameter(
                name=_required_string(item, "name", manifest_path),
                data_type=_required_string(item, "data_type", manifest_path),
                description=str(item.get("description", "")).strip(),
                required=bool(item.get("required", True)),
                json_schema=_optional_mapping_payload(item.get("json_schema")),
            ),
        )
    return tuple(parameters)


def _optional_manifest_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _parse_string_list(
    raw_values: object,
    field_name: str,
    manifest_path: Path,
) -> tuple[str, ...]:
    if not isinstance(raw_values, list):
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' field '{field_name}' must be a list.",
        )
    return tuple(
        str(item).strip()
        for item in raw_values
        if str(item).strip()
    )


def _parse_string_sets(
    raw_values: object,
    field_name: str,
    manifest_path: Path,
) -> tuple[tuple[str, ...], ...]:
    if not isinstance(raw_values, list):
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' field '{field_name}' must be a list.",
        )
    return tuple(
        _parse_string_list(item, field_name, manifest_path)
        for item in raw_values
    )


def _runtime_requirement_sets(
    raw_values: object,
    *,
    dependency_requirements: tuple[ToolDependencyRequirement, ...],
    manifest_path: Path,
) -> tuple[tuple[str, ...], ...]:
    requirement_sets = list(
        _parse_string_sets(raw_values, "runtime_requirement_sets", manifest_path),
    )
    external_requirements = tuple(
        dependency.id
        for dependency in dependency_requirements
        if dependency.kind == "external_requirement" and dependency.id.strip()
    )
    if external_requirements:
        requirement_sets.append(tuple(dict.fromkeys(external_requirements)))
    return tuple(dict.fromkeys(requirement_sets))


def _parse_credential_requirement_sets(
    raw_values: object,
    manifest_path: Path,
    *,
    tool_id: str,
    runtime_key: str | None,
) -> tuple[AccessCredentialRequirementSet, ...]:
    if raw_values in (None, []):
        return ()
    if not isinstance(raw_values, list):
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' field 'credential_requirements' must be a list.",
        )
    consumer = AccessConsumerRef(
        consumer_id=tool_id,
        module="tool",
        component="local_package",
        runtime_ref=runtime_key,
        metadata={"manifest_path": str(manifest_path)},
    )
    requirement_sets: list[AccessCredentialRequirementSet] = []
    for index, raw_set in enumerate(raw_values):
        if not isinstance(raw_set, dict):
            raise ToolValidationError(
                f"Tool namespace manifest '{manifest_path}' credential_requirements[{index}] must be a mapping.",
            )
        raw_requirements = raw_set.get("requirements")
        if raw_requirements is None:
            raw_requirements = [raw_set]
        if not isinstance(raw_requirements, list):
            raise ToolValidationError(
                f"Tool namespace manifest '{manifest_path}' credential_requirements[{index}].requirements must be a list.",
            )
        declarations = tuple(
            _parse_credential_requirement(
                raw_requirement,
                manifest_path,
                consumer=consumer,
                set_index=index,
                requirement_index=requirement_index,
            )
            for requirement_index, raw_requirement in enumerate(raw_requirements)
        )
        requirement_sets.append(
            AccessCredentialRequirementSet(
                requirement_set_id=str(
                    raw_set.get("requirement_set_id")
                    or raw_set.get("id")
                    or f"{tool_id}.credentials.{index}",
                ),
                consumer=consumer,
                requirements=declarations,
                alternative=bool(raw_set.get("alternative", False)),
                metadata=_mapping_payload(raw_set.get("metadata")),
            ),
        )
    return tuple(requirement_sets)


def _parse_credential_requirement(
    raw_value: object,
    manifest_path: Path,
    *,
    consumer: AccessConsumerRef,
    set_index: int,
    requirement_index: int,
) -> AccessCredentialRequirementDeclaration:
    if not isinstance(raw_value, dict):
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' credential requirement entries must be mappings.",
        )
    raw_slot = raw_value.get("slot")
    slot_payload = raw_slot if isinstance(raw_slot, dict) else {}
    slot = _required_text_value(
        slot_payload.get("slot") if slot_payload else raw_slot,
        field_name="slot",
        manifest_path=manifest_path,
    )
    expected_kind = _parse_access_credential_kind(
        slot_payload.get("expected_kind")
        or raw_value.get("expected_kind")
        or raw_value.get("kind"),
        manifest_path=manifest_path,
    )
    provider = _optional_text(raw_value.get("provider"))
    binding_id = _optional_text(
        slot_payload.get("binding_id") or raw_value.get("binding_id"),
    )
    if binding_id is not None:
        _reject_direct_credential_requirement_binding(
            binding_id,
            manifest_path=manifest_path,
            slot=slot,
        )
    return AccessCredentialRequirementDeclaration(
        requirement_id=str(
            raw_value.get("requirement_id")
            or raw_value.get("id")
            or f"{consumer.consumer_id}.{slot}.{set_index}.{requirement_index}",
        ),
        consumer=consumer,
        slot=AccessCredentialSlotRef(
            slot=slot,
            expected_kind=expected_kind,
            binding_id=binding_id,
            required=bool(slot_payload.get("required", raw_value.get("required", True))),
            display_name=_optional_text(
                slot_payload.get("display_name") or raw_value.get("display_name"),
            ),
            scopes=_string_tuple(
                slot_payload.get("scopes") or raw_value.get("scopes") or (),
            ),
            metadata=_mapping_payload(slot_payload.get("metadata")),
        ),
        provider=provider,
        transport=_parse_access_credential_transport(
            raw_value.get("transport"),
            manifest_path=manifest_path,
        ),
        parameter_name=_optional_text(raw_value.get("parameter_name")),
        setup_flow_hint=_parse_setup_flow_hint(
            raw_value.get("setup_flow_hint"),
            provider=provider,
            manifest_path=manifest_path,
        ),
        metadata=_mapping_payload(raw_value.get("metadata")),
    )


def _reject_direct_credential_requirement_binding(
    value: str,
    *,
    manifest_path: Path,
    slot: str,
) -> None:
    normalized = value.strip()
    if normalized.startswith(_forbidden_openapi_credential_source_prefixes):
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' credential requirement "
            f"slot '{slot}' must reference an Access credential binding id, "
            "not a direct credential source.",
        )


def _parse_access_credential_kind(
    raw_value: object,
    *,
    manifest_path: Path,
) -> AccessCredentialKind:
    normalized = _required_text_value(
        raw_value,
        field_name="expected_kind",
        manifest_path=manifest_path,
    )
    try:
        return AccessCredentialKind(normalized)
    except ValueError as exc:
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' uses unsupported credential kind '{normalized}'.",
        ) from exc


def _parse_access_credential_transport(
    raw_value: object,
    *,
    manifest_path: Path,
) -> AccessCredentialTransport:
    normalized = str(raw_value or AccessCredentialTransport.RUNTIME_CONTEXT).strip()
    try:
        return AccessCredentialTransport(normalized)
    except ValueError as exc:
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' uses unsupported credential transport '{normalized}'.",
        ) from exc


def _parse_setup_flow_hint(
    raw_value: object,
    *,
    provider: str | None,
    manifest_path: Path,
) -> AccessSetupFlowHint:
    if raw_value in (None, {}):
        return AccessSetupFlowHint(
            flow_kind=AccessSetupFlowKind.MANUAL,
            provider=provider,
        )
    if not isinstance(raw_value, dict):
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' setup_flow_hint must be a mapping.",
        )
    raw_flow_kind = raw_value.get("flow_kind") or AccessSetupFlowKind.MANUAL
    try:
        flow_kind = AccessSetupFlowKind(str(raw_flow_kind).strip())
    except ValueError as exc:
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' uses unsupported setup flow '{raw_flow_kind}'.",
        ) from exc
    return AccessSetupFlowHint(
        flow_kind=flow_kind,
        provider=_optional_text(raw_value.get("provider")) or provider,
        authorization_url=_optional_text(raw_value.get("authorization_url")),
        token_url=_optional_text(raw_value.get("token_url")),
        device_code_url=_optional_text(raw_value.get("device_code_url")),
        callback_url=_optional_text(raw_value.get("callback_url")),
        metadata=_mapping_payload(raw_value.get("metadata")),
    )


def _required_text_value(
    raw_value: object,
    *,
    field_name: str,
    manifest_path: Path,
) -> str:
    normalized = str(raw_value or "").strip()
    if not normalized:
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' credential requirement must define '{field_name}'.",
        )
    return normalized


def _optional_text(raw_value: object) -> str | None:
    if raw_value is None:
        return None
    normalized = str(raw_value).strip()
    return normalized or None


def _string_tuple(raw_value: object) -> tuple[str, ...]:
    if raw_value is None:
        return ()
    if isinstance(raw_value, str):
        return (raw_value.strip(),) if raw_value.strip() else ()
    if isinstance(raw_value, list | tuple):
        return tuple(str(item).strip() for item in raw_value if str(item).strip())
    return ()


def _mapping_payload(raw_value: object) -> dict[str, object]:
    return dict(raw_value) if isinstance(raw_value, dict) else {}


def _optional_mapping_payload(raw_value: object) -> dict[str, object] | None:
    return dict(raw_value) if isinstance(raw_value, dict) else None


def _stable_payload(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _stable_payload(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, dict):
        return {
            str(key): _stable_payload(item)
            for key, item in value.items()
        }
    if isinstance(value, tuple | list):
        return [_stable_payload(item) for item in value]
    return value


def _parse_enum_list(
    raw_values: object,
    *,
    enum_type,
    field_name: str,
    manifest_path: Path,
) -> tuple[Any, ...]:
    if not isinstance(raw_values, list):
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' field '{field_name}' must be a list.",
        )
    return tuple(
        _parse_enum(
            value,
            enum_type=enum_type,
            field_name=field_name,
            manifest_path=manifest_path,
        )
        for value in raw_values
    )


def _parse_enum(
    raw_value: object,
    *,
    enum_type,
    field_name: str,
    manifest_path: Path,
):
    try:
        return enum_type(str(raw_value).strip())
    except ValueError as exc:
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' field '{field_name}' "
            f"declares unsupported value '{raw_value}'.",
        ) from exc


def _required_string(
    payload: dict[str, Any],
    field_name: str,
    manifest_path: Path,
) -> str:
    value = str(payload.get(field_name, "")).strip()
    if not value:
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' must define non-empty '{field_name}'.",
        )
    return value


def _resolve_local_handler_activation(
    binding: ToolHandlerPlan,
    context: ToolPackageApplyContext,
) -> ResolvedToolHandlerActivation | None:
    context.validate_capabilities(
        binding.capability_ids,
        owner=(
            f"Tool namespace '{binding.namespace}' handler "
            f"'{binding.tool.id}'"
        ),
    )
    _validate_external_requirements(binding.dependencies, context, owner=binding.tool.id)
    factory_deps = _local_handler_factory_deps(binding, context)
    handler = _build_local_handler(binding, factory_deps)
    if handler is None:
        return None
    registration = _registration_for_local_handler(binding, handler)
    return ResolvedToolHandlerActivation(
        plan=binding,
        registration=registration,
        factory_deps=factory_deps,
    )


def _resolve_runtime_activation(
    binding: ToolRuntimePlan,
    context: ToolPackageApplyContext,
) -> ResolvedToolRuntimeActivation | None:
    context.validate_capabilities(
        binding.capability_ids,
        owner=(
            f"Tool namespace '{binding.namespace}' runtime "
            f"'{binding.runtime_key}'"
        ),
    )
    _validate_external_requirements(
        binding.dependencies,
        context,
        owner=binding.runtime_key,
    )
    handler = _build_runtime_handler(binding.entrypoint, context)
    if handler is None:
        return None
    return ResolvedToolRuntimeActivation(
        plan=binding,
        registration=ToolHandlerRegistration(
            namespace=binding.namespace,
            tool_id=binding.runtime_key,
            entrypoint=binding.entrypoint,
            handler=handler,
            runtime_key=binding.runtime_key,
            runtime_kind=binding.runtime_kind,
            capability_ids=binding.capability_ids,
        ),
    )


def _build_local_handler(
    binding: ToolHandlerPlan,
    factory_deps: ToolHandlerFactoryDeps,
) -> LocalToolHandler | None:
    entrypoint = binding.entrypoint
    builder = _load_entrypoint(entrypoint)
    handler = builder(_local_handler_factory_argument(builder, factory_deps))
    if handler is not None and not callable(handler):
        raise ToolValidationError(
            f"Tool entrypoint '{entrypoint}' did not return a callable handler.",
        )
    return handler


def _local_handler_factory_argument(
    builder,
    factory_deps: ToolHandlerFactoryDeps,
) -> Any:
    dependency_type = _local_handler_dependency_type(builder, factory_deps)
    if dependency_type is not None:
        return dependency_type
    if not factory_deps.requirements:
        return None
    raise ToolValidationError(
        f"Tool entrypoint '{factory_deps.entrypoint}' declares service dependencies "
        "but does not accept a typed dependency dataclass.",
    )


def _local_handler_dependency_type(
    builder,
    factory_deps: ToolHandlerFactoryDeps,
) -> object | None:
    try:
        parameters = tuple(signature(builder).parameters.values())
    except (TypeError, ValueError) as exc:
        raise ToolValidationError(
            f"Tool entrypoint '{factory_deps.entrypoint}' has an invalid factory signature.",
        ) from exc
    positional = tuple(
        parameter
        for parameter in parameters
        if parameter.kind
        in (Parameter.POSITIONAL_ONLY, Parameter.POSITIONAL_OR_KEYWORD)
    )
    if not positional:
        if factory_deps.requirements:
            raise ToolValidationError(
                f"Tool entrypoint '{factory_deps.entrypoint}' has no dependency parameter.",
            )
        return None
    parameter = positional[0]
    if parameter.name == "factory_deps":
        return factory_deps
    try:
        hints = get_type_hints(builder)
    except (NameError, TypeError, AttributeError):
        hints = {}
    annotation = hints.get(parameter.name, parameter.annotation)
    if annotation is ToolHandlerFactoryDeps:
        return factory_deps
    candidates = _dependency_dataclass_candidates(annotation)
    missing_by_type: dict[str, tuple[str, ...]] = {}
    for candidate in candidates:
        built, missing = _build_typed_handler_deps(candidate, factory_deps)
        if not missing:
            return built
        missing_by_type[candidate.__name__] = missing
    if candidates:
        formatted_missing = "; ".join(
            f"{name}: {', '.join(missing)}"
            for name, missing in missing_by_type.items()
        )
        raise ToolValidationError(
            f"Tool entrypoint '{factory_deps.entrypoint}' typed dependencies could "
            f"not be satisfied ({formatted_missing}).",
        )
    return None


def _dependency_dataclass_candidates(annotation: object) -> tuple[type[Any], ...]:
    if annotation in (Parameter.empty, Any):
        return ()
    origin = get_origin(annotation)
    if origin in (Union, UnionType):
        return tuple(
            candidate
            for item in get_args(annotation)
            for candidate in _dependency_dataclass_candidates(item)
        )
    if isinstance(annotation, type) and is_dataclass(annotation):
        return (annotation,)
    return ()


def _build_typed_handler_deps(
    dependency_type: type[Any],
    factory_deps: ToolHandlerFactoryDeps,
) -> tuple[object | None, tuple[str, ...]]:
    values: dict[str, Any] = {}
    missing: list[str] = []
    available = {
        **factory_deps.services,
        **factory_deps.config,
    }
    for field in fields(dependency_type):
        dependency_id = str(field.metadata.get("dependency_id") or field.name)
        if dependency_id in available:
            values[field.name] = available[dependency_id]
            continue
        if field.default is not MISSING or field.default_factory is not MISSING:
            continue
        missing.append(dependency_id)
    if missing:
        return None, tuple(missing)
    return dependency_type(**values), ()


def _local_handler_factory_deps(
    binding: ToolHandlerPlan,
    context: ToolPackageApplyContext,
) -> ToolHandlerFactoryDeps:
    services: dict[str, Any] = {}
    config: dict[str, Any] = {}
    for dependency in binding.dependencies:
        if dependency.kind == "external_requirement":
            continue
        dependency_source = _dependency_source(dependency)
        target = config if dependency_source == "config" else services
        value = (
            context.setting(dependency.id)
            if dependency_source == "config"
            else context.dependency(
                dependency.id,
                declared_capability_ids=binding.capability_ids,
            )
        )
        if value is None:
            if dependency.kind == "service_dependency" and dependency.required:
                raise ToolValidationError(
                    f"Tool namespace '{binding.namespace}' handler '{binding.tool.id}' "
                    f"requires service dependency '{dependency.id}'.",
                )
            continue
        target[dependency.id] = value
    return ToolHandlerFactoryDeps(
        namespace=binding.namespace,
        tool_id=binding.tool.id,
        entrypoint=binding.entrypoint,
        services=services,
        config=config,
        capability_ids=binding.capability_ids,
        requirements=binding.dependencies,
    )


def _validate_external_requirements(
    dependencies: tuple[ToolDependencyRequirement, ...],
    context: ToolPackageApplyContext,
    *,
    owner: str,
) -> None:
    for dependency in dependencies:
        if dependency.kind != "external_requirement" or not dependency.required:
            continue
        if not context.has_external_requirement(dependency.id):
            raise ToolValidationError(
                f"Tool '{owner}' requires unavailable runtime requirement "
                f"'{dependency.id}'.",
            )


def _dependency_source(dependency: ToolDependencyRequirement) -> str:
    metadata = dependency.metadata or {}
    source = metadata.get("source")
    if source is None:
        return "service"
    return str(source).strip() or "service"


def _build_runtime_handler(
    entrypoint: str,
    context: ToolPackageApplyContext,
) -> AsyncToolHandler | None:
    builder = _load_entrypoint(entrypoint)
    handler = builder(context)
    if handler is not None and not callable(handler):
        raise ToolValidationError(
            f"Tool runtime entrypoint '{entrypoint}' did not return a callable handler.",
        )
    return handler


def _load_entrypoint(entrypoint: str):
    module_name, separator, symbol_name = entrypoint.partition(":")
    module_name = module_name.strip()
    symbol_name = symbol_name.strip()
    if separator != ":" or not module_name or not symbol_name:
        raise ToolValidationError(
            f"Tool entrypoint '{entrypoint}' must use the form 'module.path:callable_name'.",
        )
    module = importlib.import_module(module_name)
    target = getattr(module, symbol_name, None)
    if target is None:
        raise ToolValidationError(
            f"Tool entrypoint '{entrypoint}' could not resolve callable '{symbol_name}'.",
        )
    if not callable(target):
        raise ToolValidationError(
            f"Tool entrypoint '{entrypoint}' resolved non-callable symbol '{symbol_name}'.",
        )
    return target
