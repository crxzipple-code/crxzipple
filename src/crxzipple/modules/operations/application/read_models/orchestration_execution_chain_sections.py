from __future__ import annotations

from datetime import datetime

from crxzipple.modules.dispatch.domain import DispatchTask
from crxzipple.modules.orchestration.application.ports import (
    OrchestrationRunQueryPort,
)
from crxzipple.modules.orchestration.domain import OrchestrationRun
from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableColumnModel,
    OperationsTableRowModel,
    OperationsTableSectionModel,
)
from crxzipple.modules.operations.application.read_models.orchestration_execution_chain_queries import (
    execution_chain_candidate_runs,
    safe_execution_chains,
)
from crxzipple.modules.operations.application.read_models.orchestration_execution_chain_rows import (
    execution_chain_row,
)


def execution_chain_section(
    run_query: OrchestrationRunQueryPort,
    runs: list[OrchestrationRun],
    *,
    dispatch_task_by_run_id: dict[str, DispatchTask],
    now: datetime,
) -> OperationsTableSectionModel:
    rows: list[OperationsTableRowModel] = []
    total_chains = 0
    for run in execution_chain_candidate_runs(runs, now=now):
        chains = safe_execution_chains(run_query, run.id)
        if not chains:
            continue
        total_chains += len(chains)
        for chain in sorted(chains, key=lambda item: item.updated_at, reverse=True)[:2]:
            rows.append(
                execution_chain_row(
                    run_query,
                    run,
                    chain,
                    dispatch_task=dispatch_task_by_run_id.get(run.id),
                    now=now,
                ),
            )
            if len(rows) >= 50:
                break
        if len(rows) >= 50:
            break
    return OperationsTableSectionModel(
        id="execution_chains",
        title="Execution Chains",
        columns=_columns(
            ("run_id", "Run ID"),
            ("chain_id", "Chain ID"),
            ("chain_status", "Chain Status"),
            ("active_step", "Active Step"),
            ("last_step", "Last Step"),
            ("steps", "Steps"),
            ("items", "Items"),
            ("continuation", "Continuation"),
            ("latest_decision", "Latest Decision"),
            ("tool_only_streak", "Tool-only"),
            ("dispatch_status", "Dispatch"),
            ("updated_at", "Updated At"),
            ("actions", "Actions"),
        ),
        rows=tuple(rows),
        total=total_chains,
        view_all_route="/operations/orchestration?tab=execution_chains",
        empty_state="No execution chains observed.",
    )


def _columns(*items: tuple[str, str]) -> tuple[OperationsTableColumnModel, ...]:
    return tuple(
        OperationsTableColumnModel(key=key, label=label) for key, label in items
    )
