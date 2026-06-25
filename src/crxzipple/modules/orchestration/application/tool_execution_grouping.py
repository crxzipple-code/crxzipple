from __future__ import annotations

from crxzipple.modules.orchestration.application.tool_execution_records import (
    PreparedToolExecution,
)
from crxzipple.modules.orchestration.application.tool_resource_policy import (
    resource_policies_conflict,
)


def group_prepared_tool_executions(
    prepared_batch: tuple[PreparedToolExecution, ...],
) -> tuple[tuple[PreparedToolExecution, ...], ...]:
    groups: list[tuple[PreparedToolExecution, ...]] = []
    current: list[PreparedToolExecution] = []
    for prepared in prepared_batch:
        if is_terminal_plan_control_tool(prepared):
            if current:
                groups.append(tuple(current))
                current = []
            groups.append((prepared,))
            continue
        if current and any(
            resource_policies_conflict(
                prepared.resource_policy,
                item.resource_policy,
            )
            for item in current
        ):
            groups.append(tuple(current))
            current = [prepared]
            continue
        current.append(prepared)
    if current:
        groups.append(tuple(current))
    return tuple(groups)


def is_terminal_plan_control_tool(prepared: PreparedToolExecution) -> bool:
    return (
        prepared.tool_call.name == "context_tree.update_plan"
        or prepared.tool_id == "context_tree.update_plan"
    )


__all__ = [
    "group_prepared_tool_executions",
    "is_terminal_plan_control_tool",
]
