from __future__ import annotations

from crxzipple.modules.llm.domain import ToolSchema
from crxzipple.modules.orchestration.application.runtime_request_mode import (
    RuntimeRequestMode,
)
from crxzipple.modules.orchestration.application.runtime_request_report import (
    RunSurfacePolicy,
)
from crxzipple.modules.orchestration.application.runtime_step_budget_policy import (
    RuntimeStepBudget,
)
from crxzipple.modules.orchestration.application.runtime_tool_schema_policy import (
    RuntimeToolSchemaPolicy,
)
from crxzipple.modules.orchestration.application.tool_resolver import (
    ResolvedTool,
    ResolvedToolSet,
)
from crxzipple.modules.tool.domain import Tool, ToolExecutionTarget


def test_tool_schema_policy_includes_tools_for_normal_non_final_turn() -> None:
    assert RuntimeToolSchemaPolicy().should_include_tool_schemas(
        resolved_mode=RuntimeRequestMode.NORMAL_TURN,
        surface_policy=RunSurfacePolicy(include_tool_schemas=True),
        resolved_tools=_resolved_tools(),
        step_budget=_budget(remaining_steps=2),
    )


def test_tool_schema_policy_keeps_tools_for_normal_final_step() -> None:
    assert RuntimeToolSchemaPolicy().should_include_tool_schemas(
        resolved_mode=RuntimeRequestMode.NORMAL_TURN,
        surface_policy=RunSurfacePolicy(include_tool_schemas=True),
        resolved_tools=_resolved_tools(),
        step_budget=_budget(remaining_steps=1),
    )


def test_tool_schema_policy_keeps_tools_for_memory_flush_final_step() -> None:
    assert RuntimeToolSchemaPolicy().should_include_tool_schemas(
        resolved_mode=RuntimeRequestMode.MEMORY_FLUSH,
        surface_policy=RunSurfacePolicy(
            surface="maintenance_write",
            include_tool_schemas=True,
        ),
        resolved_tools=_resolved_tools(),
        step_budget=_budget(remaining_steps=1),
    )


def test_tool_schema_policy_respects_surface_without_tool_schemas() -> None:
    assert not RuntimeToolSchemaPolicy().should_include_tool_schemas(
        resolved_mode=RuntimeRequestMode.NORMAL_TURN,
        surface_policy=RunSurfacePolicy(include_tool_schemas=False),
        resolved_tools=_resolved_tools(),
        step_budget=_budget(remaining_steps=10),
    )


def _budget(*, remaining_steps: int) -> RuntimeStepBudget:
    return RuntimeStepBudget(
        current_step=0,
        max_steps=remaining_steps,
        remaining_steps=remaining_steps,
        status="available",
    )


def _resolved_tools() -> ResolvedToolSet:
    return ResolvedToolSet(
        tools=(
            ResolvedTool(
                tool=Tool(
                    id="tool.weather",
                    name="weather.lookup",
                    description="Lookup weather.",
                ),
                schema=ToolSchema(name="weather.lookup"),
                target=ToolExecutionTarget(),
            ),
        ),
    )
