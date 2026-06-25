from __future__ import annotations

from dataclasses import dataclass

from crxzipple.modules.operations.application.read_models.presenters import (
    truncate_text,
)
from crxzipple.modules.tool.domain import (
    ToolEnvironment,
    ToolExecutionStrategy,
    ToolMode,
    ToolRun,
)


@dataclass(frozen=True, slots=True)
class ToolOperationsQuery:
    status: str = "all"
    time_window: str = "all"
    search: str = ""
    tool_id: str = "all"
    provider: str = "all"
    mode: str = "all"
    strategy: str = "all"
    environment: str = "all"
    worker_id: str = "all"
    has_artifact: str = "all"
    retryable: str = "all"
    limit: int = 50
    offset: int = 0


def normalize_tool_operations_query(
    query: ToolOperationsQuery | None,
) -> ToolOperationsQuery:
    if query is None:
        return ToolOperationsQuery()
    status = query.status.strip().lower() or "all"
    if status not in {
        "all",
        "active",
        "succeeded",
        "failed",
        "cancelled",
        "created",
        "queued",
        "dispatching",
        "running",
        "waiting",
        "long_running",
        "cancel_requested",
        "timed_out",
    }:
        status = "all"
    time_window = query.time_window.strip().lower() or "all"
    if time_window not in {"all", "24h"}:
        time_window = "all"
    mode = query.mode.strip().lower() or "all"
    if mode not in {"all", *(item.value for item in ToolMode)}:
        mode = "all"
    strategy = query.strategy.strip().lower() or "all"
    if strategy not in {"all", *(item.value for item in ToolExecutionStrategy)}:
        strategy = "all"
    environment = query.environment.strip().lower() or "all"
    if environment not in {"all", *(item.value for item in ToolEnvironment)}:
        environment = "all"
    has_artifact = query.has_artifact.strip().lower() or "all"
    if has_artifact not in {"all", "yes", "no"}:
        has_artifact = "all"
    retryable = query.retryable.strip().lower() or "all"
    if retryable not in {"all", "yes", "no"}:
        retryable = "all"
    return ToolOperationsQuery(
        status=status,
        time_window=time_window,
        search=truncate_text(query.search.strip(), 120),
        tool_id=_filter_value(query.tool_id),
        provider=_filter_value(query.provider).lower(),
        mode=mode,
        strategy=strategy,
        environment=environment,
        worker_id=_filter_value(query.worker_id),
        has_artifact=has_artifact,
        retryable=retryable,
        limit=max(1, min(query.limit, 200)),
        offset=max(0, query.offset),
    )


def paginate_tool_runs(
    runs: list[ToolRun],
    *,
    query: ToolOperationsQuery,
) -> list[ToolRun]:
    return runs[query.offset : query.offset + query.limit]


def tool_runs_empty_state(query: ToolOperationsQuery) -> str:
    if (
        query.status != "all"
        or query.time_window != "all"
        or query.search
        or query.tool_id != "all"
        or query.provider != "all"
        or query.mode != "all"
        or query.strategy != "all"
        or query.environment != "all"
        or query.worker_id != "all"
        or query.has_artifact != "all"
        or query.retryable != "all"
    ):
        return "No tool runs match the current filters."
    return "No tool runs recorded."


def _filter_value(value: str) -> str:
    normalized = value.strip()
    return normalized if normalized else "all"
