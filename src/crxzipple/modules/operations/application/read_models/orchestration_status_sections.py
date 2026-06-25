from __future__ import annotations

from datetime import datetime
from typing import Any

from crxzipple.modules.dispatch.domain import DispatchTask
from crxzipple.modules.orchestration.application.coordinators.continuation_tasks import (
    OrchestrationContinuationStatus,
    OrchestrationContinuationTask,
)
from crxzipple.modules.orchestration.domain import (
    OrchestrationRun,
)
from crxzipple.modules.orchestration.domain.value_objects import (
    OrchestrationRunStatus,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsKeyValueItemModel,
    OperationsKeyValueSectionModel,
)
from crxzipple.modules.operations.application.read_models.orchestration_status_projection import (
    active_dispatch_tasks,
    age_label,
    age_seconds,
    continuation_latency_label,
    dispatch_task_breakdown,
    latest_datetime,
    latest_event_time,
    observation_cursor_label,
    observation_events_label,
    percent_label,
    queue_wait_p95,
)
from crxzipple.shared.time import format_datetime_utc


def scheduler_status_section(
    *,
    runs: list[OrchestrationRun],
    queued_runs: list[OrchestrationRun],
    continuation_tasks: list[OrchestrationContinuationTask],
    dispatch_tasks: list[DispatchTask],
    event_records: tuple[Any, ...],
    completed_count: int,
    failed_count: int,
    cancelled_count: int,
    available_executor_slots: int,
    observer_state: Any | None,
    now: datetime,
) -> OperationsKeyValueSectionModel:
    recent_terminal_runs = [
        run
        for run in runs
        if run.status
        in {
            OrchestrationRunStatus.COMPLETED,
            OrchestrationRunStatus.FAILED,
            OrchestrationRunStatus.CANCELLED,
        }
        and age_seconds(run.completed_at or run.updated_at, now=now) <= 300
    ]
    recent_completed_count = len(
        [
            run
            for run in recent_terminal_runs
            if run.status is OrchestrationRunStatus.COMPLETED
        ],
    )
    latest_update = latest_event_time(event_records) or latest_datetime(
        (
            *[run.updated_at for run in runs],
            *[task.updated_at for task in continuation_tasks],
        ),
    )
    queued_continuation_count = len(
        [
            task
            for task in continuation_tasks
            if task.status is OrchestrationContinuationStatus.QUEUED
        ],
    )
    processing_continuation_count = len(
        [
            task
            for task in continuation_tasks
            if task.status is OrchestrationContinuationStatus.PROCESSING
        ],
    )
    event_loop_value = "Observed" if latest_update else "No events"
    event_loop_tone = "success" if latest_update else "warning"
    if latest_update and age_seconds(latest_update, now=now) > 120:
        event_loop_value = "Stale"
        event_loop_tone = "warning"
    return OperationsKeyValueSectionModel(
        id="scheduler_status",
        title="Scheduler Status",
        items=(
            OperationsKeyValueItemModel(
                label="Event Loop",
                value=event_loop_value,
                tone=event_loop_tone,
            ),
            OperationsKeyValueItemModel(
                label="Last Tick",
                value=format_datetime_utc(latest_update) if latest_update else "-",
            ),
            OperationsKeyValueItemModel(
                label="Tick Lag",
                value=age_label(latest_update, now=now) if latest_update else "-",
            ),
            OperationsKeyValueItemModel(
                label="Dispatch Latency",
                value=continuation_latency_label(continuation_tasks),
            ),
            OperationsKeyValueItemModel(
                label="Queue Age (p95)",
                value=queue_wait_p95(queued_runs, now=now),
                tone="warning" if queued_runs else "success",
            ),
            OperationsKeyValueItemModel(
                label="Throughput (5m)",
                value=f"{len(recent_terminal_runs)} runs",
            ),
            OperationsKeyValueItemModel(
                label="Schedule Success Rate (5m)",
                value=percent_label(recent_completed_count, len(recent_terminal_runs)),
                tone=(
                    "success"
                    if recent_terminal_runs
                    and recent_completed_count == len(recent_terminal_runs)
                    else "warning"
                    if recent_terminal_runs
                    else "neutral"
                ),
            ),
            OperationsKeyValueItemModel(
                label="Continuation Tasks",
                value=(
                    f"{queued_continuation_count} queued / "
                    f"{processing_continuation_count} processing"
                ),
                tone="warning"
                if queued_continuation_count or processing_continuation_count
                else "success",
            ),
            OperationsKeyValueItemModel(
                label="Dispatch Tasks",
                value=dispatch_task_breakdown(dispatch_tasks),
                tone="warning" if active_dispatch_tasks(dispatch_tasks) else "success",
            ),
            OperationsKeyValueItemModel(
                label="Observed Cursor",
                value=observation_cursor_label(observer_state),
                tone="success" if observer_state is not None else "warning",
            ),
            OperationsKeyValueItemModel(
                label="Observed Entities",
                value=observation_events_label(observer_state),
                tone="info" if observer_state is not None else "neutral",
            ),
        ),
    )
