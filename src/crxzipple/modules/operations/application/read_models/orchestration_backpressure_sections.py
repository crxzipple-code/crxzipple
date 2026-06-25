from __future__ import annotations

from collections import Counter
from crxzipple.modules.operations.application.read_models.models import (
    OperationsChartSectionModel,
    OperationsChartSegmentModel,
)
from crxzipple.modules.orchestration.domain import OrchestrationRun
from crxzipple.modules.orchestration.domain.value_objects import (
    OrchestrationRunStage,
    OrchestrationRunStatus,
)


def active_lane_keys(
    running_runs: list[OrchestrationRun],
    waiting_runs: list[OrchestrationRun],
) -> set[str]:
    return {
        run.lane_lock_key
        for run in [*running_runs, *waiting_runs]
        if run.lane_lock_key is not None
    }


def backpressure_section(
    *,
    queued_runs: list[OrchestrationRun],
    waiting_runs: list[OrchestrationRun],
    active_lane_keys: set[str],
    available_executor_slots: int,
) -> OperationsChartSectionModel:
    counts: Counter[str] = Counter()
    for run in queued_runs:
        counts[
            _backpressure_bucket(run, available_executor_slots, active_lane_keys)
        ] += 1
    for run in waiting_runs:
        counts[
            _backpressure_bucket(run, available_executor_slots, active_lane_keys)
        ] += 1

    specs = (
        ("executor_busy", "Executor Busy", "warning"),
        ("waiting_worker", "Waiting for Worker", "info"),
        ("lane_lock", "Waiting for Lane Lock", "warning"),
        ("approval", "Waiting for Approval", "warning"),
        ("tool", "Waiting for Tool", "info"),
        ("access", "Waiting for Access", "danger"),
        ("other", "Other", "neutral"),
    )
    return OperationsChartSectionModel(
        id="backpressure",
        title="Backpressure",
        kind="donut",
        total=sum(counts.values()),
        segments=tuple(
            OperationsChartSegmentModel(
                id=item_id, label=label, value=counts[item_id], tone=tone
            )
            for item_id, label, tone in specs
            if counts[item_id] > 0
        ),
    )

def _backpressure_bucket(
    run: OrchestrationRun,
    available_executor_slots: int,
    active_lane_keys: set[str],
) -> str:
    reason = f"{run.waiting_reason or ''} {run.stage.value}".lower()
    if (
        run.status is OrchestrationRunStatus.QUEUED
        and run.lane_key is not None
        and run.lane_key in active_lane_keys
    ):
        return "lane_lock"
    if run.stage is OrchestrationRunStage.WAITING_FOR_CONFIRMATION:
        return "approval"
    if "approval" in reason or "confirmation" in reason:
        return "approval"
    if run.pending_tool_run_ids or run.stage is OrchestrationRunStage.WAITING_ON_TOOL:
        return "tool"
    if "tool" in reason:
        return "tool"
    if "access" in reason or "capability" in reason:
        return "access"
    if "lane" in reason or "lock" in reason:
        return "lane_lock"
    if run.status is OrchestrationRunStatus.QUEUED:
        if available_executor_slots <= 0:
            return "executor_busy"
        return "waiting_worker"
    return "other"
