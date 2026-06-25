from __future__ import annotations

from datetime import datetime, timedelta
from typing import Mapping

from crxzipple.modules.operations.application.read_models.presenters import (
    display_value,
)
from crxzipple.modules.operations.application.read_models.tool_run_query import (
    ToolOperationsQuery,
)
from crxzipple.modules.operations.application.read_models.tool_run_time import (
    tool_run_duration_seconds,
    tool_run_time,
)
from crxzipple.modules.tool.domain import (
    ToolRun,
    ToolRunAssignment,
    ToolRunStatus,
)


def filter_tool_runs(
    runs: list[ToolRun],
    *,
    query: ToolOperationsQuery,
    assignment_by_run: Mapping[str, ToolRunAssignment],
    provider_key_by_tool_id: Mapping[str, str],
    artifact_run_ids: set[str],
    search_text_by_run_id: Mapping[str, str],
    now: datetime,
    long_running_seconds: int,
) -> list[ToolRun]:
    filtered = [
        run
        for run in runs
        if _tool_run_matches_status(
            run,
            query.status,
            assignment=assignment_by_run.get(run.id),
            now=now,
            long_running_seconds=long_running_seconds,
        )
        and _tool_run_matches_filters(
            run,
            query=query,
            provider_key_by_tool_id=provider_key_by_tool_id,
            artifact_run_ids=artifact_run_ids,
            search_text_by_run_id=search_text_by_run_id,
        )
    ]
    if query.time_window == "24h":
        cutoff = now - timedelta(hours=24)
        filtered = [run for run in filtered if tool_run_time(run) >= cutoff]
    return sorted(filtered, key=tool_run_time, reverse=True)


def dedupe_tool_runs(runs: tuple[ToolRun, ...]) -> list[ToolRun]:
    seen: set[str] = set()
    unique: list[ToolRun] = []
    for run in runs:
        if run.id in seen:
            continue
        seen.add(run.id)
        unique.append(run)
    return unique


def _tool_run_matches_status(
    run: ToolRun,
    status: str,
    *,
    assignment: ToolRunAssignment | None,
    now: datetime,
    long_running_seconds: int,
) -> bool:
    if status == "all":
        return True
    if status == "active":
        return not run.is_terminal()
    if status == "waiting":
        return not run.is_terminal() and run.status is not ToolRunStatus.RUNNING
    if status == "long_running":
        return (
            not run.is_terminal()
            and tool_run_duration_seconds(run, assignment=assignment, now=now)
            >= long_running_seconds
        )
    if status == "succeeded":
        return run.status is ToolRunStatus.SUCCEEDED
    if status == "failed":
        return run.status in {ToolRunStatus.FAILED, ToolRunStatus.TIMED_OUT}
    if status == "cancelled":
        return run.status in {
            ToolRunStatus.CANCELLED,
            ToolRunStatus.CANCEL_REQUESTED,
        }
    return run.status.value == status


def _tool_run_matches_filters(
    run: ToolRun,
    *,
    query: ToolOperationsQuery,
    provider_key_by_tool_id: Mapping[str, str],
    artifact_run_ids: set[str],
    search_text_by_run_id: Mapping[str, str],
) -> bool:
    if query.tool_id != "all" and query.tool_id != run.tool_id:
        return False
    provider_key = provider_key_by_tool_id.get(run.tool_id, "unknown")
    if query.provider != "all" and query.provider != provider_key.lower():
        return False
    if query.mode != "all" and query.mode != run.target.mode.value:
        return False
    if query.strategy != "all" and query.strategy != run.target.strategy.value:
        return False
    if query.environment != "all" and query.environment != run.target.environment.value:
        return False
    if query.worker_id != "all" and query.worker_id != display_value(run.worker_id):
        return False
    has_artifact = run.id in artifact_run_ids
    if query.has_artifact == "yes" and not has_artifact:
        return False
    if query.has_artifact == "no" and has_artifact:
        return False
    is_retryable = run.status in {ToolRunStatus.FAILED, ToolRunStatus.TIMED_OUT}
    if query.retryable == "yes" and not is_retryable:
        return False
    if query.retryable == "no" and is_retryable:
        return False
    if query.search and not _tool_run_matches_search(
        search_text_by_run_id.get(run.id, ""),
        query.search,
    ):
        return False
    return True


def _tool_run_matches_search(search_text: str, search: str) -> bool:
    needle = search.strip().lower()
    if not needle:
        return True
    return needle in search_text.lower()
