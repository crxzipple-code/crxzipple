from __future__ import annotations

from datetime import datetime

from crxzipple.modules.dispatch.domain import DispatchTask
from crxzipple.modules.orchestration.domain import (
    OrchestrationExecutorLease,
    OrchestrationRun,
)
from crxzipple.shared.time import coerce_utc_datetime, format_datetime_utc


def executor_capabilities_label(lease: OrchestrationExecutorLease) -> str:
    metadata = lease.metadata if isinstance(lease.metadata, dict) else {}
    explicit = _metadata_string_list(metadata.get("capabilities"))
    if explicit:
        return ", ".join(explicit[:4])

    runtime_registry = metadata.get("runtime_registry")
    if isinstance(runtime_registry, dict):
        registry_capabilities = _metadata_string_list(
            runtime_registry.get("capabilities"),
        )
        if registry_capabilities:
            return ", ".join(registry_capabilities[:4])
        tool_names = _metadata_string_list(runtime_registry.get("tool_names"))
        if tool_names:
            return ", ".join(tool_names[:4])

    runtime_state = metadata.get("runtime_state")
    if isinstance(runtime_state, dict):
        active = runtime_state.get("max_concurrent_assignments")
        if active is not None:
            return f"slots:{active}"

    service_set = metadata.get("service_set")
    if isinstance(service_set, str) and service_set.strip():
        return service_set.strip()
    return f"slots:{lease.max_inflight_assignments}"


def queue_rows(
    runs: list[OrchestrationRun],
    *,
    dispatch_task_by_run_id: dict[str, DispatchTask],
    now: datetime,
) -> tuple[dict[str, str], ...]:
    sorted_runs = sorted(
        runs,
        key=lambda run: (run.priority, run.queued_at or run.created_at),
    )
    rows: list[dict[str, str]] = []
    for run in sorted_runs[:20]:
        dispatch_task = dispatch_task_by_run_id.get(run.id)
        queued_at = _dispatch_queued_at(dispatch_task) or run.queued_at or run.created_at
        rows.append(
            {
                "Priority": f"P{_dispatch_priority_label(dispatch_task, run.priority)}",
                "Run ID": run.id,
                "Lane Key": (
                    dispatch_task.lane_key
                    if dispatch_task is not None and dispatch_task.lane_key
                    else run.lane_key or "-"
                ),
                "Wait Reason": (
                    _dispatch_wait_reason(dispatch_task) or run.waiting_reason or "-"
                ),
                "Dispatch": (
                    dispatch_task.status.value if dispatch_task is not None else "-"
                ),
                "Wait Time": _age_label(queued_at, now=now),
            },
        )
    return tuple(rows)


def lane_lock_rows(
    runs: list[OrchestrationRun],
    *,
    now: datetime,
) -> tuple[dict[str, str], ...]:
    lock_runs = [run for run in runs if run.lane_lock_key]
    return tuple(
        {
            "Lane Key": run.lane_lock_key or run.lane_key or "-",
            "Holder Run ID": run.id,
            "TTL": "-",
            "Expires At": "-",
            "Reason": f"active {run.stage.value}",
        }
        for run in sorted(lock_runs, key=lambda item: item.updated_at, reverse=True)[
            :20
        ]
    )


def executor_rows(
    leases: list[OrchestrationExecutorLease],
    *,
    running_runs: list[OrchestrationRun],
    now: datetime,
) -> tuple[dict[str, str], ...]:
    current_run_by_worker = {
        run.worker_id: run.id
        for run in running_runs
        if run.worker_id is not None and run.worker_id.strip()
    }
    rows = []
    for lease in sorted(leases, key=lambda item: item.worker_id):
        capacity = max(lease.max_inflight_assignments, 1)
        load = round((lease.inflight_assignment_count / capacity) * 100)
        rows.append(
            {
                "Worker ID": lease.worker_id,
                "Status": lease.effective_status(now=now).value,
                "Last Heartbeat": format_datetime_utc(lease.last_heartbeat_at),
                "Current Run": current_run_by_worker.get(lease.worker_id, "-"),
                "Load": f"{load}%",
                "Running": str(lease.inflight_assignment_count),
                "Capacity": str(lease.max_inflight_assignments),
                "Capabilities": executor_capabilities_label(lease),
                "Actions": "Open",
            },
        )
    return tuple(rows[:20])


def _metadata_string_list(value: object | None) -> list[str]:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, (list, tuple, set)):
        return [text for item in value for text in (_optional_str(item),) if text]
    return []


def _optional_str(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _dispatch_queued_at(task: DispatchTask | None) -> datetime | None:
    if task is None:
        return None
    return task.queued_at or task.created_at


def _dispatch_wait_reason(task: DispatchTask | None) -> str | None:
    if task is None:
        return None
    if task.waiting_reason is not None and task.waiting_reason.strip():
        return task.waiting_reason.strip()
    return task.policy.value


def _dispatch_priority_label(task: DispatchTask | None, fallback: int) -> int:
    return task.priority if task is not None else fallback


def _age_seconds(value: datetime | None, *, now: datetime) -> int:
    if value is None:
        return 0
    return max(
        int((coerce_utc_datetime(now) - coerce_utc_datetime(value)).total_seconds()),
        0,
    )


def _duration_label(seconds: int) -> str:
    seconds = max(seconds, 0)
    if seconds < 60:
        return f"{seconds}s"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {seconds}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m"


def _age_label(value: datetime | None, *, now: datetime) -> str:
    if value is None:
        return "-"
    return _duration_label(_age_seconds(value, now=now))
