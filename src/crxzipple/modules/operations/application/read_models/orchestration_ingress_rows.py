from __future__ import annotations

from datetime import datetime

from crxzipple.modules.dispatch.domain import DispatchTask
from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableRowModel,
)
from crxzipple.modules.operations.application.read_models.orchestration_ingress_projection import (
    ingress_priority,
    ingress_source,
    ingress_target_lane,
)
from crxzipple.modules.operations.application.read_models.orchestration_ingress_row_values import (
    age_label,
    dispatch_lease_expires_at,
    dispatch_queued_at,
    dispatch_worker,
    display,
    run_summary,
    tone_for_dispatch_or_ingress_status,
    tone_for_run_status,
    trace_id,
    trace_route,
    trace_route_from_id,
    workbench_route,
)
from crxzipple.modules.orchestration.domain import (
    OrchestrationIngressRequest,
    OrchestrationRun,
)
from crxzipple.shared.time import format_datetime_utc


def fallback_run_row(run: OrchestrationRun, *, now: datetime) -> OperationsTableRowModel:
    return OperationsTableRowModel(
        id=run.id,
        cells={
            "source": run.inbound_instruction.source,
            "intake_key": run.id,
            "received_at": format_datetime_utc(run.created_at),
            "target_lane": display(run.lane_key),
            "priority": f"P{run.priority}",
            "age": age_label(run.created_at, now=now),
            "actions": "Open",
            "status": run.status.value,
            "run_id": run.id,
            "session_key": display(run.session_key),
            "summary": run_summary(run),
            "trace": trace_id(run),
            "route": workbench_route(run),
            "trace_route": trace_route(run),
        },
        status=run.status.value,
        tone=tone_for_run_status(run.status),
    )


def ingress_request_row(
    request: OrchestrationIngressRequest,
    *,
    run_by_id: dict[str, OrchestrationRun],
    dispatch_task: DispatchTask | None,
    now: datetime,
) -> OperationsTableRowModel:
    run = run_by_id.get(request.run_id)
    row_trace_id = trace_id(run) if run is not None else request.run_id
    received_at = dispatch_queued_at(dispatch_task) or request.created_at
    status = (
        dispatch_task.status.value if dispatch_task is not None else request.status.value
    )
    return OperationsTableRowModel(
        id=request.id,
        cells={
            "source": ingress_source(request, run),
            "intake_key": request.id,
            "received_at": format_datetime_utc(received_at),
            "target_lane": ingress_target_lane(request, run),
            "priority": ingress_priority(request, run, dispatch_task=dispatch_task),
            "age": age_label(received_at, now=now),
            "actions": "Open",
            "status": status,
            "request_status": request.status.value,
            "dispatch_status": status,
            "dispatch_task_id": dispatch_task.id if dispatch_task is not None else "-",
            "dispatch_owner_kind": (
                dispatch_task.owner_kind if dispatch_task is not None else "-"
            ),
            "dispatch_worker": dispatch_worker(dispatch_task),
            "dispatch_lease_expires_at": dispatch_lease_expires_at(dispatch_task),
            "kind": request.kind.value,
            "worker_id": display(request.worker_id),
            "run_id": request.run_id,
            "session_key": display(run.session_key if run is not None else None),
            "summary": run_summary(run) if run is not None else request.kind.value,
            "trace": row_trace_id,
            "route": f"/ui/workbench/runs/{request.run_id}",
            "trace_route": trace_route_from_id(row_trace_id),
        },
        status=status,
        tone=tone_for_dispatch_or_ingress_status(dispatch_task, request.status),
    )
