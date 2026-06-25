from __future__ import annotations

from datetime import datetime

from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableSectionModel,
)
from crxzipple.modules.operations.application.read_models.tool_run_time import (
    tool_run_time,
)
from crxzipple.modules.operations.application.read_models.tool_scheduling_blockers import (
    run_blocker_row,
)
from crxzipple.modules.operations.application.read_models.tool_scheduling_capacity import (
    worker_group_counts,
)
from crxzipple.modules.operations.application.read_models.tool_scheduling_labels import (
    columns,
)
from crxzipple.modules.operations.application.read_models.tool_scheduling_run_projection import (
    tool_lookup,
)
from crxzipple.modules.tool.application.concurrency import ToolRunConcurrencyPolicy
from crxzipple.modules.tool.domain import (
    Tool,
    ToolRun,
    ToolRunAssignment,
    ToolWorkerRegistration,
)


def run_blockers_section(
    active_runs: list[ToolRun],
    *,
    tools: list[Tool],
    workers: list[ToolWorkerRegistration],
    assignments: list[ToolRunAssignment],
    assignment_by_run: dict[str, ToolRunAssignment],
    concurrency_policy: ToolRunConcurrencyPolicy,
    now: datetime,
) -> OperationsTableSectionModel:
    tools_by_id = tool_lookup(tools)
    group_counts, _ = worker_group_counts(
        runs=active_runs,
        assignments=assignments,
        tools_by_id=tools_by_id,
        concurrency_policy=concurrency_policy,
    )
    rows = tuple(
        run_blocker_row(
            run,
            tools_by_id=tools_by_id,
            assignment=assignment_by_run.get(run.id),
            workers=workers,
            worker_group_counts=group_counts,
            concurrency_policy=concurrency_policy,
            now=now,
        )
        for run in sorted(active_runs, key=tool_run_time, reverse=True)[:50]
    )
    return OperationsTableSectionModel(
        id="run_blockers",
        title="Run Scheduling Diagnostics",
        columns=columns(
            ("time", "Time"),
            ("tool", "Tool"),
            ("run_id", "Run ID"),
            ("capability", "Capability"),
            ("status", "Status"),
            ("reason", "Reason"),
            ("assignment_status", "Assignment"),
            ("lease_state", "Lease"),
            ("retry_budget", "Retry Budget"),
            ("candidate_workers", "Candidate Workers"),
            ("blocked_by", "Blocked By"),
            ("next_step", "Next Step"),
            ("active", "Active"),
            ("limit", "Limit"),
            ("available_workers", "Available Workers"),
            ("worker", "Worker ID"),
            ("age", "Age"),
            ("actions", "Actions"),
        ),
        rows=rows,
        total=len(active_runs),
        view_all_route="/operations/tool?tab=diagnostics",
        empty_state="No active tool runs need scheduling diagnostics.",
    )
