from __future__ import annotations

from crxzipple.modules.tool.application.activation import (
    ResolvedToolHandlerActivation,
    ResolvedToolRuntimeActivation,
    ToolHandlerFactoryDeps,
    ToolHandlerPlan,
    ToolHandlerRegistration,
    ToolPackageApplyContext,
    ToolRuntimePlan,
)
from crxzipple.modules.tool.domain.exceptions import ToolValidationError
from crxzipple.modules.tool.infrastructure.discovery.local_runtime_registry import (
    LocalToolHandler,
)
from crxzipple.modules.tool.infrastructure.runtimes.registry import AsyncToolHandler
from crxzipple.modules.tool.infrastructure.tool_package_activation_dependencies import (
    build_local_handler_factory_deps,
    local_handler_factory_argument,
    validate_external_requirements,
)
from crxzipple.modules.tool.infrastructure.tool_package_entrypoints import (
    load_tool_entrypoint,
)


def resolve_local_handler_activation(
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
    validate_external_requirements(binding.dependencies, context, owner=binding.tool.id)
    factory_deps = build_local_handler_factory_deps(binding, context)
    handler = _build_local_handler(binding, factory_deps)
    if handler is None:
        return None
    registration = _registration_for_local_handler(binding, handler)
    return ResolvedToolHandlerActivation(
        plan=binding,
        registration=registration,
        factory_deps=factory_deps,
    )


def resolve_runtime_activation(
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
    validate_external_requirements(
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


def _build_local_handler(
    binding: ToolHandlerPlan,
    factory_deps: ToolHandlerFactoryDeps,
) -> LocalToolHandler | None:
    entrypoint = binding.entrypoint
    builder = load_tool_entrypoint(entrypoint)
    handler = builder(local_handler_factory_argument(builder, factory_deps))
    if handler is not None and not callable(handler):
        raise ToolValidationError(
            f"Tool entrypoint '{entrypoint}' did not return a callable handler.",
        )
    return handler


def _build_runtime_handler(
    entrypoint: str,
    context: ToolPackageApplyContext,
) -> AsyncToolHandler | None:
    builder = load_tool_entrypoint(entrypoint)
    handler = builder(context)
    if handler is not None and not callable(handler):
        raise ToolValidationError(
            f"Tool runtime entrypoint '{entrypoint}' did not return a callable handler.",
        )
    return handler
