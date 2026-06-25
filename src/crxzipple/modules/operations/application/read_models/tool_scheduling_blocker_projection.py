from __future__ import annotations

from collections import Counter
from datetime import datetime

from crxzipple.modules.operations.application.read_models.presenters import (
    truncate_text,
)
from crxzipple.modules.operations.application.read_models.tool_scheduling_capacity import (
    concurrency_group_for_run,
    worker_can_start_group,
)
from crxzipple.modules.operations.application.read_models.tool_scheduling_labels import (
    run_reason,
)
from crxzipple.modules.operations.application.read_models.tool_scheduling_run_projection import (
    assignment_lease_expired,
)
from crxzipple.modules.operations.application.read_models.tool_worker_runtime import (
    online_workers,
)
from crxzipple.modules.tool.application.concurrency import ToolRunConcurrencyPolicy
from crxzipple.modules.tool.domain import (
    Tool,
    ToolMode,
    ToolRun,
    ToolRunAssignment,
    ToolRunAssignmentStatus,
    ToolRunStatus,
    ToolWorkerRegistration,
)


def run_blocker_reason(
    run: ToolRun,
    *,
    assignment: ToolRunAssignment | None,
    workers: list[ToolWorkerRegistration],
    worker_group_counts: dict[str, Counter[str]],
    tools_by_id: dict[str, Tool],
    concurrency_policy: ToolRunConcurrencyPolicy,
    now: datetime,
) -> str:
    if run.error_message:
        return truncate_text(run.error_message, 64)
    if assignment is not None and not assignment.is_terminal():
        if assignment_lease_expired(assignment, now=now):
            return "assignment lease expired"
        if assignment.status is ToolRunAssignmentStatus.ASSIGNED:
            return "assigned to worker"
        if assignment.status is ToolRunAssignmentStatus.RUNNING:
            return "running on worker"
    if run.target.mode.value == "inline":
        return "inline execution"

    online_worker_records = online_workers(workers, now=now)
    if not online_worker_records:
        return "waiting for online worker"
    if not any(
        worker.current_in_flight < worker.max_in_flight
        for worker in online_worker_records
    ):
        return "waiting for worker slot"

    group = concurrency_group_for_run(
        run,
        tools_by_id=tools_by_id,
        concurrency_policy=concurrency_policy,
    )
    if not any(
        worker_can_start_group(
            worker,
            group,
            worker_group_counts=worker_group_counts,
        )
        for worker in online_worker_records
    ):
        return "waiting for capability capacity"
    if run.status is ToolRunStatus.QUEUED:
        return "waiting for scheduler"
    if run.status is ToolRunStatus.CREATED:
        return "created"
    if run.status is ToolRunStatus.DISPATCHING:
        return "dispatching to worker"
    if run.status is ToolRunStatus.CANCEL_REQUESTED:
        return "cancel requested"
    return run_reason(run, assignment=assignment, now=now)


def run_blocked_by_label(
    reason: str,
    *,
    run: ToolRun,
    assignment: ToolRunAssignment | None,
) -> str:
    normalized = reason.lower()
    if run.error_message:
        return "error"
    if assignment is not None and not assignment.is_terminal():
        return f"worker:{assignment.worker_id}"
    if "online worker" in normalized:
        return "worker_pool"
    if "worker slot" in normalized:
        return "worker_capacity"
    if "capability capacity" in normalized:
        return "capability_limit"
    if "scheduler" in normalized or run.status is ToolRunStatus.QUEUED:
        return "scheduler"
    if run.target.mode is ToolMode.INLINE:
        return "inline_runtime"
    if run.status is ToolRunStatus.CANCEL_REQUESTED:
        return "cancellation"
    return "-"


def run_next_step_label(
    reason: str,
    *,
    run: ToolRun,
    assignment: ToolRunAssignment | None,
    available_workers: int,
) -> str:
    normalized = reason.lower()
    if run.error_message:
        return "inspect error"
    if assignment is not None and not assignment.is_terminal():
        if "expired" in normalized:
            return "recover expired assignment"
        if assignment.status is ToolRunAssignmentStatus.ASSIGNED:
            return "wait for worker start"
        return "monitor worker heartbeat"
    if "online worker" in normalized:
        return "start or recover worker"
    if "worker slot" in normalized or "capability capacity" in normalized:
        return "wait for capacity"
    if run.status is ToolRunStatus.QUEUED and available_workers > 0:
        return "scheduler dispatch"
    if run.status is ToolRunStatus.DISPATCHING:
        return "wait for assignment"
    if run.status is ToolRunStatus.CANCEL_REQUESTED:
        return "finish cancellation"
    if run.target.mode is ToolMode.INLINE:
        return "execute inline"
    return "monitor"


def run_blocker_tone(reason: str, status: ToolRunStatus) -> str:
    normalized = reason.lower()
    if "expired" in normalized or "missing" in normalized:
        return "danger"
    if "waiting" in normalized or status is ToolRunStatus.CANCEL_REQUESTED:
        return "warning"
    if status in {ToolRunStatus.RUNNING, ToolRunStatus.DISPATCHING}:
        return "info"
    return "neutral"
