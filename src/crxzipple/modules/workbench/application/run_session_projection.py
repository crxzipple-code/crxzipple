from __future__ import annotations

from crxzipple.modules.workbench.application import view_models as models
from crxzipple.modules.orchestration.application.ports import OrchestrationRunQueryPort
from crxzipple.modules.orchestration.domain import OrchestrationRun
from crxzipple.modules.workbench.application.projection_helpers import optional_text
from crxzipple.modules.workbench.application.run_identity_projection import turn_id
from crxzipple.modules.workbench.application.run_time_projection import (
    duration_ms,
)


def session_runs_for_run(
    run_query: OrchestrationRunQueryPort,
    run: OrchestrationRun,
    *,
    candidate_runs: list[OrchestrationRun] | None = None,
) -> tuple[OrchestrationRun, ...]:
    session_key = optional_text(run.session_key)
    if session_key is None:
        return (run,)
    runs = candidate_runs
    if runs is None:
        try:
            runs = run_query.list_runs()
        except Exception:
            return (run,)
    session_runs = [
        item
        for item in runs
        if optional_text(item.session_key) == session_key
    ]
    if not any(item.id == run.id for item in session_runs):
        session_runs.append(run)
    return tuple(
        sorted(
            session_runs,
            key=lambda item: (item.created_at, item.id),
        ),
    )


def turn_summaries(runs: tuple[OrchestrationRun, ...]):
    return tuple(
        models.TurnSummary(
            turn_id=turn_id(run),
            ordinal=index,
            status=run.status.value,
            duration_ms=duration_ms(run),
        )
        for index, run in enumerate(runs, start=1)
    )


def safe_list_runs(run_query: OrchestrationRunQueryPort) -> list[OrchestrationRun] | None:
    try:
        return run_query.list_runs()
    except Exception:
        return None


def safe_list_runs_for_session(
    run_query: OrchestrationRunQueryPort,
    session_key: str | None,
) -> list[OrchestrationRun] | None:
    normalized_session_key = optional_text(session_key)
    if normalized_session_key is None:
        return safe_list_runs(run_query)
    try:
        return run_query.list_runs(session_key=normalized_session_key)
    except TypeError:
        return safe_list_runs(run_query)
    except Exception:
        return None


__all__ = [
    "safe_list_runs",
    "safe_list_runs_for_session",
    "session_runs_for_run",
    "turn_summaries",
]
