from __future__ import annotations

from datetime import datetime

from crxzipple.modules.operations.application.read_models.models import (
    OperationsKeyValueItemModel,
)
from crxzipple.modules.operations.application.read_models.tool_worker_projection import (
    worker_provider_summary,
    worker_registration_bucket,
    worker_registration_status,
    worker_runtime_count,
)
from crxzipple.modules.tool.domain import ToolRun, ToolWorkerRegistration
from crxzipple.shared.time import coerce_utc_datetime, format_datetime_utc


def tool_worker_detail_summary(
    worker: ToolWorkerRegistration,
    *,
    status: str,
    active_runs: list[ToolRun],
    now: datetime,
) -> tuple[OperationsKeyValueItemModel, ...]:
    current_runs = tuple(sorted(run.id for run in active_runs))
    return (
        OperationsKeyValueItemModel(label="Worker ID", value=worker.id),
        OperationsKeyValueItemModel(
            label="Status",
            value=status,
            tone=worker_registration_status(worker_registration_bucket(worker, now=now))[
                1
            ],
        ),
        OperationsKeyValueItemModel(
            label="Worker Load",
            value=f"{worker.current_in_flight}/{worker.max_in_flight}",
        ),
        OperationsKeyValueItemModel(
            label="Current Run",
            value=_join_values(list(current_runs)),
        ),
        OperationsKeyValueItemModel(
            label="Last Heartbeat",
            value=format_datetime_utc(worker.heartbeat_at),
        ),
        OperationsKeyValueItemModel(
            label="Lease Expires At",
            value=(
                format_datetime_utc(worker.lease_expires_at)
                if worker.lease_expires_at is not None
                else "-"
            ),
        ),
        OperationsKeyValueItemModel(
            label="Registered At",
            value=format_datetime_utc(worker.registered_at),
        ),
        OperationsKeyValueItemModel(
            label="Age",
            value=_age_label(worker.registered_at, now=now),
        ),
        OperationsKeyValueItemModel(
            label="Runtime Count",
            value=worker_runtime_count(worker),
        ),
        OperationsKeyValueItemModel(
            label="Providers",
            value=worker_provider_summary(worker),
        ),
    )


def _age_label(value: datetime | None, *, now: datetime) -> str:
    if value is None:
        return "-"
    seconds = max(
        int((coerce_utc_datetime(now) - coerce_utc_datetime(value)).total_seconds()),
        0,
    )
    return _duration_label(seconds)


def _duration_label(seconds: int) -> str:
    seconds = max(seconds, 0)
    if seconds < 60:
        return f"{seconds}s"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {seconds}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m"


def _join_values(values: tuple[str, ...] | list[str]) -> str:
    normalized = [value.strip() for value in values if value and value.strip()]
    return ", ".join(normalized) if normalized else "-"
