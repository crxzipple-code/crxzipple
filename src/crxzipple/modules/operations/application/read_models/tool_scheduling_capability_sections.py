from __future__ import annotations

from collections import Counter
from datetime import datetime

from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableRowModel,
    OperationsTableSectionModel,
)
from crxzipple.modules.operations.application.read_models.tool_scheduling_capacity import (
    concurrency_group_for_run,
    sum_group_counts,
    worker_group_counts,
)
from crxzipple.modules.operations.application.read_models.tool_scheduling_labels import (
    columns,
)
from crxzipple.modules.operations.application.read_models.tool_scheduling_run_projection import (
    tool_lookup,
)
from crxzipple.modules.operations.application.read_models.tool_scheduling_rows import (
    capability_limit_row,
)
from crxzipple.modules.tool.application.concurrency import (
    ToolRunConcurrencyGroup,
    ToolRunConcurrencyPolicy,
)
from crxzipple.modules.tool.domain import (
    Tool,
    ToolRun,
    ToolRunAssignment,
    ToolWorkerRegistration,
)


def capability_limits_section(
    *,
    tools: list[Tool],
    runs: list[ToolRun],
    workers: list[ToolWorkerRegistration],
    assignments: list[ToolRunAssignment],
    concurrency_policy: ToolRunConcurrencyPolicy,
    now: datetime,
) -> OperationsTableSectionModel:
    tools_by_id = tool_lookup(tools)
    active_runs = [run for run in runs if not run.is_terminal()]
    group_counts, assigned_run_ids = worker_group_counts(
        runs=active_runs,
        assignments=assignments,
        tools_by_id=tools_by_id,
        concurrency_policy=concurrency_policy,
    )
    active_by_group = sum_group_counts(group_counts)
    waiting_by_group: Counter[str] = Counter()
    catalog_by_group: Counter[str] = Counter()
    default_catalog_count = 0

    for tool in tools:
        group = concurrency_policy.group_for_tool(tool)
        if group.key.startswith("capability:"):
            catalog_by_group[group.key] += 1
        else:
            default_catalog_count += 1

    groups: dict[str, ToolRunConcurrencyGroup] = {}
    for tool in tools:
        group = concurrency_policy.group_for_tool(tool)
        if group.key.startswith("capability:"):
            groups[group.key] = group

    for run in active_runs:
        group = concurrency_group_for_run(
            run,
            tools_by_id=tools_by_id,
            concurrency_policy=concurrency_policy,
        )
        if group.key.startswith("capability:"):
            groups[group.key] = group
        if run.id not in assigned_run_ids and not run.worker_id:
            waiting_by_group[group.key] += 1

    default_active = sum(
        count for key, count in active_by_group.items() if key.startswith("tool:")
    )
    default_waiting = sum(
        count for key, count in waiting_by_group.items() if key.startswith("tool:")
    )

    rows: list[OperationsTableRowModel] = []
    for key, group in sorted(groups.items(), key=lambda item: item[0]):
        rows.append(
            capability_limit_row(
                group=group,
                catalog_count=catalog_by_group[key],
                active=active_by_group[key],
                waiting=waiting_by_group[key],
                workers=workers,
                worker_group_counts=group_counts,
                now=now,
            ),
        )

    if default_catalog_count or default_active or default_waiting:
        default_group = ToolRunConcurrencyGroup(
            key="tool:*",
            max_in_flight=concurrency_policy.default_max_in_flight,
        )
        rows.append(
            capability_limit_row(
                group=default_group,
                catalog_count=default_catalog_count,
                active=default_active,
                waiting=default_waiting,
                workers=workers,
                worker_group_counts=group_counts,
                now=now,
            ),
        )

    return OperationsTableSectionModel(
        id="capability_limits",
        title="Capability Concurrency",
        columns=columns(
            ("capability", "Capability"),
            ("limit", "Limit"),
            ("capacity", "Capacity"),
            ("active", "Active"),
            ("waiting", "Waiting"),
            ("available_workers", "Available Workers"),
            ("tools", "Tools"),
            ("state", "State"),
            ("reason", "Reason"),
        ),
        rows=tuple(rows),
        total=len(rows),
        view_all_route="/operations/tool?tab=capabilities",
        empty_state="No tool capability groups observed.",
    )
