from __future__ import annotations

from crxzipple.modules.operations.application.read_models.models import (
    OperationsTabModel,
)


def page_tabs(
    *,
    queued_run_count: int,
    execution_chain_count: int,
    repeated_probe_count: int,
    lane_lock_count: int,
    executor_count: int,
    failed_run_count: int,
    has_recent_failures: bool,
) -> tuple[OperationsTabModel, ...]:
    return (
        OperationsTabModel(id="overview", label="Overview"),
        OperationsTabModel(id="runs", label="Runs", count=queued_run_count),
        OperationsTabModel(
            id="execution_chains",
            label="Execution",
            count=execution_chain_count,
        ),
        OperationsTabModel(
            id="repeated_probes",
            label="Repeated Probes",
            count=repeated_probe_count,
            tone="warning" if repeated_probe_count else "neutral",
        ),
        OperationsTabModel(
            id="lane_locks",
            label="Lane Locks",
            count=lane_lock_count,
        ),
        OperationsTabModel(
            id="executors",
            label="Executors",
            count=executor_count,
        ),
        OperationsTabModel(
            id="failures",
            label="Failures",
            count=failed_run_count,
            tone="danger" if has_recent_failures else "neutral",
        ),
        OperationsTabModel(id="events", label="Events"),
    )
