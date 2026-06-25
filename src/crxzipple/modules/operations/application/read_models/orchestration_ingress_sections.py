from __future__ import annotations

from datetime import datetime

from crxzipple.modules.dispatch.domain import DispatchTask
from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableSectionModel,
)
from crxzipple.modules.operations.application.read_models.orchestration_ingress_row_values import (
    columns,
)
from crxzipple.modules.operations.application.read_models.orchestration_ingress_rows import (
    fallback_run_row,
    ingress_request_row,
)
from crxzipple.modules.orchestration.domain import (
    OrchestrationIngressRequest,
    OrchestrationRun,
)


def ingress_queue_section(
    requests: list[OrchestrationIngressRequest],
    *,
    fallback_runs: list[OrchestrationRun],
    run_by_id: dict[str, OrchestrationRun],
    dispatch_task_by_request_id: dict[str, DispatchTask],
    now: datetime,
) -> OperationsTableSectionModel:
    fallback_rows = tuple(
        fallback_run_row(run, now=now)
        for run in sorted(fallback_runs, key=lambda item: item.created_at)[:50]
    )
    if requests:
        request_rows = tuple(
            ingress_request_row(
                request,
                run_by_id=run_by_id,
                dispatch_task=dispatch_task_by_request_id.get(request.id),
                now=now,
            )
            for request in sorted(requests, key=lambda item: item.created_at)[:50]
        )
        rows = request_rows + fallback_rows[: max(0, 50 - len(request_rows))]
        total = len(requests) + len(fallback_runs)
    else:
        rows = fallback_rows
        total = len(fallback_runs)
    return OperationsTableSectionModel(
        id="ingress_queue",
        title="Ingress Queue",
        columns=columns(
            ("source", "Source"),
            ("intake_key", "Intake Key"),
            ("received_at", "Received At"),
            ("target_lane", "Target Lane"),
            ("priority", "Priority"),
            ("status", "Status"),
            ("dispatch_worker", "Worker"),
            ("age", "Age"),
            ("actions", "Actions"),
        ),
        rows=rows,
        total=total,
        empty_state="Ingress queue is empty.",
    )
