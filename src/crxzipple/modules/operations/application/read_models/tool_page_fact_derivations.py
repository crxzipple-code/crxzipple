from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from crxzipple.modules.operations.application.read_models.tool_page_run_selection import (
    dedupe_tool_page_runs,
)
from crxzipple.modules.operations.application.read_models.tool_run_time import (
    tool_run_duration_seconds,
)
from crxzipple.modules.tool.domain import (
    ToolRun,
    ToolRunAssignment,
    ToolRunStatus,
)


@dataclass(frozen=True, slots=True)
class ToolPageRunBuckets:
    active: list[ToolRun]
    running: list[ToolRun]
    waiting: list[ToolRun]
    failed: list[ToolRun]
    long_running_detail: list[ToolRun]


def tool_page_run_buckets(
    runs: list[ToolRun],
    *,
    assignment_by_run: dict[str, ToolRunAssignment],
    now: datetime,
    long_running_seconds: int,
) -> ToolPageRunBuckets:
    active_runs = [run for run in runs if not run.is_terminal()]
    running_runs = [run for run in active_runs if run.status is ToolRunStatus.RUNNING]
    running_run_ids = {run.id for run in running_runs}
    waiting_runs = [run for run in active_runs if run.id not in running_run_ids]
    failed_runs = [
        run
        for run in runs
        if run.status in {ToolRunStatus.FAILED, ToolRunStatus.TIMED_OUT}
    ]
    long_running_detail_runs = [
        run
        for run in active_runs
        if tool_run_duration_seconds(
            run,
            assignment=assignment_by_run.get(run.id),
            now=now,
        )
        >= long_running_seconds
    ]
    return ToolPageRunBuckets(
        active=active_runs,
        running=running_runs,
        waiting=waiting_runs,
        failed=failed_runs,
        long_running_detail=long_running_detail_runs,
    )


def tool_page_detail_runs(
    visible_tool_runs: list[ToolRun],
    buckets: ToolPageRunBuckets,
) -> list[ToolRun]:
    return dedupe_tool_page_runs(
        (
            *visible_tool_runs,
            *buckets.running,
            *buckets.waiting,
            *buckets.failed,
            *buckets.long_running_detail,
        ),
    )


def tool_page_owner_call_count(
    *,
    provider_backends: list[object],
    sources: list[object],
    run_query: object | None,
    operations_observation: object | None,
    events_service: object | None,
) -> int:
    return (
        7
        + len(provider_backends)
        + len(sources)
        + (1 if run_query is not None else 0)
        + (1 if operations_observation is not None else 0)
        + (1 if events_service is not None else 0)
    )
