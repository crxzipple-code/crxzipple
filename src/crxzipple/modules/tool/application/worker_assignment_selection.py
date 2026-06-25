from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Mapping

from crxzipple.modules.tool.application.concurrency import ToolRunConcurrencyPolicy
from crxzipple.modules.tool.domain.entities import Tool, ToolRun, ToolRunAssignment


def select_runnable_assignment_run_ids(
    assignments: list[ToolRunAssignment],
    *,
    runs_by_id: Mapping[str, ToolRun],
    active_counts: Counter[str],
    limit: int,
    concurrency_policy: ToolRunConcurrencyPolicy,
    resolve_tool_for_run: Callable[[ToolRun], Tool | None],
) -> tuple[str, ...]:
    assignments.sort(key=lambda assignment: assignment.assigned_at)
    selected: list[str] = []
    for assignment in assignments:
        run = runs_by_id.get(assignment.run_id)
        if run is None or run.is_terminal():
            continue
        tool = resolve_tool_for_run(run)
        if tool is None:
            continue
        if not concurrency_policy.can_start(
            run=run,
            tool=tool,
            active_counts=active_counts,
        ):
            continue
        concurrency_policy.reserve(
            run=run,
            tool=tool,
            active_counts=active_counts,
        )
        selected.append(assignment.run_id)
        if len(selected) >= limit:
            break
    return tuple(selected)


__all__ = ["select_runnable_assignment_run_ids"]
