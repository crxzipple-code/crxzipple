from __future__ import annotations

from collections.abc import Callable
from typing import Any

from crxzipple.modules.tool.application.tool_result_artifacts import (
    externalize_tool_result_attachments,
)
from crxzipple.modules.tool.application.tool_result_validation import (
    validate_tool_result_details,
)
from crxzipple.modules.tool.domain.entities import Tool
from crxzipple.modules.tool.domain.exceptions import ToolValidationError
from crxzipple.modules.tool.domain.value_objects import (
    ToolExecutionContext,
    ToolExecutionTarget,
    ToolMode,
    ToolRunResult,
)


async def execute_tool_runtime_for_worker(
    *,
    runtime_gateway,
    tool: Tool,
    arguments: dict[str, Any],
    run_id: str,
    target: ToolExecutionTarget,
    worker_id: str | None,
    execution_context: ToolExecutionContext | None,
    manage_heartbeat: bool,
    heartbeat_context_factory: Callable[..., Any],
    artifact_service,
    details_max_chars: int,
) -> ToolRunResult:
    async def _execute() -> object:
        return await runtime_gateway.execute(
            tool,
            target,
            arguments,
            execution_context=execution_context,
        )

    if target.mode is ToolMode.BACKGROUND and worker_id is not None and manage_heartbeat:
        with heartbeat_context_factory(run_id=run_id, worker_id=worker_id):
            raw_result = await _execute()
    else:
        raw_result = await _execute()

    if not isinstance(raw_result, ToolRunResult):
        raise ToolValidationError(
            f"Tool runtime '{tool.resolved_runtime_key()}' must return ToolRunResult.",
        )
    result = externalize_tool_result_attachments(
        raw_result,
        run_id=run_id,
        tool=tool,
        artifact_service=artifact_service,
    )
    validate_tool_result_details(
        result,
        details_max_chars=details_max_chars,
    )
    return result


__all__ = ["execute_tool_runtime_for_worker"]
