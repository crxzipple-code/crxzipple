from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

from crxzipple.modules.dispatch.domain import DispatchTask, DispatchTaskStatus
from crxzipple.modules.orchestration.application.coordinators.continuation_tasks import (
    OrchestrationContinuationTask,
)
from crxzipple.modules.orchestration.domain import OrchestrationRun
from crxzipple.modules.operations.application.read_models.orchestration_event_log_rows import (
    event_record_time,
)
from crxzipple.modules.operations.application.read_models.presenters import (
    display_value,
)
from crxzipple.shared.time import coerce_utc_datetime


def latest_event_time(event_records: tuple[Any, ...]) -> datetime | None:
    timestamps = [event_record_time(record) for record in event_records]
    return max(timestamps, default=None)


def latest_datetime(values: tuple[datetime | None, ...]) -> datetime | None:
    timestamps = [
        coerce_utc_datetime(value)
        for value in values
        if isinstance(value, datetime)
    ]
    return max(timestamps, default=None)


def continuation_latency_label(
    continuation_tasks: list[OrchestrationContinuationTask],
) -> str:
    latencies = [
        age_seconds(task.created_at, now=task.completed_at)
        for task in continuation_tasks
        if task.completed_at is not None
    ]
    if not latencies:
        return "-"
    return f"p95 {duration_label(percentile(latencies, 0.95))}"


def queue_wait_p95(runs: list[OrchestrationRun], *, now: datetime) -> str:
    if not runs:
        return "0s"
    ages = [age_seconds(run.queued_at or run.created_at, now=now) for run in runs]
    return duration_label(percentile(ages, 0.95))


def percentile(values: list[int], percentile_value: float) -> int:
    if not values:
        return 0
    sorted_values = sorted(values)
    index = round((len(sorted_values) - 1) * percentile_value)
    return sorted_values[index]


def percent_label(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "-"
    return f"{round((numerator / denominator) * 100)}%"


def active_dispatch_tasks(tasks: list[DispatchTask]) -> list[DispatchTask]:
    return [task for task in tasks if is_active_dispatch_status(task.status)]


def is_active_dispatch_status(status: DispatchTaskStatus) -> bool:
    return status in {
        DispatchTaskStatus.QUEUED,
        DispatchTaskStatus.CLAIMED,
        DispatchTaskStatus.WAITING,
    }


def dispatch_task_breakdown(tasks: list[DispatchTask]) -> str:
    active_tasks = active_dispatch_tasks(tasks)
    if not active_tasks:
        return "0 active"
    by_kind: Counter[str] = Counter(task.owner_kind for task in active_tasks)
    return " / ".join(
        f"{count} {owner_kind}"
        for owner_kind, count in sorted(by_kind.items(), key=lambda item: item[0])
    )


def observation_cursor_label(observer_state: Any | None) -> str:
    if observer_state is None:
        return "-"
    return display(getattr(observer_state, "last_cursor", None))


def observation_events_label(observer_state: Any | None) -> str:
    if observer_state is None:
        return "-"
    event_count = int_from_attr(observer_state, "event_count")
    recent_count = len(getattr(observer_state, "recent_events", ()) or ())
    last_event_name = display(getattr(observer_state, "last_event_name", None))
    return f"{event_count} total / {recent_count} recent / last {last_event_name}"


def int_from_attr(value: Any, attr: str) -> int:
    raw = getattr(value, attr, 0)
    return raw if isinstance(raw, int) else 0


def age_seconds(value: datetime | None, *, now: datetime) -> int:
    if value is None:
        return 0
    return max(
        int((coerce_utc_datetime(now) - coerce_utc_datetime(value)).total_seconds()),
        0,
    )


def duration_label(seconds: int) -> str:
    seconds = max(seconds, 0)
    if seconds < 60:
        return f"{seconds}s"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {seconds}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m"


def age_label(value: datetime | None, *, now: datetime) -> str:
    if value is None:
        return "-"
    return duration_label(age_seconds(value, now=now))


def display(value: object | None) -> str:
    return display_value(value)
