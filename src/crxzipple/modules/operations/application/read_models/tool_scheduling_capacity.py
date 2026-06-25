from __future__ import annotations

from collections import Counter
from datetime import datetime

from crxzipple.modules.operations.application.read_models.tool_worker_runtime import (
    online_workers,
)
from crxzipple.modules.tool.application.concurrency import (
    ToolRunConcurrencyGroup,
    ToolRunConcurrencyPolicy,
)
from crxzipple.modules.tool.domain import (
    Tool,
    ToolRun,
    ToolRunAssignment,
    ToolRunAssignmentStatus,
    ToolWorkerRegistration,
)


def worker_group_counts(
    *,
    runs: list[ToolRun],
    assignments: list[ToolRunAssignment],
    tools_by_id: dict[str, Tool],
    concurrency_policy: ToolRunConcurrencyPolicy,
) -> tuple[dict[str, Counter[str]], set[str]]:
    counts: dict[str, Counter[str]] = {}
    counted_run_ids: set[str] = set()
    runs_by_id = {run.id: run for run in runs}
    for assignment in assignments:
        if assignment.status not in {
            ToolRunAssignmentStatus.ASSIGNED,
            ToolRunAssignmentStatus.RUNNING,
        }:
            continue
        run = runs_by_id.get(assignment.run_id)
        if run is None or run.is_terminal():
            continue
        group = concurrency_group_for_run(
            run,
            tools_by_id=tools_by_id,
            concurrency_policy=concurrency_policy,
        )
        counts.setdefault(assignment.worker_id, Counter())[group.key] += 1
        counted_run_ids.add(run.id)

    for run in runs:
        if run.id in counted_run_ids or run.is_terminal() or not run.worker_id:
            continue
        group = concurrency_group_for_run(
            run,
            tools_by_id=tools_by_id,
            concurrency_policy=concurrency_policy,
        )
        counts.setdefault(run.worker_id, Counter())[group.key] += 1
        counted_run_ids.add(run.id)
    return counts, counted_run_ids


def concurrency_group_for_run(
    run: ToolRun,
    *,
    tools_by_id: dict[str, Tool],
    concurrency_policy: ToolRunConcurrencyPolicy,
) -> ToolRunConcurrencyGroup:
    return concurrency_policy.group_for(run=run, tool=tools_by_id.get(run.tool_id))


def group_worker_capacity(
    group: ToolRunConcurrencyGroup,
    *,
    workers: list[ToolWorkerRegistration],
    now: datetime,
) -> int:
    return sum(
        min(max(worker.max_in_flight, 0), group.max_in_flight)
        for worker in online_workers(workers, now=now)
    )


def sum_group_counts(worker_group_counts: dict[str, Counter[str]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for counts_for_worker in worker_group_counts.values():
        counts.update(counts_for_worker)
    return counts


def available_worker_count_for_group(
    group: ToolRunConcurrencyGroup,
    *,
    workers: list[ToolWorkerRegistration],
    worker_group_counts: dict[str, Counter[str]],
    now: datetime,
) -> int:
    return sum(
        1
        for worker in online_workers(workers, now=now)
        if worker_can_start_group(
            worker,
            group,
            worker_group_counts=worker_group_counts,
        )
    )


def worker_can_start_group(
    worker: ToolWorkerRegistration,
    group: ToolRunConcurrencyGroup,
    *,
    worker_group_counts: dict[str, Counter[str]],
) -> bool:
    if worker.current_in_flight >= worker.max_in_flight:
        return False
    return worker_group_counts.get(worker.id, Counter())[group.key] < group.max_in_flight
