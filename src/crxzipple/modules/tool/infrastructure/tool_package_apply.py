from __future__ import annotations

from crxzipple.modules.tool.application.activation import (
    ResolvedToolPackageActivation,
    ToolPackageApplyContext,
    ToolPackageApplyResult,
    ToolPackagePlan,
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
from crxzipple.modules.tool.infrastructure.runtimes.openapi_remote import (
    register_openapi_remote_handlers,
)
from crxzipple.modules.tool.infrastructure.runtimes.registry import (
    ToolRuntimeRegistry,
)
from crxzipple.modules.tool.infrastructure.tool_package_activation_resolution import (
    resolve_tool_package_activations,
)


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
        _apply_local_handlers(context, activation)
        _apply_remote_runtimes(context, activation)
        _apply_sandbox_runtimes(context, activation)
        if activation.openapi is not None:
            _apply_openapi_namespace(context, activation)
    return ToolPackageApplyResult(activations=resolved)


def _apply_local_handlers(
    context: ToolPackageApplyContext,
    activation: ResolvedToolPackageActivation,
) -> None:
    if not activation.local_handlers:
        return
    local_runtime_registry = context.local_runtime_registry
    assert isinstance(local_runtime_registry, LocalToolRuntimeRegistry)
    for item in activation.local_handlers:
        local_runtime_registry.register(
            item.plan.tool,
            item.registration.handler,
            provider_name=item.plan.provider_name,
        )


def _apply_remote_runtimes(
    context: ToolPackageApplyContext,
    activation: ResolvedToolPackageActivation,
) -> None:
    if not activation.remote_runtimes:
        return
    remote_tool_registry = context.remote_tool_registry
    assert isinstance(remote_tool_registry, ToolRuntimeRegistry)
    for item in activation.remote_runtimes:
        remote_tool_registry.register(
            item.plan.runtime_key,
            item.registration.handler,
        )


def _apply_sandbox_runtimes(
    context: ToolPackageApplyContext,
    activation: ResolvedToolPackageActivation,
) -> None:
    if not activation.sandbox_runtimes:
        return
    sandbox_tool_registry = context.sandbox_tool_registry
    assert isinstance(sandbox_tool_registry, ToolRuntimeRegistry)
    for item in activation.sandbox_runtimes:
        sandbox_tool_registry.register(
            item.plan.runtime_key,
            item.registration.handler,
        )


def _apply_openapi_namespace(
    context: ToolPackageApplyContext,
    activation: ResolvedToolPackageActivation,
) -> None:
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


class _UnavailableCredentialProvider:
    def resolve_credential(self, *_args, **_kwargs) -> str:
        raise ToolValidationError(
            "OpenAPI operation requires credentials, but no credential provider "
            "binding was available during tool package activation.",
        )


__all__ = ["apply_tool_package_plans"]
