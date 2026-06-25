from __future__ import annotations

from dataclasses import dataclass

from crxzipple.modules.tool.domain import ToolRun


@dataclass(frozen=True, slots=True)
class ToolExecutionControlDecision:
    yield_requested: bool = False
    yield_reason: str | None = None
    stop_remaining_batches: bool = False


def tool_execution_control_decision(tool_run: ToolRun) -> ToolExecutionControlDecision:
    yield_requested, yield_reason = _yield_control(tool_run)
    if yield_requested:
        return ToolExecutionControlDecision(
            yield_requested=True,
            yield_reason=yield_reason,
        )
    return ToolExecutionControlDecision(
        stop_remaining_batches=_terminal_plan_stops_remaining_batches(tool_run),
    )


def _yield_control(tool_run: ToolRun) -> tuple[bool, str | None]:
    tool_result = tool_run.result
    if tool_result is None:
        return False, None
    payload = tool_result.metadata.get("session_control")
    if not isinstance(payload, dict):
        return False, None
    if payload.get("yield") is not True:
        return False, None
    reason = payload.get("reason")
    if isinstance(reason, str):
        normalized_reason = reason.strip()
        if normalized_reason:
            return True, normalized_reason
    return True, None


def _terminal_plan_stops_remaining_batches(tool_run: ToolRun) -> bool:
    tool_result = tool_run.result
    if tool_result is None:
        return False
    if tool_result.metadata.get("terminal_plan") is not True:
        return False
    tool_name = tool_result.metadata.get("tool")
    if isinstance(tool_name, str) and tool_name.strip() != "context_tree.update_plan":
        return False
    return True


__all__ = [
    "ToolExecutionControlDecision",
    "tool_execution_control_decision",
]
