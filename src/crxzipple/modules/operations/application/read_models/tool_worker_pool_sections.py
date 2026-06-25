from __future__ import annotations

from collections import Counter
from datetime import datetime

from crxzipple.modules.operations.application.read_models.models import (
    OperationsChartSectionModel,
    OperationsChartSegmentModel,
)
from crxzipple.modules.operations.application.read_models.tool_worker_projection import (
    worker_registration_bucket,
    worker_registration_counts_in_pool,
)
from crxzipple.modules.operations.application.read_models.tool_worker_run_projection import (
    worker_run_bucket,
)
from crxzipple.modules.tool.domain import ToolRun, ToolWorkerRegistration


def worker_pool_section(
    workers: list[ToolWorkerRegistration],
    *,
    active_runs: list[ToolRun],
    now: datetime,
) -> OperationsChartSectionModel:
    counts: Counter[str] = Counter()
    if workers:
        current_workers = [
            worker
            for worker in workers
            if worker_registration_counts_in_pool(worker, now=now)
        ]
        for worker in current_workers:
            counts[worker_registration_bucket(worker, now=now)] += 1
        return _worker_pool_chart(
            title="Worker Pool by Current Registrations",
            total=len(current_workers),
            counts=counts,
            specs=(
                ("idle", "Idle", "success"),
                ("active", "Active", "info"),
                ("busy", "Busy", "warning"),
                ("stale", "Stale", "warning"),
                ("lease_expired", "Lease Expired", "danger"),
            ),
        )
    for run in active_runs:
        counts[worker_run_bucket(run, now=now)] += 1
    return _worker_pool_chart(
        title="Worker Pool by Active Runs",
        total=len(active_runs),
        counts=counts,
        specs=(
            ("queued", "Queued", "warning"),
            ("dispatching", "Dispatching", "info"),
            ("running", "Running", "success"),
            ("cancel_requested", "Cancel Requested", "warning"),
            ("lease_expired", "Lease Expired", "danger"),
            ("created", "Created", "neutral"),
        ),
    )


def _worker_pool_chart(
    *,
    title: str,
    total: int,
    counts: Counter[str],
    specs: tuple[tuple[str, str, str], ...],
) -> OperationsChartSectionModel:
    return OperationsChartSectionModel(
        id="worker_pool",
        title=title,
        kind="donut",
        total=total,
        segments=tuple(
            OperationsChartSegmentModel(
                id=item_id,
                label=label,
                value=counts[item_id],
                tone=tone,
            )
            for item_id, label, tone in specs
            if counts[item_id] > 0
        ),
    )
