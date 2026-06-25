from __future__ import annotations

from datetime import datetime
from typing import Any

from crxzipple.modules.operations.application.read_models.tool_provider_identity import (
    tool_provider_key,
)
from crxzipple.modules.operations.application.read_models.tool_provider_limit_rows import (
    int_value,
)
from crxzipple.modules.operations.application.read_models.tool_scheduling_capacity import (
    concurrency_group_for_run,
    group_worker_capacity,
    worker_group_counts,
)
from crxzipple.modules.operations.application.read_models.tool_worker_runtime import (
    online_workers,
)
from crxzipple.modules.tool.application.concurrency import (
    ToolRunConcurrencyGroup,
    ToolRunConcurrencyPolicy,
)
from crxzipple.modules.tool.domain import (
    Tool,
    ToolMode,
    ToolRun,
    ToolRunAssignment,
    ToolWorkerRegistration,
)


def provider_local_capacity_configurations(
    *,
    tools: list[Tool],
    runs: list[ToolRun],
    workers: list[ToolWorkerRegistration],
    assignments: list[ToolRunAssignment],
    concurrency_policy: ToolRunConcurrencyPolicy,
    now: datetime,
) -> tuple[tuple[str, dict[str, Any]], ...]:
    tools_by_id = tool_lookup(tools)
    active_runs = [run for run in runs if not run.is_terminal()]
    _, assigned_run_ids = worker_group_counts(
        runs=active_runs,
        assignments=assignments,
        tools_by_id=tools_by_id,
        concurrency_policy=concurrency_policy,
    )
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for tool in tools:
        if ToolMode.BACKGROUND not in tool.execution_support.supported_modes:
            continue
        provider_key = tool_provider_key(tool)
        group = concurrency_policy.group_for_tool(tool)
        if not is_provider_limiter_key(provider_key) or not group.key.startswith(
            "capability:",
        ):
            continue
        bucket = grouped.setdefault(
            (provider_key, group.key),
            {
                "active": 0,
                "waiting": 0,
                "limit": group.max_in_flight,
                "runtime_keys": set(),
                "group": group,
            },
        )
        bucket["runtime_keys"].add(tool.resolved_runtime_key())
        if group.max_in_flight > int_value(bucket.get("limit")):
            bucket["limit"] = group.max_in_flight
            bucket["group"] = group

    for run in active_runs:
        tool = tools_by_id.get(run.tool_id)
        if tool is None:
            continue
        provider_key = tool_provider_key(tool)
        group = concurrency_group_for_run(
            run,
            tools_by_id=tools_by_id,
            concurrency_policy=concurrency_policy,
        )
        if not is_provider_limiter_key(provider_key) or not group.key.startswith(
            "capability:",
        ):
            continue
        bucket = grouped.setdefault(
            (provider_key, group.key),
            {
                "active": 0,
                "waiting": 0,
                "limit": group.max_in_flight,
                "runtime_keys": set(),
                "group": group,
            },
        )
        bucket["runtime_keys"].add(tool.resolved_runtime_key())
        if run.id in assigned_run_ids or run.worker_id:
            bucket["active"] += 1
        else:
            bucket["waiting"] += 1

    online_worker_records = online_workers(workers, now=now)
    worker_sources = {worker.id for worker in online_worker_records}
    rows: list[tuple[str, dict[str, Any]]] = []
    for (provider_key, _group_key), bucket in sorted(grouped.items()):
        group = bucket.get("group")
        if not isinstance(group, ToolRunConcurrencyGroup):
            continue
        rows.append(
            (
                provider_key,
                {
                    "active": bucket["active"],
                    "waiting": bucket["waiting"],
                    "limit": bucket["limit"],
                    "capacity": group_worker_capacity(
                        group,
                        workers=workers,
                        now=now,
                    ),
                    "runtime_keys": bucket["runtime_keys"],
                    "sources": worker_sources or {"tool-policy"},
                },
            ),
        )
    return tuple(rows)


def is_provider_limiter_key(provider_key: str) -> bool:
    return provider_key.startswith(("provider:", "openapi:", "mcp:"))


def tool_lookup(tools: list[Tool]) -> dict[str, Tool]:
    return {tool.id: tool for tool in tools}
