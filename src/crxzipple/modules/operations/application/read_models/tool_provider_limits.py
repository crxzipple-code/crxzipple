from __future__ import annotations

from datetime import datetime
from typing import Any

from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableSectionModel,
)
from crxzipple.modules.operations.application.read_models.tool_provider_limit_facts import (
    TOOL_PROVIDER_LIMITER_ACTIVE,
    TOOL_PROVIDER_LIMITER_WAITERS,
    TOOL_PROVIDER_LIMITER_WAIT_SECONDS,
    metric_items,
    metric_provider_key,
    provider_limiter_configurations,
)
from crxzipple.modules.operations.application.read_models.tool_provider_limit_snapshots import (
    provider_limiter_configuration_snapshots,
    provider_metric_snapshots,
)
from crxzipple.modules.operations.application.read_models.tool_provider_local_capacity import (
    provider_local_capacity_configurations,
)
from crxzipple.modules.operations.application.read_models.tool_provider_limit_rows import (
    columns,
    float_value,
    int_value,
    optional_str,
    provider_limit_row,
    provider_metric_bucket,
)
from crxzipple.modules.tool.application.concurrency import (
    ToolRunConcurrencyPolicy,
)
from crxzipple.modules.tool.domain import Tool, ToolRun, ToolRunAssignment, ToolWorkerRegistration


def provider_limits_section(
    *,
    tools: list[Tool],
    runs: list[ToolRun],
    workers: list[ToolWorkerRegistration],
    assignments: list[ToolRunAssignment],
    concurrency_policy: ToolRunConcurrencyPolicy,
    runtime_metrics: Any | None,
    runtime_registry: Any | None,
    now: datetime,
) -> OperationsTableSectionModel:
    snapshots = provider_metric_snapshots(
        workers=workers,
        runtime_metrics=runtime_metrics,
        now=now,
    )
    grouped: dict[str, dict[str, Any]] = {}
    for source, snapshot in provider_limiter_configuration_snapshots(
        workers=workers,
        runtime_registry=runtime_registry,
        now=now,
    ):
        for provider_key, config in provider_limiter_configurations(snapshot):
            bucket = grouped.setdefault(provider_key, provider_metric_bucket())
            bucket["sources"].add(source)
            bucket["runtime_keys"].update(config.get("runtime_keys", set()))
            limit = config.get("limit")
            if limit is not None:
                limit_value = int_value(limit)
                bucket["configured_capacity"] += limit_value
                bucket["configured_limit_entries"].add(("proc", limit_value))
                bucket["process_limits"].add(limit_value)
    for provider_key, config in provider_local_capacity_configurations(
        tools=tools,
        runs=runs,
        workers=workers,
        assignments=assignments,
        concurrency_policy=concurrency_policy,
        now=now,
    ):
        bucket = grouped.setdefault(provider_key, provider_metric_bucket())
        bucket["sources"].update(config.get("sources", set()))
        bucket["runtime_keys"].update(config.get("runtime_keys", set()))
        bucket["configured_capacity"] += int_value(config.get("capacity"))
        bucket["active"] += float_value(config.get("active"))
        bucket["waiting"] += float_value(config.get("waiting"))
        limit = config.get("limit")
        if limit is not None:
            bucket["configured_limit_entries"].add(("worker", int_value(limit)))
    for source, snapshot in snapshots:
        for item in metric_items(snapshot, "gauges"):
            name = optional_str(item.get("name"))
            provider_key = metric_provider_key(item)
            if provider_key is None:
                continue
            bucket = grouped.setdefault(provider_key, provider_metric_bucket())
            bucket["sources"].add(source)
            if name == TOOL_PROVIDER_LIMITER_ACTIVE:
                bucket["active"] += float_value(item.get("value"))
            elif name == TOOL_PROVIDER_LIMITER_WAITERS:
                bucket["waiting"] += float_value(item.get("value"))
        for item in metric_items(snapshot, "timings"):
            if optional_str(item.get("name")) != TOOL_PROVIDER_LIMITER_WAIT_SECONDS:
                continue
            provider_key = metric_provider_key(item)
            if provider_key is None:
                continue
            bucket = grouped.setdefault(provider_key, provider_metric_bucket())
            bucket["sources"].add(source)
            count = int_value(item.get("count"))
            total = float_value(item.get("total_seconds"))
            bucket["wait_count"] += count
            bucket["total_wait_seconds"] += total
            bucket["max_wait_seconds"] = max(
                bucket["max_wait_seconds"],
                float_value(item.get("max_seconds")),
            )

    rows = tuple(
        provider_limit_row(provider_key, bucket)
        for provider_key, bucket in sorted(grouped.items())
        if bucket["active"]
        or bucket["waiting"]
        or bucket["wait_count"]
        or bucket["sources"]
        or bucket["configured_capacity"]
    )
    return OperationsTableSectionModel(
        id="provider_limits",
        title="Provider Limits",
        columns=columns(
            ("provider", "Provider"),
            ("state", "State"),
            ("limit", "Limit"),
            ("capacity", "Capacity"),
            ("waiting", "Waiting"),
            ("runtimes", "Runtime Count"),
            ("wait_count", "Wait Count"),
            ("avg_wait", "Avg Wait"),
            ("max_wait", "Max Wait"),
            ("sources", "Sources"),
        ),
        rows=rows,
        total=len(rows),
        view_all_route="/operations/tool?tab=provider_limits",
        empty_state="No remote provider limiter metrics observed.",
    )

