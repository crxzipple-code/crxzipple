from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from crxzipple.modules.tool.application.specifications import ToolSpec
from crxzipple.core.config import McpProviderSettings
from crxzipple.modules.tool.domain import ToolDefinitionOrigin
from crxzipple.modules.tool.domain.exceptions import ToolValidationError
from crxzipple.modules.tool.domain.value_objects import (
    ToolEnvironment,
    ToolExecutionPolicy,
    ToolExecutionSupport,
    ToolExecutionStrategy,
    ToolKind,
    ToolMode,
    ToolParameter,
)
from crxzipple.modules.tool.infrastructure.mcp_client import McpClient, build_mcp_client


@dataclass(frozen=True, slots=True)
class McpToolDefinition:
    provider_name: str
    tool_name: str
    tool_id: str
    runtime_key: str
    name: str
    description: str
    tags: tuple[str, ...]
    parameters: tuple[ToolParameter, ...]
    timeout_seconds: int
    mutates_state: bool
    required_effect_ids: tuple[str, ...] = ()

    def to_tool_spec(self) -> ToolSpec:
        return ToolSpec(
            id=self.tool_id,
            name=self.name,
            description=self.description,
            provider_name=self.provider_name,
            kind=ToolKind.MCP,
            parameters=self.parameters,
            tags=self.tags,
            required_effect_ids=self.required_effect_ids,
            execution_policy=ToolExecutionPolicy(
                timeout_seconds=self.timeout_seconds,
                requires_confirmation=False,
                mutates_state=self.mutates_state,
            ),
            execution_support=ToolExecutionSupport(
                supported_modes=(ToolMode.INLINE, ToolMode.BACKGROUND),
                supported_strategies=(ToolExecutionStrategy.ASYNC,),
                supported_environments=(ToolEnvironment.REMOTE,),
            ),
            definition_origin=ToolDefinitionOrigin.REMOTE_DISCOVERY,
            runtime_key=self.runtime_key,
            enabled=True,
        )


class McpDiscoveryProvider:
    definition_origin = ToolDefinitionOrigin.REMOTE_DISCOVERY

    def __init__(
        self,
        config: McpProviderSettings,
        *,
        client: McpClient | None = None,
    ) -> None:
        self.config = config
        self.name = config.name
        self.description = (
            config.description
            or f"Discovers MCP tools exposed by provider '{config.name}'."
        )
        self.client = client or build_mcp_client(config)
        self._definitions_cache: tuple[McpToolDefinition, ...] | None = None

    def discover_specs(self) -> list[ToolSpec]:
        return [definition.to_tool_spec() for definition in self.definitions()]

    def definitions(self) -> tuple[McpToolDefinition, ...]:
        if self._definitions_cache is None:
            self._definitions_cache = tuple(
                _parse_tool_definitions(
                    self.name,
                    self.config.timeout_seconds,
                    self.config.default_effect_ids,
                    self.client.list_tools(),
                ),
            )
        return self._definitions_cache


def _parse_tool_definitions(
    provider_name: str,
    timeout_seconds: int,
    default_effect_ids: tuple[str, ...],
    tools: list[dict[str, Any]],
) -> list[McpToolDefinition]:
    definitions: list[McpToolDefinition] = []
    for tool in tools:
        tool_name = str(tool.get("name", "")).strip()
        if not tool_name:
            raise ToolValidationError(
                f"MCP provider '{provider_name}' returned a tool without a name.",
            )

        title = str(tool.get("title") or tool_name).strip()
        description = str(
            tool.get("description") or tool.get("title") or f"MCP tool {tool_name}",
        ).strip()
        input_schema = tool.get("inputSchema") if isinstance(tool.get("inputSchema"), dict) else {}
        tags = tuple(
            dict.fromkeys(
                tag
                for tag in (
                    *(
                        str(tag).strip().lower()
                        for tag in tool.get("tags", [])
                        if str(tag).strip()
                    ),
                    "mcp",
                    provider_name.lower(),
                )
                if tag
            ),
        )
        tool_id = f"{provider_name}.{tool_name}"
        runtime_key = f"mcp.{provider_name}.{tool_name}"

        definitions.append(
            McpToolDefinition(
                provider_name=provider_name,
                tool_name=tool_name,
                tool_id=tool_id,
                runtime_key=runtime_key,
                name=title,
                description=description,
                tags=tags,
                parameters=_parameters_from_input_schema(input_schema),
                timeout_seconds=timeout_seconds,
                mutates_state=_mutates_state(tool),
                required_effect_ids=default_effect_ids,
            ),
        )

    return definitions


def _parameters_from_input_schema(input_schema: dict[str, Any]) -> tuple[ToolParameter, ...]:
    properties = (
        input_schema.get("properties")
        if isinstance(input_schema.get("properties"), dict)
        else {}
    )
    required = {
        str(name)
        for name in input_schema.get("required", [])
        if isinstance(name, str) and name.strip()
    }

    parameters: list[ToolParameter] = []
    for name, schema in properties.items():
        if not isinstance(schema, dict):
            continue
        description = str(schema.get("description", "")).strip()
        parameters.append(
            ToolParameter(
                name=str(name),
                data_type=_schema_type(schema),
                description=description,
                required=str(name) in required,
                json_schema=_tool_parameter_json_schema(
                    schema,
                    description=description,
                ),
            ),
        )
    return tuple(parameters)


def _tool_parameter_json_schema(
    schema: dict[str, Any],
    *,
    description: str,
) -> dict[str, Any]:
    payload = dict(schema)
    if not payload:
        payload["type"] = _schema_type(schema)
    if description and not payload.get("description"):
        payload["description"] = description
    return payload


def _schema_type(schema: dict[str, Any]) -> str:
    schema_type = str(schema.get("type", "")).strip().lower()
    if schema_type == "array":
        items = schema.get("items") if isinstance(schema.get("items"), dict) else {}
        return f"array[{_schema_type(items)}]"
    if schema_type:
        return schema_type
    if "properties" in schema:
        return "object"
    return "string"


def _mutates_state(tool: dict[str, Any]) -> bool:
    annotations = tool.get("annotations") if isinstance(tool.get("annotations"), dict) else {}
    read_only_hint = annotations.get("readOnlyHint")
    if isinstance(read_only_hint, bool):
        return not read_only_hint
    return False
