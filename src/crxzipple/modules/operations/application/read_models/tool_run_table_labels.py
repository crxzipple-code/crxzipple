from __future__ import annotations

from typing import Mapping

from crxzipple.modules.operations.application.read_models.presenters import (
    display_value,
)
from crxzipple.modules.operations.application.read_models.tool_run_source_labels import (
    tool_run_source_label,
    tool_run_trace_id,
)
from crxzipple.modules.tool.domain import Tool, ToolRun


def tool_run_filter_search_text(
    run: ToolRun,
    *,
    tool: Tool | None,
    run_context: Mapping[str, str] | None = None,
) -> str:
    return " ".join(
        item
        for item in (
            run.id,
            run.tool_id,
            display_value(run.call_id),
            display_value(run.tool_surface_id),
            tool.name if tool is not None else "",
            display_value(run.worker_id),
            tool_run_source_label(run, run_context=run_context),
            tool_run_trace_id(run, run_context=run_context),
            display_value(run.error_message),
        )
        if item
    )


def tool_label(run: ToolRun, tools_by_id: dict[str, Tool]) -> str:
    tool = tools_by_id.get(run.tool_id)
    if tool is None:
        return run.tool_id
    return tool.id if tool.id == tool.name else f"{tool.name} ({tool.id})"
