from __future__ import annotations

from dataclasses import MISSING, fields, is_dataclass
from inspect import Parameter, signature
from types import UnionType
from typing import Any, Union, get_args, get_origin, get_type_hints

from crxzipple.modules.tool.application.activation import (
    ToolDependencyRequirement,
    ToolHandlerFactoryDeps,
    ToolHandlerPlan,
    ToolPackageApplyContext,
)
from crxzipple.modules.tool.domain.exceptions import ToolValidationError


def local_handler_factory_argument(
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


def build_local_handler_factory_deps(
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


def validate_external_requirements(
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


def _dependency_source(dependency: ToolDependencyRequirement) -> str:
    metadata = dependency.metadata or {}
    source = metadata.get("source")
    if source is None:
        return "service"
    return str(source).strip() or "service"


__all__ = [
    "build_local_handler_factory_deps",
    "local_handler_factory_argument",
    "validate_external_requirements",
]
