from __future__ import annotations

from crxzipple.core.config import OpenApiProviderSettings
from crxzipple.modules.tool.application.capabilities import (
    DEFAULT_TOOL_CAPABILITY_CATALOG,
)
from crxzipple.modules.tool.application.activation import (
    ResolvedToolHandlerActivation,
    ResolvedToolPackageActivation,
    ResolvedToolRuntimeActivation,
    ToolHandlerPlan,
    ToolOpenApiPlan,
    ToolPackageApplyContext,
    ToolPackagePlan,
    ToolRuntimePlan,
)
from crxzipple.modules.tool.domain.exceptions import ToolValidationError
from crxzipple.modules.tool.infrastructure.discovery.local_runtime_registry import (
    LocalToolRuntimeRegistry,
)
from crxzipple.modules.tool.infrastructure.discovery.providers import (
    ToolDiscoveryRegistry,
)
from crxzipple.modules.tool.infrastructure.runtimes.registry import (
    ToolRuntimeRegistry,
)
from crxzipple.modules.tool.infrastructure.tool_package_activation import (
    resolve_local_handler_activation,
    resolve_runtime_activation,
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
        activations.append(
            _resolve_tool_package_activation(
                context,
                namespace,
                include_openapi=include_openapi,
                include_local=include_local,
                include_runtimes=include_runtimes,
            ),
        )
    return tuple(activations)


def _resolve_tool_package_activation(
    context: ToolPackageApplyContext,
    namespace: ToolPackagePlan,
    *,
    include_openapi: bool,
    include_local: bool,
    include_runtimes: bool,
) -> ResolvedToolPackageActivation:
    namespace_name = _package_namespace(namespace)
    package_kind = _package_kind(namespace)
    context.validate_capabilities(
        getattr(namespace, "capability_ids", ()),
        owner=f"Tool namespace '{namespace_name}'",
    )
    if package_kind == "local_package":
        return _resolve_local_package_activation(
            context,
            namespace,
            namespace_name=namespace_name,
            include_local=include_local,
            include_runtimes=include_runtimes,
        )
    if (
        package_kind == "openapi"
        and include_openapi
        and _openapi_provider(namespace) is not None
        and isinstance(context.tool_discovery_registry, ToolDiscoveryRegistry)
        and isinstance(context.remote_tool_registry, ToolRuntimeRegistry)
    ):
        return _resolve_openapi_package_activation(
            context,
            namespace,
            namespace_name=namespace_name,
        )
    return ResolvedToolPackageActivation(
        namespace=namespace_name,
        package_kind=package_kind,
    )


def _resolve_local_package_activation(
    context: ToolPackageApplyContext,
    namespace: ToolPackagePlan,
    *,
    namespace_name: str,
    include_local: bool,
    include_runtimes: bool,
) -> ResolvedToolPackageActivation:
    local_handlers: tuple[ResolvedToolHandlerActivation, ...] = ()
    remote_runtimes: tuple[ResolvedToolRuntimeActivation, ...] = ()
    sandbox_runtimes: tuple[ResolvedToolRuntimeActivation, ...] = ()
    if include_local and isinstance(
        context.local_runtime_registry,
        LocalToolRuntimeRegistry,
    ):
        active_handler_refs = context.local_function_refs_for_namespace(namespace_name)
        local_handlers = tuple(
            item
            for item in (
                resolve_local_handler_activation(binding, context)
                for binding in _local_handler_plans(namespace)
                if _local_handler_enabled_by_catalog(binding, active_handler_refs)
            )
            if item is not None
        )
    if include_runtimes and isinstance(context.remote_tool_registry, ToolRuntimeRegistry):
        remote_runtimes = tuple(
            item
            for item in (
                resolve_runtime_activation(binding, context)
                for binding in _remote_runtime_plans(namespace)
            )
            if item is not None
        )
    if include_runtimes and isinstance(context.sandbox_tool_registry, ToolRuntimeRegistry):
        sandbox_runtimes = tuple(
            item
            for item in (
                resolve_runtime_activation(binding, context)
                for binding in _sandbox_runtime_plans(namespace)
            )
            if item is not None
        )
    return ResolvedToolPackageActivation(
        namespace=namespace_name,
        package_kind="local_package",
        local_handlers=local_handlers,
        remote_runtimes=remote_runtimes,
        sandbox_runtimes=sandbox_runtimes,
    )


def _resolve_openapi_package_activation(
    context: ToolPackageApplyContext,
    namespace: ToolPackagePlan,
    *,
    namespace_name: str,
) -> ResolvedToolPackageActivation:
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
    return ResolvedToolPackageActivation(
        namespace=namespace_name,
        package_kind="openapi",
        openapi=openapi_plan,
    )


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
        _validate_unique_local_handlers(namespace, tool_ids, include_local=include_local)
        _validate_unique_runtimes(namespace, runtime_keys, include_runtimes=include_runtimes)


def _validate_unique_local_handlers(
    namespace: ToolPackagePlan,
    tool_ids: set[str],
    *,
    include_local: bool,
) -> None:
    if not include_local:
        return
    for handler in _local_handler_plans(namespace):
        DEFAULT_TOOL_CAPABILITY_CATALOG.validate_capability_ids(handler.capability_ids)
        tool_id = handler.tool.id
        if tool_id in tool_ids:
            raise ToolValidationError(
                f"Duplicate tool id '{tool_id}' in package apply plan.",
            )
        tool_ids.add(tool_id)


def _validate_unique_runtimes(
    namespace: ToolPackagePlan,
    runtime_keys: set[str],
    *,
    include_runtimes: bool,
) -> None:
    if not include_runtimes:
        return
    for runtime in (*_remote_runtime_plans(namespace), *_sandbox_runtime_plans(namespace)):
        DEFAULT_TOOL_CAPABILITY_CATALOG.validate_capability_ids(runtime.capability_ids)
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


__all__ = ["resolve_tool_package_activations"]
