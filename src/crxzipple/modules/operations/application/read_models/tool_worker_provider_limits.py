from __future__ import annotations

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
from crxzipple.modules.operations.application.read_models.tool_provider_limit_rows import (
    columns,
    float_value,
    int_value,
    optional_str,
    provider_limit_row,
    provider_metric_bucket,
)
from crxzipple.modules.tool.domain import ToolWorkerRegistration


def tool_worker_provider_limits_section(
    worker: ToolWorkerRegistration,
) -> OperationsTableSectionModel:
    snapshot = worker.capabilities_payload.get("runtime_metrics")
    registry = worker.capabilities_payload.get("runtime_registry")
    grouped: dict[str, dict[str, Any]] = {}
    if isinstance(registry, dict):
        for provider_key, config in provider_limiter_configurations(registry):
            bucket = grouped.setdefault(provider_key, provider_metric_bucket())
            limit = int_value(config.get("limit"))
            runtime_keys = config.get("runtime_keys")
            if isinstance(runtime_keys, set):
                bucket["runtime_keys"].update(runtime_keys)
            if limit:
                bucket["configured_capacity"] += limit
                bucket["configured_limit_entries"].add(("worker", limit))
    if isinstance(snapshot, dict):
        for item in metric_items(snapshot, "gauges"):
            provider_key = metric_provider_key(item)
            if provider_key is None:
                continue
            bucket = grouped.setdefault(provider_key, provider_metric_bucket())
            bucket["sources"].add(worker.id)
            name = optional_str(item.get("name"))
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
            bucket["sources"].add(worker.id)
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
        or bucket["configured_capacity"]
        or bucket["runtime_keys"]
    )
    return OperationsTableSectionModel(
        id="worker_provider_limits",
        title="Worker Provider Limits",
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
        ),
        rows=rows,
        total=len(rows),
        empty_state="No provider limiter metrics reported by this worker.",
    )
