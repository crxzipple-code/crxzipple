from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from crxzipple.modules.tool.domain.entities import Tool
from crxzipple.modules.tool.domain.entities import ToolFunction
from crxzipple.modules.tool.domain.value_objects import (
    ToolDefinitionOrigin,
    ToolEnvironment,
    ToolExecutionPolicy,
    ToolExecutionStrategy,
    ToolExecutionSupport,
    ToolKind,
    ToolMode,
    ToolParameter,
)

from .credential_requirement_payloads import credential_requirement_sets_from_payload


def build_tool_from_function(function: ToolFunction) -> Tool:
    metadata = dict(function.metadata)
    return Tool(
        id=function.function_id,
        source_id=function.source_id,
        name=function.name,
        description=function.description,
        kind=_tool_kind_from_metadata(metadata),
        parameters=_parameters_from_input_schema(function.input_schema),
        tags=tuple(
            str(tag).strip()
            for tag in metadata.get("tags", ())
            if str(tag).strip()
        ),
        required_effect_ids=function.required_effect_overrides
        if function.required_effect_overrides is not None
        else function.required_effect_ids,
        access_requirement_sets=function.access_requirement_sets,
        runtime_requirement_sets=_runtime_requirement_sets(function),
        context_requirements=_context_requirements(metadata),
        capability_ids=function.capability_ids,
        credential_requirements=credential_requirement_sets_from_payload(
            function.credential_requirements,
        ),
        execution_policy=_execution_policy_from_metadata(metadata),
        execution_support=_execution_support_from_metadata(
            metadata,
            default=function.execution_support,
        ),
        definition_origin=_tool_definition_origin_from_metadata(metadata),
        runtime_key=_runtime_key_from_function(function),
        enabled=function.enabled,
    )


def _tool_kind_from_metadata(metadata: Mapping[str, Any]) -> ToolKind:
    value = str(metadata.get("tool_kind") or ToolKind.FUNCTION.value)
    try:
        return ToolKind(value)
    except ValueError:
        return ToolKind.FUNCTION


def _tool_definition_origin_from_metadata(
    metadata: Mapping[str, Any],
) -> ToolDefinitionOrigin:
    value = str(
        metadata.get("definition_origin") or ToolDefinitionOrigin.LOCAL_DISCOVERY.value,
    )
    try:
        return ToolDefinitionOrigin(value)
    except ValueError:
        return ToolDefinitionOrigin.LOCAL_DISCOVERY


def _execution_policy_from_metadata(metadata: Mapping[str, Any]) -> ToolExecutionPolicy:
    raw_policy = metadata.get("execution_policy")
    policy = raw_policy if isinstance(raw_policy, Mapping) else {}
    return ToolExecutionPolicy(
        timeout_seconds=max(int(policy.get("timeout_seconds") or 30), 1),
        requires_confirmation=bool(policy.get("requires_confirmation", False)),
        mutates_state=bool(policy.get("mutates_state", False)),
        supports_parallel=bool(policy.get("supports_parallel", True)),
        resource_scope=_optional_policy_text(policy.get("resource_scope")),
        serial_group_key=_optional_policy_text(policy.get("serial_group_key")),
    )


def _execution_support_from_metadata(
    metadata: Mapping[str, Any],
    *,
    default: ToolExecutionSupport,
) -> ToolExecutionSupport:
    raw_support = metadata.get("execution_support")
    support = raw_support if isinstance(raw_support, Mapping) else {}
    if not support:
        return default
    return ToolExecutionSupport(
        supported_modes=_enum_tuple_from_metadata(
            support.get("supported_modes"),
            enum_type=ToolMode,
            default=default.supported_modes,
        ),
        supported_strategies=_enum_tuple_from_metadata(
            support.get("supported_strategies"),
            enum_type=ToolExecutionStrategy,
            default=default.supported_strategies,
        ),
        supported_environments=_enum_tuple_from_metadata(
            support.get("supported_environments"),
            enum_type=ToolEnvironment,
            default=default.supported_environments,
        ),
    )


def _enum_tuple_from_metadata(
    value: object,
    *,
    enum_type: Any,
    default: tuple[Any, ...],
) -> tuple[Any, ...]:
    if not isinstance(value, list | tuple):
        return default
    parsed: list[Any] = []
    for item in value:
        try:
            parsed.append(enum_type(str(item)))
        except ValueError:
            continue
    return tuple(dict.fromkeys(parsed)) or default


def _parameters_from_input_schema(
    input_schema: Mapping[str, Any],
) -> tuple[ToolParameter, ...]:
    raw_properties = input_schema.get("properties")
    properties = raw_properties if isinstance(raw_properties, Mapping) else {}
    raw_required = input_schema.get("required")
    required = {
        str(item).strip()
        for item in raw_required
        if str(item).strip()
    } if isinstance(raw_required, list | tuple) else set()
    parameters: list[ToolParameter] = []
    for name, raw_schema in properties.items():
        if not isinstance(name, str) or not name.strip():
            continue
        schema = raw_schema if isinstance(raw_schema, Mapping) else {}
        parameters.append(
            ToolParameter(
                name=name,
                data_type=_parameter_data_type(schema),
                description=str(schema.get("description") or ""),
                required=name in required,
            ),
        )
    return tuple(parameters)


def _parameter_data_type(schema: Mapping[str, Any]) -> str:
    explicit = schema.get("x-crxzipple-data-type")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    value = schema.get("type")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return "string"


def _runtime_requirement_sets(function: ToolFunction) -> tuple[tuple[str, ...], ...]:
    values: list[tuple[str, ...]] = []
    for item in function.runtime_requirements:
        raw_requirements = item.get("requirements")
        if isinstance(raw_requirements, list | tuple):
            normalized = tuple(
                dict.fromkeys(
                    str(requirement).strip()
                    for requirement in raw_requirements
                    if str(requirement).strip()
                ),
            )
            if normalized:
                values.append(normalized)
            continue
        raw_requirement = item.get("requirement")
        if isinstance(raw_requirement, str) and raw_requirement.strip():
            values.append((raw_requirement.strip(),))
    return tuple(values)


def _context_requirements(metadata: Mapping[str, Any]) -> tuple[str, ...]:
    raw_values = metadata.get("context_requirements")
    if not isinstance(raw_values, list | tuple):
        return ()
    return tuple(
        dict.fromkeys(
            str(value).strip()
            for value in raw_values
            if str(value).strip()
        ),
    )


def _runtime_key_from_function(function: ToolFunction) -> str:
    for key in ("ref", "runtime_key", "handler"):
        value = function.handler_ref.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return function.function_id


def _optional_policy_text(value: object | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


__all__ = ["build_tool_from_function"]
