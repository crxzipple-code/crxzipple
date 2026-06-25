from __future__ import annotations

from datetime import datetime

from crxzipple.modules.dispatch.domain import DispatchTask
from crxzipple.modules.orchestration.domain import OrchestrationRun
from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableRowModel,
)
from crxzipple.modules.operations.application.read_models.orchestration_queue_row_values import (
    age_label,
    dispatch_lease_expires_at,
    dispatch_priority_label,
    dispatch_queued_at,
    dispatch_wait_reason,
    dispatch_worker,
    display,
    run_wait_reason,
    tone_for_dispatch_or_run_status,
    trace_id,
    trace_route,
    workbench_route,
)
from crxzipple.shared.time import format_datetime_utc


def run_queue_row(
    run: OrchestrationRun,
    *,
    dispatch_task: DispatchTask | None,
    now: datetime,
) -> OperationsTableRowModel:
    queued_at = dispatch_queued_at(dispatch_task) or run.queued_at or run.created_at
    status = dispatch_task.status.value if dispatch_task is not None else run.status.value
    return OperationsTableRowModel(
        id=run.id,
        cells={
            "priority": f"P{dispatch_priority_label(dispatch_task, run.priority)}",
            "run_id": run.id,
            "lane_key": display(
                dispatch_task.lane_key if dispatch_task is not None else run.lane_key,
            ),
            "enqueued_at": format_datetime_utc(queued_at),
            "agent_target": display(run.agent_id),
            "wait_reason": dispatch_wait_reason(dispatch_task) or run_wait_reason(run),
            "wait_time": age_label(queued_at, now=now),
            "dispatch_status": status,
            "dispatch_task_id": dispatch_task.id if dispatch_task is not None else "-",
            "dispatch_owner_kind": (
                dispatch_task.owner_kind if dispatch_task is not None else "-"
            ),
            "dispatch_worker": dispatch_worker(dispatch_task),
            "dispatch_lease_expires_at": dispatch_lease_expires_at(dispatch_task),
            "actions": "Open / Trace / Cancel / Requeue",
            "policy": (
                dispatch_task.policy.value
                if dispatch_task is not None
                else run.queue_policy.value
            ),
            "stage": run.stage.value,
            "trace": trace_id(run),
            "route": workbench_route(run),
            "trace_route": trace_route(run),
        },
        status=status,
        tone=tone_for_dispatch_or_run_status(dispatch_task, run.status),
    )
