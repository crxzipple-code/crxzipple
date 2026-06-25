from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from crxzipple.core.config import (
    PROJECT_ROOT,
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
    ToolDependencyRequirement,
    ToolHandlerPlan,
    ToolOpenApiPlan,
    ToolPackageApplyContext,
    ToolPackageApplyResult,
    ToolPackagePlan,
    ToolRuntimeKind,
    ToolRuntimePlan,
)
from crxzipple.modules.tool.domain.exceptions import ToolValidationError
from crxzipple.modules.tool.infrastructure.discovery.local_runtime_registry import (
    LocalToolRuntimeRegistry,
)
from crxzipple.modules.tool.infrastructure.discovery.openapi import (
    OpenApiDiscoveryProvider,
)
from crxzipple.modules.tool.infrastructure.discovery.providers import (
    ToolDiscoveryRegistry,
)
from crxzipple.modules.tool.infrastructure.tool_package_access import (
    load_openapi_provider_from_manifest,
)
from crxzipple.modules.tool.infrastructure.tool_package_activation import (
    resolve_local_handler_activation,
    resolve_runtime_activation,
)
from crxzipple.modules.tool.infrastructure.tool_package_manifest_values import (
    combined_capability_ids,
    load_capability_ids,
    load_dependency_requirements,
    load_runtime_request_metadata,
    required_string,
)
from crxzipple.modules.tool.infrastructure.tool_package_provider_backends import (
    load_provider_backend_plans,
)
from crxzipple.modules.tool.infrastructure.tool_package_tool_declarations import (
    build_tool_from_manifest,
)
from crxzipple.modules.tool.infrastructure.runtimes.openapi_remote import (
    register_openapi_remote_handlers,
)
from crxzipple.modules.tool.infrastructure.runtimes.registry import (
    ToolRuntimeRegistry,
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
                        resolve_local_handler_activation(binding, context)
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
                        resolve_runtime_activation(binding, context)
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
                        resolve_runtime_activation(binding, context)
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


def _load_yaml_mapping(manifest_path: Path) -> dict[str, object]:
    loader = getattr(yaml, "CSafeLoader", yaml.SafeLoader)
    payload = yaml.load(manifest_path.read_text(encoding="utf-8"), Loader=loader)
    if not isinstance(payload, dict):
        raise ToolValidationError(
            f"Tool namespace manifest '{manifest_path}' must decode to a mapping.",
        )
    return payload


def _load_namespace(manifest_path: Path) -> ToolNamespaceDefinition:
    payload = _load_yaml_mapping(manifest_path)

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
    package_dependencies = load_dependency_requirements(
        payload.get("dependencies", []),
        manifest_path,
    )
    package_capability_ids = load_capability_ids(payload, manifest_path)
    if kind == "local_package":
        return ToolNamespaceDefinition(
            namespace=namespace_name,
            root_path=str(manifest_path.parent),
            manifest_path=str(manifest_path),
            package_kind=kind,
            capability_ids=package_capability_ids,
            runtime_request=load_runtime_request_metadata(payload.get("runtime_request"), manifest_path),
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
            provider_backends=load_provider_backend_plans(
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
            runtime_request=load_runtime_request_metadata(payload.get("runtime_request"), manifest_path),
            openapi=ToolOpenApiPlan(
                namespace=namespace_name,
                provider=load_openapi_provider_from_manifest(payload, manifest_path),
                capability_ids=package_capability_ids,
                dependencies=package_dependencies,
            ),
            provider_backends=load_provider_backend_plans(
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
            + load_dependency_requirements(
                item.get("dependencies", []),
                manifest_path,
            )
        )
        capability_ids = combined_capability_ids(
            package_capability_ids,
            load_capability_ids(item, manifest_path),
        )
        bindings.append(
            LocalToolBinding(
                namespace=namespace,
                tool=build_tool_from_manifest(
                    item,
                    manifest_path,
                    dependency_requirements=dependencies,
                    capability_ids=capability_ids,
                ),
                provider_name=str(item.get("provider_name", "local_system")).strip()
                or "local_system",
                entrypoint=required_string(item, "entrypoint", manifest_path),
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
                runtime_key=required_string(item, "runtime_key", manifest_path),
                entrypoint=required_string(item, "entrypoint", manifest_path),
                runtime_kind=runtime_kind,
                capability_ids=combined_capability_ids(
                    package_capability_ids,
                    load_capability_ids(item, manifest_path),
                ),
                dependencies=(
                    package_dependencies
                    + load_dependency_requirements(
                        item.get("dependencies", []),
                        manifest_path,
                    )
                ),
            ),
        )
    return tuple(bindings)
