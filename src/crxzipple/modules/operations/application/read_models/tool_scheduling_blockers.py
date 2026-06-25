from __future__ import annotations

from collections import Counter
from datetime import datetime

from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableRowModel,
)
from crxzipple.modules.operations.application.read_models.presenters import (
    display_value,
    title_label,
)
from crxzipple.modules.operations.application.read_models.tool_run_time import (
    tool_run_time,
)
from crxzipple.modules.operations.application.read_models.tool_scheduling_capacity import (
    available_worker_count_for_group,
    concurrency_group_for_run,
)
from crxzipple.modules.operations.application.read_models.tool_scheduling_blocker_projection import (
    run_blocked_by_label,
    run_blocker_reason,
    run_blocker_tone,
    run_next_step_label,
)
from crxzipple.modules.operations.application.read_models.tool_scheduling_labels import (
    age_label,
    capability_label,
    retry_budget_label,
)
from crxzipple.modules.operations.application.read_models.tool_scheduling_run_projection import (
    assignment_id,
    assignment_status_label,
    lease_expires_label,
    lease_state_label,
    source_label,
    source_route,
    tool_label,
    trace_id,
    trace_route,
)
from crxzipple.modules.tool.application.concurrency import ToolRunConcurrencyPolicy
from crxzipple.modules.tool.domain import (
    Tool,
    ToolRun,
    ToolRunAssignment,
    ToolWorkerRegistration,
)
from crxzipple.shared.time import format_datetime_utc


def run_blocker_row(
    run: ToolRun,
    *,
    tools_by_id: dict[str, Tool],
    assignment: ToolRunAssignment | None,
    workers: list[ToolWorkerRegistration],
    worker_group_counts: dict[str, Counter[str]],
    concurrency_policy: ToolRunConcurrencyPolicy,
    now: datetime,
) -> OperationsTableRowModel:
    group = concurrency_group_for_run(
        run,
        tools_by_id=tools_by_id,
        concurrency_policy=concurrency_policy,
    )
    active = sum(counts[group.key] for counts in worker_group_counts.values())
    available_workers = available_worker_count_for_group(
        group,
        workers=workers,
        worker_group_counts=worker_group_counts,
        now=now,
    )
    reason = run_blocker_reason(
        run,
        assignment=assignment,
        workers=workers,
        worker_group_counts=worker_group_counts,
        tools_by_id=tools_by_id,
        concurrency_policy=concurrency_policy,
        now=now,
    )
    return OperationsTableRowModel(
        id=run.id,
        cells={
            "time": format_datetime_utc(tool_run_time(run)),
            "tool": tool_label(run, tools_by_id),
            "run_id": run.id,
            "source": source_label(run),
            "capability": capability_label(group.key),
            "capability_key": group.key,
            "status": title_label(run.status.value),
            "reason": reason,
            "assignment_status": assignment_status_label(assignment),
            "assignment_id": assignment_id(assignment),
            "lease_state": lease_state_label(run, assignment=assignment, now=now),
            "lease_expires_at": lease_expires_label(run, assignment=assignment),
            "retry_budget": retry_budget_label(run),
            "candidate_workers": str(available_workers),
            "blocked_by": run_blocked_by_label(
                reason,
                run=run,
                assignment=assignment,
            ),
            "next_step": run_next_step_label(
                reason,
                run=run,
                assignment=assignment,
                available_workers=available_workers,
            ),
            "active": str(active),
            "limit": f"{group.max_in_flight}/worker",
            "available_workers": str(available_workers),
            "mode": run.target.mode.value,
            "strategy": run.target.strategy.value,
            "worker": display_value(run.worker_id),
            "age": age_label(run.created_at, now=now),
            "actions": "Open / Trace / Cancel",
            "route": source_route(run),
            "trace": trace_id(run),
            "trace_route": trace_route(run),
        },
        status=run.status.value,
        tone=run_blocker_tone(reason, run.status),
    )
