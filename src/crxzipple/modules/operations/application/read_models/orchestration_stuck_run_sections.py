from __future__ import annotations

from datetime import datetime

from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableColumnModel,
    OperationsTableRowModel,
    OperationsTableSectionModel,
)
from crxzipple.modules.orchestration.domain import OrchestrationRun
from crxzipple.modules.orchestration.domain.value_objects import OrchestrationRunStage
from crxzipple.shared.time import coerce_utc_datetime


def stuck_runs_section(
    *,
    queued_runs: list[OrchestrationRun],
    running_runs: list[OrchestrationRun],
    waiting_runs: list[OrchestrationRun],
    now: datetime,
) -> OperationsTableSectionModel:
    queued_stuck = [
        run
        for run in queued_runs
        if _age_seconds(run.queued_at or run.created_at, now=now) >= 300
    ]
    running_stale = [
        run for run in running_runs if _age_seconds(run.updated_at, now=now) >= 600
    ]
    waiting_approval = [
        run
        for run in waiting_runs
        if run.stage is OrchestrationRunStage.WAITING_FOR_CONFIRMATION
    ]
    waiting_tools = [
        run
        for run in waiting_runs
        if run.stage is OrchestrationRunStage.WAITING_ON_TOOL
        or bool(run.pending_tool_run_ids)
    ]
    buckets = (
        (
            "queued_over_5m",
            "Queued > 5m",
            queued_stuck,
            "Inspect queue policy",
            "warning",
            tuple(run.queued_at or run.created_at for run in queued_stuck),
        ),
        (
            "running_stale",
            "Running stale > 10m",
            running_stale,
            "Open trace",
            "danger",
            tuple(run.updated_at for run in running_stale),
        ),
        (
            "waiting_approval",
            "Waiting approval",
            waiting_approval,
            "Resolve approval",
            "warning",
            tuple(run.updated_at for run in waiting_approval),
        ),
        (
            "waiting_tools",
            "Waiting tool",
            waiting_tools,
            "Inspect tool run",
            "info",
            tuple(run.updated_at for run in waiting_tools),
        ),
    )
    rows = []
    for row_id, issue, bucket_runs, action, tone, timestamps in buckets:
        if not bucket_runs:
            continue
        first_run = sorted(bucket_runs, key=lambda run: run.updated_at, reverse=True)[0]
        approval = first_run.pending_approval_request()
        rows.append(
            OperationsTableRowModel(
                id=row_id,
                cells={
                    "issue": issue,
                    "count": str(len(bucket_runs)),
                    "oldest": _max_age_label(timestamps, now=now),
                    "action": "View",
                    "recommended_action": action,
                    "example_run_id": first_run.id,
                    "approval_request_id": (
                        approval.request_id if approval is not None else "-"
                    ),
                    "approval_effect_id": (
                        approval.effect_id if approval is not None else "-"
                    ),
                    "approval_label": approval.label if approval is not None else "-",
                    "route": _workbench_route(first_run),
                },
                status=row_id,
                tone=tone,
            ),
        )
    return OperationsTableSectionModel(
        id="stuck_runs",
        title="Stuck Runs",
        columns=_columns(
            ("issue", "Issue"),
            ("count", "Count"),
            ("action", "Action"),
        ),
        rows=tuple(rows),
        total=len(rows),
        empty_state="No stuck runs detected.",
    )


def _columns(*items: tuple[str, str]) -> tuple[OperationsTableColumnModel, ...]:
    return tuple(
        OperationsTableColumnModel(key=key, label=label) for key, label in items
    )


def _workbench_route(run: OrchestrationRun) -> str:
    return f"/ui/workbench/runs/{run.id}"


def _max_age_label(
    values: tuple[datetime | None, ...],
    *,
    now: datetime,
) -> str:
    ages = [_age_seconds(value, now=now) for value in values if value is not None]
    if not ages:
        return "-"
    return _duration_label(max(ages))


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
