from __future__ import annotations

from dataclasses import dataclass

from crxzipple.modules.llm.domain import ToolCallIntent
from crxzipple.modules.orchestration.application.tool_execution_control import (
    tool_execution_control_decision,
)
from crxzipple.modules.orchestration.application.tool_execution_records import (
    PreparedToolExecution,
    ToolExecutionBatchState,
    ToolRunLink,
    tool_lifecycle_from_tool_run,
)
from crxzipple.modules.tool.domain import ToolRun, ToolRunStatus


ToolResultMessageItem = tuple[ToolCallIntent, ToolRun, str, str]


@dataclass(frozen=True, slots=True)
class ToolExecutionResultRecord:
    result_message_item: ToolResultMessageItem | None = None
    result_link_position: int | None = None


def record_tool_execution_result(
    state: ToolExecutionBatchState,
    prepared: PreparedToolExecution,
    tool_run: ToolRun,
    *,
    append_tool_result_messages: bool,
) -> ToolExecutionResultRecord:
    tool_call = prepared.tool_call
    call_session_item_id = state.tool_call_session_item_id_by_call_id.get(
        tool_call.id,
    )
    if tool_run.status is ToolRunStatus.QUEUED:
        state.background_runs.append((tool_call, tool_run))
        state.tool_run_links.append(
            tool_run_link(
                prepared,
                tool_run,
                background=True,
                call_session_item_id=call_session_item_id,
            ),
        )
        return ToolExecutionResultRecord()

    result_link_position = None
    result_message_item = None
    if append_tool_result_messages:
        result_link_position = len(state.tool_run_links)
        result_message_item = (tool_call, tool_run, "tool_run", tool_run.id)

    state.inline_runs.append(tool_run)
    state.tool_run_links.append(
        tool_run_link(
            prepared,
            tool_run,
            background=False,
            call_session_item_id=call_session_item_id,
        ),
    )

    control_decision = tool_execution_control_decision(tool_run)
    if control_decision.yield_requested:
        state.request_yield(control_decision.yield_reason)
    elif control_decision.stop_remaining_batches:
        state.stop_remaining()

    return ToolExecutionResultRecord(
        result_message_item=result_message_item,
        result_link_position=result_link_position,
    )


def tool_run_link(
    prepared: PreparedToolExecution,
    tool_run: ToolRun,
    *,
    background: bool,
    call_session_item_id: str | None = None,
) -> ToolRunLink:
    return ToolRunLink(
        tool_call_id=prepared.tool_call.id,
        tool_name=prepared.tool_call.name,
        tool_run_id=tool_run.id,
        tool_id=prepared.tool_id,
        status=tool_run.status.value,
        mode=prepared.target.mode.value,
        strategy=prepared.target.strategy.value,
        environment=prepared.target.environment.value,
        call_session_item_id=call_session_item_id,
        background=background,
        tool_execution_plan=(
            prepared.plan.to_payload() if prepared.plan is not None else {}
        ),
        tool_lifecycle=tool_lifecycle_from_tool_run(tool_run),
    )


__all__ = [
    "ToolExecutionResultRecord",
    "ToolResultMessageItem",
    "record_tool_execution_result",
    "tool_run_link",
]
