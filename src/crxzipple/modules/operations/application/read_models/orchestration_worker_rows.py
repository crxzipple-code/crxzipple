from __future__ import annotations

from collections import Counter
from datetime import datetime

from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableRowModel,
)
from crxzipple.modules.operations.application.read_models.orchestration_overview_rows import (
    executor_capabilities_label,
)
from crxzipple.modules.operations.application.read_models.orchestration_worker_projection import (
    age_label,
    age_seconds,
    display,
    lane_lock_expires_label,
    lane_lock_renewed_at,
    lane_lock_ttl_label,
    run_progress_label,
    run_type_label,
    tone_for_executor_status,
    trace_id,
    trace_route,
    workbench_route,
)
from crxzipple.modules.orchestration.domain import (
    OrchestrationExecutorLease,
    OrchestrationRun,
)
from crxzipple.modules.orchestration.domain.value_objects import (
    OrchestrationRunStatus,
)
from crxzipple.shared.time import format_datetime_utc


def lane_lock_rows(
    running_runs: list[OrchestrationRun],
    *,
    leases: list[OrchestrationExecutorLease],
    now: datetime,
) -> tuple[OperationsTableRowModel, ...]:
    lock_runs = [run for run in running_runs if run.lane_lock_key]
    leases_by_worker = {lease.worker_id: lease for lease in leases}
    return tuple(
        OperationsTableRowModel(
            id=run.lane_lock_key or run.id,
            cells={
                "lane_key": run.lane_lock_key or run.lane_key or "-",
                "holder_run_id": run.id,
                "run_id": run.id,
                "type": run_type_label(run),
                "worker_id": display(run.worker_id),
                "duration": age_label(run.started_at or run.updated_at, now=now),
                "status": run.status.value,
                "progress": run_progress_label(run),
                "lock_epoch": str(run.current_step),
                "ttl": lane_lock_ttl_label(
                    leases_by_worker.get(run.worker_id or ""),
                    now=now,
                ),
                "expires_at": lane_lock_expires_label(
                    leases_by_worker.get(run.worker_id or ""),
                ),
                "renewed_at": format_datetime_utc(
                    lane_lock_renewed_at(
                        run,
                        leases_by_worker.get(run.worker_id or ""),
                    ),
                ),
                "reason": f"active {run.stage.value}",
                "held_for": age_label(run.started_at or run.updated_at, now=now),
                "stage": run.stage.value,
                "trace": trace_id(run),
                "route": workbench_route(run),
                "trace_route": trace_route(run),
                "actions": "Open / Trace",
            },
            status=run.status.value,
            tone="info",
        )
        for run in sorted(lock_runs, key=lambda item: item.updated_at, reverse=True)[
            :50
        ]
    )


def executor_rows(
    leases: list[OrchestrationExecutorLease],
    *,
    runs: list[OrchestrationRun],
    running_runs: list[OrchestrationRun],
    now: datetime,
) -> tuple[OperationsTableRowModel, ...]:
    current_run_by_worker = {
        run.worker_id: run.id
        for run in running_runs
        if run.worker_id is not None and run.worker_id.strip()
    }
    runs_5m_by_worker = _recent_terminal_runs_by_worker(runs, now=now)
    rows: list[OperationsTableRowModel] = []
    for lease in sorted(leases, key=lambda item: item.worker_id):
        capacity = max(lease.max_inflight_assignments, 1)
        load = round((lease.inflight_assignment_count / capacity) * 100)
        status = lease.effective_status(now=now).value
        rows.append(
            OperationsTableRowModel(
                id=lease.worker_id,
                cells={
                    "worker_id": lease.worker_id,
                    "status": status,
                    "last_heartbeat": format_datetime_utc(lease.last_heartbeat_at),
                    "lease_expires_at": (
                        format_datetime_utc(lease.lease_expires_at)
                        if lease.lease_expires_at
                        else "-"
                    ),
                    "current_run": current_run_by_worker.get(lease.worker_id, "-"),
                    "load": f"{load}%",
                    "running": str(lease.inflight_assignment_count),
                    "capacity": str(lease.max_inflight_assignments),
                    "available_slots": str(lease.available_assignment_slots(now=now)),
                    "capabilities": executor_capabilities_label(lease),
                    "runs_5m": str(runs_5m_by_worker[lease.worker_id]),
                    "actions": "Open",
                },
                status=status,
                tone=tone_for_executor_status(status),
            ),
        )
    return tuple(rows[:50])


def _recent_terminal_runs_by_worker(
    runs: list[OrchestrationRun],
    *,
    now: datetime,
) -> Counter[str]:
    runs_by_worker: Counter[str] = Counter()
    for run in runs:
        if run.worker_id is None or not run.worker_id.strip():
            continue
        if run.status not in {
            OrchestrationRunStatus.COMPLETED,
            OrchestrationRunStatus.FAILED,
            OrchestrationRunStatus.CANCELLED,
        }:
            continue
        if age_seconds(run.completed_at or run.updated_at, now=now) <= 300:
            runs_by_worker[run.worker_id] += 1
    return runs_by_worker
