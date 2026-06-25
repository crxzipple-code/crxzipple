from __future__ import annotations

from datetime import datetime

from crxzipple.modules.orchestration.domain import (
    OrchestrationIngressRequest,
    OrchestrationRun,
)
from crxzipple.modules.operations.application.read_models.models import (
    MetricCardModel,
)
from crxzipple.modules.operations.application.read_models.presenters import (
    health_delta,
    health_label,
    health_tone,
)
from crxzipple.shared.time import coerce_utc_datetime

_RECENT_FAILURE_HEALTH_SECONDS = 300


def health(
    *,
    queued_runs: list[OrchestrationRun],
    running_runs: list[OrchestrationRun],
    waiting_runs: list[OrchestrationRun],
    failed_runs: list[OrchestrationRun],
    available_executor_slots: int,
) -> str:
    if failed_runs:
        return "warning"
    if queued_runs and available_executor_slots <= 0:
        return "warning"
    if running_runs or queued_runs or waiting_runs:
        return "healthy"
    return "healthy"


def health_label_value(health: str) -> str:
    return health_label(health)


def health_delta_value(health: str) -> str:
    return health_delta(health, healthy="All systems operational")


def health_tone_value(health: str) -> str:
    return health_tone(health)


def failed_metric(
    *,
    failed_runs: list[OrchestrationRun],
    recent_failed_runs: list[OrchestrationRun],
    cancelled_runs: list[OrchestrationRun],
) -> MetricCardModel:
    retained_label = f"{len(failed_runs)} retained"
    if cancelled_runs:
        retained_label = f"{retained_label} / {len(cancelled_runs)} cancelled"
    return MetricCardModel(
        id="failed",
        label="Recent Failed",
        value=str(len(recent_failed_runs)),
        delta=retained_label,
        tone="danger" if recent_failed_runs else "neutral" if failed_runs else "success",
    )


def ingress_rate_label(
    ingress_requests: list[OrchestrationIngressRequest],
    *,
    fallback_runs: list[OrchestrationRun],
    now: datetime,
) -> str:
    recent_count = len(
        [
            request
            for request in ingress_requests
            if _age_seconds(request.created_at, now=now) <= 60
        ],
    ) + len(
        [
            run
            for run in fallback_runs
            if _age_seconds(run.created_at, now=now) <= 60
        ],
    )
    if recent_count == 0:
        return "0/s"
    rate = recent_count / 60
    return f"{rate:.1f}/s" if rate < 1 else f"{round(rate)}/s"


def average_latency_label(
    runs: list[OrchestrationRun],
    *,
    running_runs: list[OrchestrationRun],
    now: datetime,
) -> str:
    terminal_latencies = [
        max(
            int(
                (
                    coerce_utc_datetime(run.completed_at)
                    - coerce_utc_datetime(run.started_at or run.created_at)
                ).total_seconds(),
            ),
            0,
        )
        for run in runs
        if run.completed_at is not None
        and _age_seconds(run.completed_at, now=now) <= 86_400
    ]
    if terminal_latencies:
        return _duration_label(round(sum(terminal_latencies) / len(terminal_latencies)))

    running_latencies = [
        _age_seconds(run.started_at or run.created_at, now=now)
        for run in running_runs
    ]
    if running_latencies:
        return _duration_label(round(sum(running_latencies) / len(running_latencies)))
    return "0s"


def recent_failed_runs(
    failed_runs: list[OrchestrationRun],
    *,
    now: datetime,
) -> list[OrchestrationRun]:
    return [
        run
        for run in failed_runs
        if _age_seconds(run.completed_at or run.updated_at, now=now)
        <= _RECENT_FAILURE_HEALTH_SECONDS
    ]


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

