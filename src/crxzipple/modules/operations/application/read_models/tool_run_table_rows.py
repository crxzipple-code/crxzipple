from __future__ import annotations

from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableColumnModel,
    OperationsTableRowModel,
)
from crxzipple.modules.operations.application.read_models.presenters import (
    display_value,
    title_label,
)
from crxzipple.modules.operations.application.read_models.tool_run_time import (
    tool_run_time,
)
from crxzipple.modules.operations.application.read_models.tool_run_table_facts import (
    ToolRunTableFacts,
)
from crxzipple.modules.tool.domain import ToolRun, ToolRunStatus
from crxzipple.shared.time import format_datetime_utc


def tool_run_row(
    run: ToolRun,
    *,
    facts: ToolRunTableFacts,
) -> OperationsTableRowModel:
    retryable = run.status in {ToolRunStatus.FAILED, ToolRunStatus.TIMED_OUT}
    return OperationsTableRowModel(
        id=run.id,
        cells={
            "time": format_datetime_utc(tool_run_time(run)),
            "tool": facts.tool_label,
            "tool_id": run.tool_id,
            "provider": facts.provider,
            "run_id": run.id,
            "call_id": display_value(run.call_id),
            "tool_surface_id": display_value(run.tool_surface_id),
            "source": facts.source,
            "orchestration_run_id": facts.orchestration_run_id,
            "chain_id": facts.chain_id,
            "step_id": facts.step_id,
            "browser": facts.browser,
            "status": status_label(run.status),
            "assignment_status": facts.assignment_status,
            "assignment_id": facts.assignment_id,
            "lease_state": facts.lease_state,
            "lease_expires_at": facts.lease_expires_at,
            "mode": run.target.mode.value,
            "strategy": run.target.strategy.value,
            "environment": run.target.environment.value,
            "worker": display_value(run.worker_id),
            "worker_id": display_value(run.worker_id),
            "duration": facts.duration,
            "progress": facts.progress,
            "result": facts.result,
            "has_artifact": "yes" if facts.has_artifact else "no",
            "retryable": "yes" if retryable else "no",
            "actions": tool_run_actions(run),
            "route": facts.route,
            "trace": facts.trace,
            "trace_route": facts.trace_route,
            "search_text": facts.search_text,
        },
        status=run.status.value,
        tone=tone_for_status(run.status),
    )


def tool_run_actions(run: ToolRun) -> str:
    if not run.is_terminal():
        return "Open / Trace / Cancel"
    if run.status in {ToolRunStatus.FAILED, ToolRunStatus.TIMED_OUT}:
        return "Open / Trace / Retry"
    return "Open / Trace"


def tone_for_status(status: ToolRunStatus) -> str:
    if status is ToolRunStatus.SUCCEEDED:
        return "success"
    if status in {ToolRunStatus.FAILED, ToolRunStatus.TIMED_OUT}:
        return "danger"
    if status in {ToolRunStatus.CANCEL_REQUESTED, ToolRunStatus.CANCELLED}:
        return "warning"
    if status in {ToolRunStatus.RUNNING, ToolRunStatus.DISPATCHING}:
        return "info"
    return "neutral"


def status_label(status: ToolRunStatus) -> str:
    return title_label(status.value)


def columns(*items: tuple[str, str]) -> tuple[OperationsTableColumnModel, ...]:
    return tuple(
        OperationsTableColumnModel(key=key, label=label)
        for key, label in items
    )
