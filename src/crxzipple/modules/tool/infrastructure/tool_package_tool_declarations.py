from __future__ import annotations

from pathlib import Path

from crxzipple.modules.tool.application.activation import ToolDependencyRequirement
from crxzipple.modules.tool.domain import (
    Tool,
    ToolDefinitionOrigin,
    ToolEnvironment,
    ToolExecutionPolicy,
    ToolExecutionStrategy,
    ToolExecutionSupport,
    ToolKind,
    ToolMode,
    ToolParameter,
)
from crxzipple.modules.tool.domain.exceptions import ToolValidationError
from crxzipple.modules.tool.infrastructure.tool_package_access import (
    parse_credential_requirement_sets,
)
from crxzipple.modules.tool.infrastructure.tool_package_manifest_values import (
    optional_manifest_text,
    optional_mapping_payload,
    parse_enum,
    parse_enum_list,
    parse_string_list,
    parse_string_sets,
    required_string,
    runtime_requirement_sets,
)


def build_tool_from_manifest(
    payload: dict[str, object],
    manifest_path: Path,
    *,
    dependency_requirements: tuple[ToolDependencyRequirement, ...] = (),
    capability_ids: tuple[str, ...] = (),
) -> Tool:
    tool_id = required_string(payload, "id", manifest_path)
    runtime_key = (
        str(payload["runtime_key"]).strip()
        if payload.get("runtime_key") is not None
        else None
    )
    return Tool(
        id=tool_id,
        name=required_string(payload, "name", manifest_path),
        description=required_string(payload, "description", manifest_path),
        kind=parse_enum(
            payload.get("tool_kind", ToolKind.FUNCTION.value),
            enum_type=ToolKind,
            field_name="tool_kind",
            manifest_path=manifest_path,
        ),
        parameters=_parse_parameters(payload.get("parameters", []), manifest_path),
        tags=parse_string_list(payload.get("tags", []), "tags", manifest_path),
        required_effect_ids=parse_string_list(
            payload.get("required_effect_ids", []),
            "required_effect_ids",
            manifest_path,
        ),
        access_requirements=parse_string_list(
            payload.get("access_requirements", []),
            "access_requirements",
            manifest_path,
        ),
        access_requirement_sets=parse_string_sets(
            payload.get("access_requirement_sets", []),
            "access_requirement_sets",
            manifest_path,
        ),
        runtime_requirement_sets=runtime_requirement_sets(
            payload.get("runtime_requirement_sets", []),
            dependency_requirements=dependency_requirements,
            manifest_path=manifest_path,
        ),
        context_requirements=parse_string_list(
            payload.get("context_requirements", []),
            "context_requirements",
            manifest_path,
        ),
        capability_ids=capability_ids,
        credential_requirements=parse_credential_requirement_sets(
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
            resource_scope=optional_manifest_text(payload.get("resource_scope")),
            serial_group_key=optional_manifest_text(payload.get("serial_group_key")),
        ),
        execution_support=ToolExecutionSupport(
            supported_modes=parse_enum_list(
                payload.get("supported_modes", [ToolMode.INLINE.value]),
                enum_type=ToolMode,
                field_name="supported_modes",
                manifest_path=manifest_path,
            ),
            supported_strategies=parse_enum_list(
                payload.get(
                    "supported_strategies",
                    [ToolExecutionStrategy.ASYNC.value],
                ),
                enum_type=ToolExecutionStrategy,
                field_name="supported_strategies",
                manifest_path=manifest_path,
            ),
            supported_environments=parse_enum_list(
                payload.get(
                    "supported_environments",
                    [ToolEnvironment.LOCAL.value],
                ),
                enum_type=ToolEnvironment,
                field_name="supported_environments",
                manifest_path=manifest_path,
            ),
        ),
        definition_origin=parse_enum(
            payload.get("definition_origin", ToolDefinitionOrigin.LOCAL_DISCOVERY.value),
            enum_type=ToolDefinitionOrigin,
            field_name="definition_origin",
            manifest_path=manifest_path,
        ),
        runtime_key=runtime_key,
        enabled=bool(payload.get("enabled", True)),
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
                name=required_string(item, "name", manifest_path),
                data_type=required_string(item, "data_type", manifest_path),
                description=str(item.get("description", "")).strip(),
                required=bool(item.get("required", True)),
                json_schema=optional_mapping_payload(item.get("json_schema")),
            ),
        )
    return tuple(parameters)
