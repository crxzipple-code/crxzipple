from __future__ import annotations

from dataclasses import MISSING, fields, is_dataclass
import importlib
from inspect import Parameter, signature
from types import UnionType
from typing import Any, Union, get_args, get_origin, get_type_hints

from crxzipple.modules.tool.application.activation import (
    ResolvedToolHandlerActivation,
    ResolvedToolRuntimeActivation,
    ToolDependencyRequirement,
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
