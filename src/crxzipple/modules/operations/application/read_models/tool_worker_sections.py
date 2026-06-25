from __future__ import annotations

from datetime import datetime

from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableColumnModel,
    OperationsTableRowModel,
    OperationsTableSectionModel,
)
from crxzipple.modules.operations.application.read_models.presenters import (
    display_value,
)
from crxzipple.modules.operations.application.read_models.tool_worker_projection import (
    worker_capability_summary,
    worker_provider_summary,
    worker_registration_bucket,
    worker_registration_status,
    worker_runtime_count,
)
from crxzipple.modules.operations.application.read_models.tool_worker_run_projection import (
    percent_label,
    worker_avg_duration_label,
    worker_run_lease_expires_label,
    worker_run_status_label,
    worker_run_tone,
    worker_success_rate_label,
)
from crxzipple.modules.tool.domain import (
    ToolRun,
    ToolRunAssignment,
    ToolWorkerRegistration,
)
from crxzipple.shared.time import format_datetime_utc


def workers_section(
    workers: list[ToolWorkerRegistration],
    *,
    active_runs: list[ToolRun],
    runs: list[ToolRun],
    assignment_by_run: dict[str, ToolRunAssignment],
    now: datetime,
) -> OperationsTableSectionModel:
    rows: list[OperationsTableRowModel] = []
    current_run_by_worker = {
        run.worker_id: run.id
        for run in active_runs
        if run.worker_id is not None and run.worker_id.strip()
    }

    if workers:
        for worker in sorted(workers, key=lambda item: item.id):
            bucket = worker_registration_bucket(worker, now=now)
            status, tone = worker_registration_status(bucket)
            rows.append(
                OperationsTableRowModel(
                    id=worker.id,
                    cells={
                        "worker": worker.id,
                        "status": status,
                        "last_heartbeat": format_datetime_utc(worker.heartbeat_at),
                        "lease_expires_at": (
                            format_datetime_utc(worker.lease_expires_at)
                            if worker.lease_expires_at is not None
                            else "-"
                        ),
                        "current_run": current_run_by_worker.get(worker.id, "-"),
                        "load": f"{worker.current_in_flight}/{worker.max_in_flight}",
                        "load_percent": percent_label(
                            worker.current_in_flight,
                            max(worker.max_in_flight, 1),
                        ),
                        "running": str(
                            sum(1 for run in active_runs if run.worker_id == worker.id),
                        ),
                        "success_rate": worker_success_rate_label(
                            worker.id,
                            runs=runs,
                        ),
                        "avg_duration": worker_avg_duration_label(
                            worker.id,
                            runs=runs,
                            assignment_by_run=assignment_by_run,
                            now=now,
                        ),
                        "runtimes": worker_runtime_count(worker),
                        "providers": worker_provider_summary(worker),
                        "capabilities": worker_capability_summary(worker),
                    },
                    status=status,
                    tone=tone,
                ),
            )
    else:
        for run in sorted(active_runs, key=lambda item: item.created_at, reverse=True):
            status = worker_run_status_label(run.status)
            rows.append(
                OperationsTableRowModel(
                    id=run.worker_id or run.id,
                    cells={
                        "worker": display_value(run.worker_id),
                        "status": status,
                        "last_heartbeat": (
                            format_datetime_utc(run.heartbeat_at)
                            if run.heartbeat_at is not None
                            else "-"
                        ),
                        "lease_expires_at": worker_run_lease_expires_label(run),
                        "current_run": run.id,
                        "load": "-",
                        "load_percent": "-",
                        "running": "1",
                        "success_rate": worker_success_rate_label(
                            run.worker_id or "",
                            runs=runs,
                        ),
                        "avg_duration": worker_avg_duration_label(
                            run.worker_id or "",
                            runs=runs,
                            assignment_by_run=assignment_by_run,
                            now=now,
                        ),
                        "runtimes": "-",
                        "providers": "-",
                        "capabilities": "-",
                    },
                    status=status,
                    tone=worker_run_tone(run.status),
                ),
            )

    return OperationsTableSectionModel(
        id="workers",
        title="Workers",
        columns=_columns(
            ("worker", "Worker ID"),
            ("status", "Status"),
            ("last_heartbeat", "Last Heartbeat"),
            ("lease_expires_at", "Lease Expires At"),
            ("current_run", "Current Run"),
            ("load", "Worker Load"),
            ("load_percent", "Load"),
            ("running", "Running"),
            ("success_rate", "Success Rate"),
            ("avg_duration", "Avg Duration"),
            ("runtimes", "Runtime Count"),
            ("providers", "Providers"),
            ("capabilities", "Capabilities"),
        ),
        rows=tuple(rows[:50]),
        total=len(rows),
        view_all_route="/operations/tool?tab=workers",
        empty_state="No tool workers registered.",
    )


def _columns(*items: tuple[str, str]) -> tuple[OperationsTableColumnModel, ...]:
    return tuple(
        OperationsTableColumnModel(key=key, label=label) for key, label in items
    )
