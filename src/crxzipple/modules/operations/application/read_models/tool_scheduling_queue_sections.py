from __future__ import annotations

from datetime import datetime

from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableSectionModel,
)
from crxzipple.modules.operations.application.read_models.tool_scheduling_labels import (
    columns,
)
from crxzipple.modules.operations.application.read_models.tool_scheduling_queue_rows import (
    queue_summary_rows,
    waiting_io_rows,
)
from crxzipple.modules.operations.application.read_models.tool_scheduling_rows import (
    waiting_run_rows,
)
from crxzipple.modules.tool.application.concurrency import ToolRunConcurrencyPolicy
from crxzipple.modules.tool.domain import (
    Tool,
    ToolRun,
    ToolRunAssignment,
    ToolWorkerRegistration,
)


def tool_queue_section(
    queue_runs: list[ToolRun],
    *,
    active_runs: list[ToolRun],
    tools: list[Tool],
    workers: list[ToolWorkerRegistration],
    assignments: list[ToolRunAssignment],
    assignment_by_run: dict[str, ToolRunAssignment],
    concurrency_policy: ToolRunConcurrencyPolicy,
    now: datetime,
) -> OperationsTableSectionModel:
    rows = queue_summary_rows(
        queue_runs,
        active_runs=active_runs,
        tools=tools,
        workers=workers,
        assignments=assignments,
        assignment_by_run=assignment_by_run,
        concurrency_policy=concurrency_policy,
        now=now,
    )
    return OperationsTableSectionModel(
        id="tool_queue",
        title="Tool Queue",
        columns=columns(
            ("reason", "Reason"),
            ("count", "Count"),
            ("oldest", "Oldest Wait"),
            ("percent", "% of Queue"),
        ),
        rows=tuple(rows),
        total=len(queue_runs),
        view_all_route="/operations/tool?tab=queue",
        empty_state="No waiting tool runs.",
    )


def tool_queue_runs_section(
    queue_runs: list[ToolRun],
    *,
    active_runs: list[ToolRun],
    tools: list[Tool],
    workers: list[ToolWorkerRegistration],
    assignments: list[ToolRunAssignment],
    assignment_by_run: dict[str, ToolRunAssignment],
    concurrency_policy: ToolRunConcurrencyPolicy,
    now: datetime,
) -> OperationsTableSectionModel:
    rows = waiting_run_rows(
        queue_runs,
        active_runs=active_runs,
        tools=tools,
        workers=workers,
        assignments=assignments,
        assignment_by_run=assignment_by_run,
        concurrency_policy=concurrency_policy,
        now=now,
    )
    return OperationsTableSectionModel(
        id="tool_queue_runs",
        title="Queued Tool Runs",
        columns=columns(
            ("run_id", "Tool Run ID"),
            ("tool", "Tool"),
            ("source", "Source"),
            ("priority", "Priority"),
            ("wait_time", "Wait Time"),
            ("reason", "Reason"),
            ("actions", "Actions"),
        ),
        rows=rows,
        total=len(queue_runs),
        view_all_route="/operations/tool?tab=queue",
        empty_state="No waiting tool runs.",
    )


def tool_waiting_io_section(
    queue_runs: list[ToolRun],
    *,
    active_runs: list[ToolRun],
    tools: list[Tool],
    workers: list[ToolWorkerRegistration],
    assignments: list[ToolRunAssignment],
    assignment_by_run: dict[str, ToolRunAssignment],
    concurrency_policy: ToolRunConcurrencyPolicy,
    now: datetime,
) -> OperationsTableSectionModel:
    rows = waiting_io_rows(
        queue_runs,
        active_runs=active_runs,
        tools=tools,
        workers=workers,
        assignments=assignments,
        assignment_by_run=assignment_by_run,
        concurrency_policy=concurrency_policy,
        now=now,
    )
    return OperationsTableSectionModel(
        id="tool_waiting_io",
        title="Waiting IO",
        columns=columns(
            ("run_id", "Tool Run ID"),
            ("tool", "Tool"),
            ("source", "Source"),
            ("wait_time", "Wait Time"),
            ("external_service", "External Service"),
            ("timeout", "Timeout"),
            ("actions", "Actions"),
        ),
        rows=rows,
        total=len(rows),
        view_all_route="/operations/tool?tab=waiting_io",
        empty_state="No provider I/O waits.",
    )
