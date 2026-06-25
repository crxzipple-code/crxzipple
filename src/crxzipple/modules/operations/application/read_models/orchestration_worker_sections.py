from __future__ import annotations

from datetime import datetime

from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableColumnModel,
    OperationsTableSectionModel,
)
from crxzipple.modules.operations.application.read_models.orchestration_worker_rows import (
    executor_rows,
    lane_lock_rows,
)
from crxzipple.modules.orchestration.domain import (
    OrchestrationExecutorLease,
    OrchestrationRun,
)


def lane_locks_section(
    running_runs: list[OrchestrationRun],
    *,
    leases: list[OrchestrationExecutorLease],
    now: datetime,
) -> OperationsTableSectionModel:
    lock_runs = [run for run in running_runs if run.lane_lock_key]
    rows = lane_lock_rows(
        running_runs,
        leases=leases,
        now=now,
    )
    return OperationsTableSectionModel(
        id="lane_locks",
        title="Lane Locks",
        columns=_columns(
            ("lane_key", "Lane Key"),
            ("holder_run_id", "Holder Run ID"),
            ("type", "Type"),
            ("worker_id", "Worker ID"),
            ("duration", "Duration"),
            ("status", "Status"),
            ("progress", "Progress"),
            ("lock_epoch", "Lock Epoch"),
            ("ttl", "TTL"),
            ("expires_at", "Expires At"),
            ("renewed_at", "Renewed At"),
            ("reason", "Reason"),
            ("actions", "Actions"),
        ),
        rows=rows,
        total=len(lock_runs),
        view_all_route="/operations/orchestration?tab=lane_locks",
        empty_state="No active lane locks.",
    )


def executor_section(
    leases: list[OrchestrationExecutorLease],
    *,
    runs: list[OrchestrationRun],
    running_runs: list[OrchestrationRun],
    now: datetime,
) -> OperationsTableSectionModel:
    rows = executor_rows(
        leases,
        runs=runs,
        running_runs=running_runs,
        now=now,
    )
    return OperationsTableSectionModel(
        id="executor_overview",
        title="Executor Overview",
        columns=_columns(
            ("worker_id", "Worker ID"),
            ("status", "Status"),
            ("last_heartbeat", "Last Heartbeat"),
            ("lease_expires_at", "Lease (Expires At)"),
            ("current_run", "Current Run"),
            ("load", "Load (1m)"),
            ("running", "Running"),
            ("capacity", "Capacity"),
            ("capabilities", "Capabilities"),
            ("runs_5m", "Runs (5m)"),
            ("actions", "Actions"),
        ),
        rows=rows,
        total=len(leases),
        view_all_route="/operations/orchestration?tab=executors",
        empty_state="No executor leases registered.",
    )


def _columns(*items: tuple[str, str]) -> tuple[OperationsTableColumnModel, ...]:
    return tuple(
        OperationsTableColumnModel(key=key, label=label) for key, label in items
    )
