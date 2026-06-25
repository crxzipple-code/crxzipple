from __future__ import annotations

from datetime import datetime

from crxzipple.modules.orchestration.application.ports import (
    OrchestrationRunQueryPort,
)
from crxzipple.modules.orchestration.domain import (
    ExecutionChain,
    ExecutionStep,
    ExecutionStepItem,
    OrchestrationRun,
)
from crxzipple.modules.orchestration.domain.value_objects import (
    OrchestrationRunStatus,
)
from crxzipple.shared.time import coerce_utc_datetime


def execution_chain_candidate_runs(
    runs: list[OrchestrationRun],
    *,
    now: datetime,
) -> list[OrchestrationRun]:
    selected: dict[str, OrchestrationRun] = {}
    active_statuses = {
        OrchestrationRunStatus.ACCEPTED,
        OrchestrationRunStatus.QUEUED,
        OrchestrationRunStatus.RUNNING,
        OrchestrationRunStatus.WAITING,
    }
    for run in sorted(runs, key=lambda item: item.updated_at, reverse=True):
        if run.status in active_statuses:
            selected[run.id] = run
    for run in sorted(runs, key=lambda item: item.updated_at, reverse=True):
        if len(selected) >= 30:
            break
        if run.id in selected:
            continue
        if _age_seconds(run.completed_at or run.updated_at, now=now) <= 900:
            selected[run.id] = run
    return list(selected.values())[:30]


def safe_execution_chains(
    run_query: OrchestrationRunQueryPort,
    run_id: str,
) -> list[ExecutionChain]:
    try:
        return run_query.list_execution_chains(run_id)
    except Exception:
        return []


def safe_execution_steps(
    run_query: OrchestrationRunQueryPort,
    chain_id: str,
) -> list[ExecutionStep]:
    try:
        return run_query.list_execution_steps(chain_id)
    except Exception:
        return []


def safe_execution_step_items(
    run_query: OrchestrationRunQueryPort,
    step_id: str,
) -> list[ExecutionStepItem]:
    try:
        return run_query.list_execution_step_items(step_id)
    except Exception:
        return []


def _age_seconds(value: datetime | None, *, now: datetime) -> int:
    if value is None:
        return 0
    return max(
        int((coerce_utc_datetime(now) - coerce_utc_datetime(value)).total_seconds()),
        0,
    )
