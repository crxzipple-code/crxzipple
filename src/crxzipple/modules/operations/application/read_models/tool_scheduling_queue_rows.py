from __future__ import annotations

from datetime import datetime

from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableRowModel,
)
from crxzipple.modules.operations.application.read_models.tool_scheduling_blocker_projection import (
    run_blocker_reason,
)
from crxzipple.modules.operations.application.read_models.tool_scheduling_capacity import (
    worker_group_counts,
)
from crxzipple.modules.operations.application.read_models.tool_scheduling_labels import (
    age_label,
    is_waiting_io_reason,
    percent_label,
    queue_oldest_label,
    queue_reason_tone,
)
from crxzipple.modules.operations.application.read_models.tool_scheduling_rows import (
    waiting_run_rows,
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


def queue_summary_rows(
    queue_runs: list[ToolRun],
    *,
    active_runs: list[ToolRun],
    tools: list[Tool],
    workers: list[ToolWorkerRegistration],
    assignments: list[ToolRunAssignment],
    assignment_by_run: dict[str, ToolRunAssignment],
    concurrency_policy: ToolRunConcurrencyPolicy,
    now: datetime,
) -> tuple[OperationsTableRowModel, ...]:
    tools_by_id = tool_lookup(tools)
    group_counts, _ = worker_group_counts(
        runs=active_runs,
        assignments=assignments,
        tools_by_id=tools_by_id,
        concurrency_policy=concurrency_policy,
    )
    grouped: dict[str, list[ToolRun]] = {}
    for run in queue_runs:
        grouped.setdefault(
            run_blocker_reason(
                run,
                assignment=assignment_by_run.get(run.id),
                workers=workers,
                worker_group_counts=group_counts,
                tools_by_id=tools_by_id,
                concurrency_policy=concurrency_policy,
                now=now,
            ),
            [],
        ).append(run)

    total = len(queue_runs)
    rows: list[OperationsTableRowModel] = []
    for reason, reason_runs in sorted(
        grouped.items(),
        key=lambda item: (-len(item[1]), item[0]),
    ):
        oldest = min((run.created_at for run in reason_runs), default=None)
        rows.append(
            OperationsTableRowModel(
                id=reason,
                cells={
                    "reason": reason,
                    "count": str(len(reason_runs)),
                    "oldest": queue_oldest_label(
                        reason_runs,
                        assignment_by_run=assignment_by_run,
                        now=now,
                    )
                    if reason_runs
                    else age_label(oldest, now=now),
                    "percent": percent_label(len(reason_runs), total),
                },
                status=reason,
                tone=queue_reason_tone(reason),
            ),
        )
    return tuple(rows)


def waiting_io_rows(
    queue_runs: list[ToolRun],
    *,
    active_runs: list[ToolRun],
    tools: list[Tool],
    workers: list[ToolWorkerRegistration],
    assignments: list[ToolRunAssignment],
    assignment_by_run: dict[str, ToolRunAssignment],
    concurrency_policy: ToolRunConcurrencyPolicy,
    now: datetime,
) -> tuple[OperationsTableRowModel, ...]:
    return tuple(
        row
        for row in waiting_run_rows(
            queue_runs,
            active_runs=active_runs,
            tools=tools,
            workers=workers,
            assignments=assignments,
            assignment_by_run=assignment_by_run,
            concurrency_policy=concurrency_policy,
            now=now,
        )
        if is_waiting_io_reason(row.cells.get("reason", ""))
    )
