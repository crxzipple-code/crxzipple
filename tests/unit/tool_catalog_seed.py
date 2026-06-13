from __future__ import annotations

from collections.abc import Callable
from typing import Any

from crxzipple.interfaces.runtime_container import AppKey
from crxzipple.modules.tool.domain import (
    Tool,
    ToolCatalogSourceKind,
    ToolDefinitionOrigin,
    ToolEnvironment,
    ToolExecutionStrategy,
    ToolExecutionSupport,
    ToolFunction,
    ToolFunctionRuntimeKind,
    ToolFunctionStatus,
    ToolKind,
    ToolMode,
    ToolParameter,
    ToolRunResult,
    ToolSource,
)
from crxzipple.modules.tool.interfaces.dto import _credential_requirement_set_payload
from crxzipple.shared.access import AccessCredentialRequirementSet


def seed_catalog_tool(
    container: object,
    *,
    tool_id: str,
    name: str | None = None,
    description: str = "Seeded catalog tool for unit tests.",
    kind: ToolKind = ToolKind.FUNCTION,
    parameters: tuple[ToolParameter, ...] = (),
    tags: tuple[str, ...] = (),
    mutates_state: bool = False,
    timeout_seconds: int = 30,
    requires_confirmation: bool = False,
    required_effect_ids: tuple[str, ...] = (),
    access_requirements: tuple[str, ...] = (),
    access_requirement_sets: tuple[tuple[str, ...], ...] | None = None,
    credential_requirements: tuple[AccessCredentialRequirementSet, ...] = (),
    runtime_requirement_sets: tuple[tuple[str, ...], ...] = (),
    capability_ids: tuple[str, ...] = (),
    supported_modes: tuple[ToolMode, ...] = (ToolMode.INLINE,),
    supported_strategies: tuple[ToolExecutionStrategy, ...] = (
        ToolExecutionStrategy.ASYNC,
    ),
    supported_environments: tuple[ToolEnvironment, ...] = (ToolEnvironment.LOCAL,),
    definition_origin: ToolDefinitionOrigin = ToolDefinitionOrigin.LOCAL_DISCOVERY,
    runtime_key: str | None = None,
    enabled: bool = True,
    handler: Callable[..., Any] | None = None,
    source_id: str | None = None,
) -> Tool:
    resolved_source_id = source_id or f"test.local_package.{tool_id}"
    resolved_runtime_key = runtime_key or tool_id
    with container.require(AppKey.UNIT_OF_WORK_FACTORY)() as uow:
        uow.tool_sources.upsert(
            ToolSource(
                id=resolved_source_id,
                display_name=f"Test source for {tool_id}",
                kind=ToolCatalogSourceKind.LOCAL_PACKAGE,
                description="Unit test source seeded through the catalog.",
                config={"namespace": "unit_test"},
            ),
        )
        uow.tool_functions.upsert(
            ToolFunction(
                id=tool_id,
                source_id=resolved_source_id,
                stable_key=f"{resolved_source_id}.{tool_id}",
                name=name or tool_id,
                display_name=name or tool_id,
                description=description,
                input_schema=_input_schema(parameters),
                runtime_kind=ToolFunctionRuntimeKind.LOCAL,
                handler_ref={"ref": resolved_runtime_key},
                credential_requirements=tuple(
                    _credential_requirement_set_payload(requirement_set)
                    for requirement_set in credential_requirements
                ),
                access_requirement_sets=(
                    access_requirement_sets
                    if access_requirement_sets is not None
                    else (tuple(access_requirements),) if access_requirements else ()
                ),
                runtime_requirements=tuple(
                    {"requirements": tuple(requirement_set)}
                    for requirement_set in runtime_requirement_sets
                ),
                required_effect_ids=required_effect_ids,
                execution_support=ToolExecutionSupport(
                    supported_modes=supported_modes,
                    supported_strategies=supported_strategies,
                    supported_environments=supported_environments,
                ),
                capability_ids=capability_ids,
                enabled=enabled,
                metadata={
                    "tool_kind": kind.value,
                    "definition_origin": definition_origin.value,
                    "runtime_key": resolved_runtime_key,
                    "tags": tuple(tags),
                    "execution_policy": {
                        "timeout_seconds": timeout_seconds,
                        "requires_confirmation": requires_confirmation,
                        "mutates_state": mutates_state,
                    },
                    "execution_support": {
                        "supported_modes": tuple(mode.value for mode in supported_modes),
                        "supported_strategies": tuple(
                            strategy.value for strategy in supported_strategies
                        ),
                        "supported_environments": tuple(
                            environment.value for environment in supported_environments
                        ),
                    },
                },
                status=ToolFunctionStatus.ACTIVE,
            ),
        )
        uow.commit()
    tool = container.require(AppKey.TOOL_SERVICE).get_tool(tool_id)
    if handler is not None:
        container.require(AppKey.TOOL_LOCAL_RUNTIME_REGISTRY).register(
            tool,
            handler,
            provider_name="local_system",
        )
    return tool


def _input_schema(parameters: tuple[ToolParameter, ...]) -> dict[str, object]:
    properties = {
        parameter.name: {
            "type": parameter.data_type,
            "x-crxzipple-data-type": parameter.data_type,
            "description": parameter.description,
        }
        for parameter in parameters
    }
    schema: dict[str, object] = {
        "type": "object",
        "properties": properties,
    }
    required = [parameter.name for parameter in parameters if parameter.required]
    if required:
        schema["required"] = required
    return schema


def static_text_handler(text: str = "ok") -> Callable[..., Any]:
    async def _handler(_arguments: dict[str, object]) -> ToolRunResult:
        return ToolRunResult.text(text)

    return _handler
