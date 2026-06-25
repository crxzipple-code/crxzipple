from __future__ import annotations

from datetime import datetime

from crxzipple.modules.dispatch.domain import DispatchTask
from crxzipple.modules.orchestration.application.ports import (
    OrchestrationRunQueryPort,
)
from crxzipple.modules.orchestration.domain import (
    ExecutionChain,
    ExecutionStep,
    OrchestrationRun,
)
from crxzipple.modules.orchestration.domain.value_objects import (
    ExecutionStepItemStatus,
    ExecutionStepStatus,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableRowModel,
)
from crxzipple.modules.operations.application.read_models.orchestration_execution_chain_row_values import (
    age_label,
    dispatch_worker,
    execution_item_breakdown,
    execution_step_breakdown,
    execution_step_label,
    tone_for_execution_chain_status,
    trace_id,
    trace_route,
    workbench_route,
)
from crxzipple.modules.operations.application.read_models.orchestration_execution_chain_diagnostics import (
    continuation_decision_count_label,
    continuation_decision_items,
    continuation_decision_label,
    latest_continuation_decision,
    llm_tool_only_streak_label,
    llm_tool_only_streaks,
)
from crxzipple.modules.operations.application.read_models.orchestration_execution_chain_queries import (
    safe_execution_step_items,
    safe_execution_steps,
)
from crxzipple.shared.time import format_datetime_utc


_ACTIVE_EXECUTION_ITEM_STATUSES = frozenset(
    {
        ExecutionStepItemStatus.CREATED,
        ExecutionStepItemStatus.RUNNING,
        ExecutionStepItemStatus.WAITING,
    },
)


def execution_chain_row(
    run_query: OrchestrationRunQueryPort,
    run: OrchestrationRun,
    chain: ExecutionChain,
    *,
    dispatch_task: DispatchTask | None,
    now: datetime,
) -> OperationsTableRowModel:
    steps = safe_execution_steps(run_query, chain.id)
    items_by_step_id = {
        step.id: tuple(safe_execution_step_items(run_query, step.id))
        for step in steps
    }
    items = [
        item
        for step in steps
        for item in items_by_step_id.get(step.id, ())
    ]
    active_step = _active_execution_step(chain, steps)
    last_step = max(steps, key=lambda item: item.step_index, default=None)
    active_item_count = len(
        [item for item in items if item.status in _ACTIVE_EXECUTION_ITEM_STATUSES],
    )
    continuation_items = continuation_decision_items(items)
    latest_continuation = latest_continuation_decision(continuation_items)
    tool_only_streaks = llm_tool_only_streaks(items_by_step_id, steps=steps)
    dispatch_status = (
        dispatch_task.status.value if dispatch_task is not None else run.status.value
    )
    return OperationsTableRowModel(
        id=f"{run.id}:{chain.id}",
        cells={
            "run_id": run.id,
            "chain_id": chain.id,
            "chain_status": chain.status.value,
            "active_step": execution_step_label(active_step),
            "last_step": execution_step_label(last_step),
            "steps": f"{len(steps)}",
            "items": f"{len(items)} / {active_item_count} active",
            "continuation": continuation_decision_count_label(continuation_items),
            "latest_decision": continuation_decision_label(latest_continuation),
            "tool_only_streak": llm_tool_only_streak_label(tool_only_streaks),
            "dispatch_status": dispatch_status,
            "dispatch_task_id": dispatch_task.id if dispatch_task is not None else "-",
            "dispatch_worker": dispatch_worker(dispatch_task),
            "updated_at": format_datetime_utc(chain.updated_at),
            "started_at": (
                format_datetime_utc(chain.started_at) if chain.started_at else "-"
            ),
            "completed_at": (
                format_datetime_utc(chain.completed_at) if chain.completed_at else "-"
            ),
            "age": age_label(chain.updated_at, now=now),
            "step_breakdown": execution_step_breakdown(steps),
            "item_breakdown": execution_item_breakdown(items),
            "active_step_id": chain.active_step_id or "-",
            "stage": run.stage.value,
            "trace": trace_id(run),
            "route": workbench_route(run),
            "trace_route": trace_route(run),
            "actions": "Open / Trace",
        },
        status=chain.status.value,
        tone=tone_for_execution_chain_status(chain.status),
    )


def _active_execution_step(
    chain: ExecutionChain,
    steps: list[ExecutionStep],
) -> ExecutionStep | None:
    if chain.active_step_id:
        for step in steps:
            if step.id == chain.active_step_id:
                return step
    for step in sorted(steps, key=lambda item: item.step_index):
        if step.status in {
            ExecutionStepStatus.CREATED,
            ExecutionStepStatus.RUNNING,
            ExecutionStepStatus.WAITING,
        }:
            return step
    return max(steps, key=lambda item: item.step_index, default=None)
