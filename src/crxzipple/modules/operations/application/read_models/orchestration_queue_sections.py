from __future__ import annotations

from datetime import datetime

from crxzipple.modules.dispatch.domain import DispatchTask
from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableColumnModel,
    OperationsTableSectionModel,
)
from crxzipple.modules.operations.application.read_models.orchestration_queue_rows import (
    run_queue_row,
)
from crxzipple.modules.orchestration.domain import OrchestrationRun


def run_queue_section(
    runs: list[OrchestrationRun],
    *,
    dispatch_task_by_run_id: dict[str, DispatchTask],
    now: datetime,
) -> OperationsTableSectionModel:
    sorted_runs = sorted(
        runs,
        key=lambda run: (run.priority, run.queued_at or run.created_at),
    )
    rows = tuple(
        run_queue_row(
            run,
            dispatch_task=dispatch_task_by_run_id.get(run.id),
            now=now,
        )
        for run in sorted_runs[:50]
    )
    return OperationsTableSectionModel(
        id="run_queue",
        title="Run Queue",
        columns=_columns(
            ("priority", "Priority"),
            ("run_id", "Run ID"),
            ("lane_key", "Lane Key"),
            ("enqueued_at", "Enqueued At"),
            ("agent_target", "Agent (Target)"),
            ("wait_reason", "Wait Reason"),
            ("dispatch_status", "Dispatch"),
            ("wait_time", "Wait Time"),
            ("actions", "Actions"),
        ),
        rows=rows,
        total=len(runs),
        view_all_route="/operations/orchestration?tab=runs",
        empty_state="Run queue is empty.",
    )

def _columns(*items: tuple[str, str]) -> tuple[OperationsTableColumnModel, ...]:
    return tuple(
        OperationsTableColumnModel(key=key, label=label) for key, label in items
    )
