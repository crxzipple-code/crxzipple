from __future__ import annotations

from crxzipple.modules.workbench.application import view_models as models
from dataclasses import dataclass

from crxzipple.modules.orchestration.application.ports import OrchestrationRunQueryPort
from crxzipple.modules.orchestration.domain import OrchestrationRun
from crxzipple.modules.orchestration.domain.value_objects import OrchestrationRunStatus
from crxzipple.modules.workbench.application.projection_helpers import (
    metadata_str,
    optional_text,
    truncate,
)
from crxzipple.modules.workbench.application.run_identity_projection import turn_id
from crxzipple.modules.workbench.application.run_text_projection import (
    output_text,
    run_title,
)
from crxzipple.shared.runtime_console import TraceContext
from crxzipple.shared.time import format_optional_datetime_utc


@dataclass(frozen=True, slots=True)
class WorkbenchThreadListProjector:
    run_query: OrchestrationRunQueryPort

    def project_home_view(
        self,
        *,
        run_id: str | None = None,
        session_key: str | None = None,
    ):
        latest_runs = latest_runs_by_session(self.run_query.list_runs())
        threads = tuple(
            thread_summary(run)
            for run in sorted(
                latest_runs.values(),
                key=lambda item: item.updated_at,
                reverse=True,
            )
        )
        active_run_id = active_run_id_for_threads(
            threads,
            requested_run_id=run_id,
            requested_session_key=session_key,
        )
        fallback_thread_id = (
            None
            if run_id is not None or session_key is not None
            else threads[0].id if threads else None
        )
        active_thread_id = next(
            (
                thread.id
                for thread in threads
                if thread.run_id == active_run_id
                or (
                    session_key is not None
                    and thread.session_key == session_key.strip()
                )
            ),
            fallback_thread_id,
        )
        latest_updated_at = threads[0].updated_at if threads else None
        return models.WorkbenchHomeView(
            connection=models.WorkbenchConnectionState(
                status="connected",
                label="Connected",
                updated_at=latest_updated_at,
                details="Workbench read model is using orchestration state.",
            ),
            filters=thread_filters(threads),
            threads=threads,
            active_thread_id=active_thread_id,
            active_run_id=active_run_id,
            actions=(
                {
                    "id": "new_task",
                    "label": "New task",
                    "owner": "orchestration",
                    "risk": "normal",
                    "allowed": True,
                    "requires_confirmation": False,
                    "reason_required": False,
                    "method": "POST",
                    "endpoint": "/turns",
                },
            ),
        )


def latest_runs_by_session(
    runs: list[OrchestrationRun],
) -> dict[str, OrchestrationRun]:
    latest: dict[str, OrchestrationRun] = {}
    for run in sorted(runs, key=lambda item: item.updated_at, reverse=True):
        session_key = optional_text(run.session_key)
        if session_key is None or session_key in latest:
            continue
        latest[session_key] = run
    return latest


def thread_summary(run: OrchestrationRun):
    session_key = optional_text(run.session_key) or run.id
    resolved_turn_id = turn_id(run)
    return models.WorkbenchThreadSummary(
        id=session_key,
        session_key=session_key,
        run_id=run.id,
        title=run_title(run),
        agent=run.agent_id or "Unknown Agent",
        status=run.status.value,
        current_activity=thread_activity(run),
        updated_at=format_optional_datetime_utc(run.updated_at) or "",
        starred=bool(run.metadata.get("starred")),
        trace=thread_trace_for_run(run, turn_id=resolved_turn_id),
    )


def active_run_id_for_threads(
    threads: tuple[object, ...],
    *,
    requested_run_id: str | None,
    requested_session_key: str | None,
) -> str | None:
    normalized_run_id = optional_text(requested_run_id)
    if normalized_run_id is not None:
        if any(getattr(thread, "run_id", None) == normalized_run_id for thread in threads):
            return normalized_run_id
        return normalized_run_id
    normalized_session_key = optional_text(requested_session_key)
    if normalized_session_key is not None:
        for thread in threads:
            if getattr(thread, "session_key", None) == normalized_session_key:
                return getattr(thread, "run_id", None)
    return getattr(threads[0], "run_id", None) if threads else None


def thread_filters(threads: tuple[object, ...]):
    running_statuses = {"accepted", "queued", "running", "waiting"}
    completed_statuses = {"completed", "success"}
    failed_statuses = {"failed", "cancelled"}
    return (
        models.WorkbenchFilterSummary(id="all", label="All", count=len(threads)),
        models.WorkbenchFilterSummary(
            id="running",
            label="Running",
            count=sum(
                1
                for thread in threads
                if getattr(thread, "status", None) in running_statuses
            ),
        ),
        models.WorkbenchFilterSummary(
            id="completed",
            label="Completed",
            count=sum(
                1
                for thread in threads
                if getattr(thread, "status", None) in completed_statuses
            ),
        ),
        models.WorkbenchFilterSummary(
            id="failed",
            label="Failed",
            count=sum(
                1
                for thread in threads
                if getattr(thread, "status", None) in failed_statuses
            ),
        ),
    )


def thread_activity(run: OrchestrationRun) -> str:
    if run.status is OrchestrationRunStatus.WAITING:
        return truncate(run.waiting_reason or "Waiting", limit=120)
    if run.status is OrchestrationRunStatus.QUEUED:
        return truncate(run.waiting_reason or "Queued for execution", limit=120)
    if run.status is OrchestrationRunStatus.RUNNING:
        return f"Running: {run.stage.value}"
    if run.status is OrchestrationRunStatus.ACCEPTED:
        return "Accepted"
    if run.status is OrchestrationRunStatus.COMPLETED:
        return truncate(output_text(run) or "Completed", limit=120)
    if run.status is OrchestrationRunStatus.FAILED:
        if run.error is not None and run.error.message:
            return truncate(run.error.message, limit=120)
        return "Failed"
    if run.status is OrchestrationRunStatus.CANCELLED:
        return "Cancelled"
    return run.status.value


def thread_trace_for_run(run: OrchestrationRun, *, turn_id: str) -> TraceContext:
    trace_id = metadata_str(run, "trace_id") or run.id
    return TraceContext(
        trace_id=trace_id,
        correlation_id=metadata_str(run, "correlation_id"),
        session_key=run.session_key,
        session_id=run.active_session_id,
        turn_id=turn_id,
        run_id=run.id,
    )
