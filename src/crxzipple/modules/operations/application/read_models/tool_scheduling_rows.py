from __future__ import annotations

from collections import Counter
from datetime import datetime

from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableRowModel,
)
from crxzipple.modules.operations.application.read_models.presenters import title_label
from crxzipple.modules.operations.application.read_models.tool_metric_values import (
    duration_label,
)
from crxzipple.modules.operations.application.read_models.tool_provider_identity import (
    provider_history_label,
    tool_provider_key,
)
from crxzipple.modules.operations.application.read_models.tool_scheduling_capacity import (
    available_worker_count_for_group,
    group_worker_capacity,
    worker_group_counts,
)
from crxzipple.modules.operations.application.read_models.tool_scheduling_blocker_projection import (
    run_blocker_reason,
)
from crxzipple.modules.operations.application.read_models.tool_scheduling_labels import (
    age_label,
    capability_label,
    queue_reason_tone,
    run_priority_label,
)
from crxzipple.modules.operations.application.read_models.tool_scheduling_run_projection import (
    source_label,
    source_route,
    tool_label,
    tool_lookup,
    trace_id,
    trace_route,
)
from crxzipple.modules.tool.application.concurrency import (
    ToolRunConcurrencyGroup,
    ToolRunConcurrencyPolicy,
)
from crxzipple.modules.tool.domain import (
    Tool,
    ToolRun,
    ToolRunAssignment,
    ToolWorkerRegistration,
)


def waiting_run_rows(
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
    rows: list[OperationsTableRowModel] = []
    for run in sorted(queue_runs, key=lambda item: item.created_at):
        tool = tools_by_id.get(run.tool_id)
        reason = run_blocker_reason(
            run,
            assignment=assignment_by_run.get(run.id),
            workers=workers,
            worker_group_counts=group_counts,
            tools_by_id=tools_by_id,
            concurrency_policy=concurrency_policy,
            now=now,
        )
        rows.append(
            OperationsTableRowModel(
                id=run.id,
                cells={
                    "run_id": run.id,
                    "tool": tool_label(run, tools_by_id),
                    "source": source_label(run),
                    "priority": run_priority_label(run),
                    "wait_time": age_label(run.created_at, now=now),
                    "reason": reason,
                    "external_service": provider_history_label(tool_provider_key(tool)),
                    "timeout": duration_label(tool.execution_policy.timeout_seconds)
                    if tool is not None
                    else "-",
                    "actions": "Open / Trace / Cancel",
                    "route": source_route(run),
                    "trace": trace_id(run),
                    "trace_route": trace_route(run),
                },
                status=reason,
                tone=queue_reason_tone(reason),
            ),
        )
    return tuple(rows[:50])


def capability_limit_row(
    *,
    group: ToolRunConcurrencyGroup,
    catalog_count: int,
    active: int,
    waiting: int,
    workers: list[ToolWorkerRegistration],
    worker_group_counts: dict[str, Counter[str]],
    now: datetime,
) -> OperationsTableRowModel:
    capacity = group_worker_capacity(group, workers=workers, now=now)
    available_workers = available_worker_count_for_group(
        group,
        workers=workers,
        worker_group_counts=worker_group_counts,
        now=now,
    )
    if waiting and capacity <= 0:
        state = "no worker"
        tone = "danger"
        reason = "waiting for online worker"
    elif waiting and available_workers <= 0:
        state = "saturated"
        tone = "warning"
        reason = "waiting for capability capacity"
    elif active:
        state = "active"
        tone = "info"
        reason = "capacity available" if available_workers else "worker slots full"
    else:
        state = "ready"
        tone = "success"
        reason = "capacity available" if capacity else "no online worker"
    return OperationsTableRowModel(
        id=group.key,
        cells={
            "capability": capability_label(group.key),
            "capability_key": group.key,
            "limit": f"{group.max_in_flight}/worker",
            "capacity": str(capacity),
            "active": str(active),
            "waiting": str(waiting),
            "available_workers": str(available_workers),
            "tools": str(catalog_count),
            "state": title_label(state),
            "reason": reason,
        },
        status=state,
        tone=tone,
    )
