from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from typing import Any

from crxzipple.modules.operations.application.read_models.models import MetricCardModel
from crxzipple.modules.operations.application.read_models.presenters import (
    health_delta,
    health_label,
    health_tone,
)
from crxzipple.modules.operations.application.read_models.tool_metric_values import (
    duration_label,
    percentile_int,
    runs_since,
    terminal_run_duration_seconds,
    throughput_label,
)
from crxzipple.modules.operations.application.read_models.tool_runtime_metrics import (
    runtime_default_metric_cards,
)
from crxzipple.modules.operations.application.read_models.tool_worker_runtime import (
    worker_is_online,
)
from crxzipple.modules.tool.domain import Tool, ToolRun, ToolRunStatus, ToolWorkerRegistration


def tool_health(
    *,
    tools: list[Tool],
    active_runs: list[ToolRun],
    failed_runs: list[ToolRun],
) -> str:
    if failed_runs:
        return "warning"
    if active_runs:
        return "healthy"
    if not tools:
        return "warning"
    return "healthy"


def tool_metric_cards(
    *,
    tools: list[Tool],
    runs: list[ToolRun],
    active_runs: list[ToolRun],
    failed_runs: list[ToolRun],
    health: str,
    workers: list[ToolWorkerRegistration],
    now: datetime,
    runtime_bootstrap_config: Any | None = None,
) -> tuple[MetricCardModel, ...]:
    run_counts = Counter(run.status for run in runs)
    enabled_count = sum(1 for tool in tools if tool.enabled)
    confirmation_count = sum(
        1 for tool in tools if tool.execution_policy.requires_confirmation
    )
    access_gated_count = sum(1 for tool in tools if tool.access_requirement_sets)
    recent_runs = runs_since(runs, since=now - timedelta(hours=24))
    failed_24h = [
        run
        for run in recent_runs
        if run.status in {ToolRunStatus.FAILED, ToolRunStatus.TIMED_OUT}
    ]
    terminal_durations = [
        duration
        for duration in (
            terminal_run_duration_seconds(run) for run in (recent_runs or runs)
        )
        if duration is not None
    ]
    avg_latency = (
        duration_label(int(round(sum(terminal_durations) / len(terminal_durations))))
        if terminal_durations
        else "-"
    )
    p95_latency = (
        duration_label(percentile_int(terminal_durations, 95))
        if terminal_durations
        else "-"
    )
    throughput = throughput_label(len(recent_runs))
    online_capacity = sum(
        worker.max_in_flight
        for worker in workers
        if worker_is_online(worker, now=now)
    )
    runtime_metrics = runtime_default_metric_cards(runtime_bootstrap_config)
    return (
        MetricCardModel(
            id="health",
            label="Overall Health",
            value=health_label(health),
            delta=health_delta(health, healthy="Tool runtime state is queryable"),
            tone=health_tone(health),
        ),
        MetricCardModel(
            id="catalog",
            label="Tool Catalog",
            value=str(len(tools)),
            delta=f"{enabled_count} enabled",
            tone="success" if enabled_count else "warning",
        ),
        MetricCardModel(
            id="active_runs",
            label="Active Tool Runs",
            value=str(len(active_runs)),
            delta=f"{run_counts[ToolRunStatus.QUEUED]} queued / {online_capacity} capacity",
            tone="info" if active_runs else "success",
        ),
        MetricCardModel(
            id="failed_runs",
            label="Failed Tool Runs (24h)",
            value=str(len(failed_24h)),
            delta=f"{len(failed_runs)} retained failures",
            tone="danger" if failed_24h else "success",
        ),
        MetricCardModel(
            id="avg_latency",
            label="Average Latency",
            value=avg_latency,
            delta="terminal tool runs",
            tone=(
                "warning"
                if terminal_durations and max(terminal_durations) > 120
                else "info"
            ),
        ),
        MetricCardModel(
            id="p95_latency",
            label="P95 Latency",
            value=p95_latency,
            delta="24h when available",
            tone=(
                "warning"
                if terminal_durations and percentile_int(terminal_durations, 95) > 120
                else "info"
            ),
        ),
        MetricCardModel(
            id="throughput",
            label="Throughput",
            value=throughput,
            delta="last 24h",
            tone="info" if recent_runs else "neutral",
        ),
        MetricCardModel(
            id="confirmation",
            label="Confirmation Required",
            value=str(confirmation_count),
            delta="tools require operator consent",
            tone="warning" if confirmation_count else "success",
        ),
        MetricCardModel(
            id="access_gated",
            label="Access Gated",
            value=str(access_gated_count),
            delta="tools with access requirements",
            tone="warning" if access_gated_count else "neutral",
        ),
        *runtime_metrics,
    )
