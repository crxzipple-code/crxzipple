from __future__ import annotations

from crxzipple.modules.llm.domain import ToolCallIntent
from crxzipple.modules.orchestration.application.tool_execution_grouping import (
    group_prepared_tool_executions,
    is_terminal_plan_control_tool,
)
from crxzipple.modules.orchestration.application.tool_execution_records import (
    PreparedToolExecution,
)
from crxzipple.modules.orchestration.application.tool_resource_policy import (
    ToolResourcePolicy,
)
from crxzipple.modules.tool.domain import ToolExecutionTarget


def test_group_prepared_tool_executions_batches_parallel_tools_together() -> None:
    first = _prepared("call-fetch-1", "web.fetch_text")
    second = _prepared("call-fetch-2", "web.fetch_text")

    assert group_prepared_tool_executions((first, second)) == ((first, second),)


def test_group_prepared_tool_executions_splits_conflicting_serial_resources() -> None:
    first = _prepared(
        "call-click-1",
        "browser.click",
        resource_policy=ToolResourcePolicy(
            supports_parallel=False,
            mutates_state=True,
            execution_lane="serial",
            resource_scope="browser.target",
            resource_key="browser.target:profile=default;target=page-1",
            serial_group_key="browser.target",
        ),
    )
    second = _prepared(
        "call-click-2",
        "browser.click",
        resource_policy=ToolResourcePolicy(
            supports_parallel=False,
            mutates_state=True,
            execution_lane="serial",
            resource_scope="browser.target",
            resource_key="browser.target:profile=default;target=page-1",
            serial_group_key="browser.target",
        ),
    )

    assert group_prepared_tool_executions((first, second)) == ((first,), (second,))


def test_group_prepared_tool_executions_isolates_terminal_plan_control_tool() -> None:
    before = _prepared("call-before", "web.fetch_text")
    terminal_plan = _prepared("call-plan", "context_tree.update_plan")
    after = _prepared("call-after", "web.fetch_text")

    assert is_terminal_plan_control_tool(terminal_plan) is True
    assert group_prepared_tool_executions((before, terminal_plan, after)) == (
        (before,),
        (terminal_plan,),
        (after,),
    )


def _prepared(
    call_id: str,
    tool_name: str,
    *,
    resource_policy: ToolResourcePolicy | None = None,
) -> PreparedToolExecution:
    return PreparedToolExecution(
        tool_call=ToolCallIntent(
            id=call_id,
            name=tool_name,
            arguments={},
        ),
        tool_id=tool_name,
        target=ToolExecutionTarget(),
        resource_policy=resource_policy
        or ToolResourcePolicy(
            supports_parallel=True,
            mutates_state=False,
            execution_lane="parallel",
        ),
    )
