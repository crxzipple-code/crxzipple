from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
import re
from typing import Any, Mapping

from crxzipple.modules.orchestration.domain import ExecutionOwnerReference
from crxzipple.modules.operations.application.read_models.models import (
    MetricCardModel,
    OperationsChartSectionModel,
    OperationsChartSegmentModel,
    OperationsKeyValueItemModel,
    OperationsKeyValueSectionModel,
    OperationsModuleOverview,
    OperationsModuleRoleModel,
    OperationsTabModel,
    OperationsTableColumnModel,
    OperationsTableRowModel,
    OperationsTableSectionModel,
    RuntimeActionModel,
)
from crxzipple.modules.operations.application.observation import (
    OperationsObservedEvent,
    observed_event_from_record,
)
from crxzipple.modules.operations.application.read_models.ports import (
    OperationsToolQueryPort,
)
from crxzipple.modules.tool.application.concurrency import (
    ToolRunConcurrencyGroup,
    ToolRunConcurrencyPolicy,
)
from crxzipple.modules.tool.domain import (
    Tool,
    ToolEnvironment,
    ToolExecutionStrategy,
    ToolRun,
    ToolRunAssignment,
    ToolRunAssignmentStatus,
    ToolRunStatus,
    ToolMode,
    ToolDefinitionOrigin,
    ToolWorkerRegistration,
    ToolWorkerStatus,
)
from crxzipple.shared.content_blocks import describe_content_for_text_fallback
from crxzipple.shared.event_contracts import (
    TOOL_CLI_EVENT_NAMES,
    TOOL_FUNCTION_EVENT_NAMES,
    TOOL_SOURCE_EVENT_NAMES,
)
from crxzipple.shared.time import coerce_utc_datetime, format_datetime_utc

_LONG_RUNNING_SECONDS = 300
_WORKER_POOL_EXPIRED_GRACE_SECONDS = 300
_TOOL_PROVIDER_LIMITER_PREFIX = "tool.remote_provider_limiter."
_TOOL_PROVIDER_LIMITER_ACTIVE = f"{_TOOL_PROVIDER_LIMITER_PREFIX}active"
_TOOL_PROVIDER_LIMITER_WAITERS = f"{_TOOL_PROVIDER_LIMITER_PREFIX}waiters"
_TOOL_PROVIDER_LIMITER_WAIT_SECONDS = f"{_TOOL_PROVIDER_LIMITER_PREFIX}wait_seconds"
_KNOWN_PROVIDER_TAGS = frozenset(
    {
        "anthropic",
        "azure",
        "browserbase",
        "gemini",
        "google",
        "mcp",
        "ollama",
        "openai",
        "openapi",
        "vllm",
    },
)
_MAX_TOOL_EVENT_TOPICS = 200
_MAX_RECENT_TOOL_EVENTS = 240
_RECENT_TOOL_TOPIC_LIMIT = 100
_TOOL_DIRECT_EVENT_TOPICS = (
    "events.named.tool.run.created",
    "events.named.tool.run.queued",
    "events.named.tool.run.dispatching",
    "events.named.tool.run.started",
    "events.named.tool.run.heartbeated",
    "events.named.tool.run.succeeded",
    "events.named.tool.run.failed",
    "events.named.tool.run.requeued",
    "events.named.tool.run.cancel_requested",
    "events.named.tool.run.cancelled",
    "events.named.tool.run.timed_out",
    "events.named.tool.assignment.created",
    "events.named.tool.assignment.started",
    "events.named.tool.assignment.heartbeated",
    "events.named.tool.assignment.succeeded",
    "events.named.tool.assignment.failed",
    "events.named.tool.assignment.cancelled",
    "events.named.tool.assignment.expired",
    "events.named.tool.worker.registered",
    "events.named.tool.worker.capabilities_updated",
    "events.named.tool.worker.recovered",
    "events.named.tool.worker.pruned",
    "events.named.tool.worker.stale",
    "events.named.tool.enabled",
    "events.named.tool.disabled",
    *(f"events.named.{event_name}" for event_name in TOOL_SOURCE_EVENT_NAMES),
    *(f"events.named.{event_name}" for event_name in TOOL_FUNCTION_EVENT_NAMES),
    *(f"events.named.{event_name}" for event_name in TOOL_CLI_EVENT_NAMES),
    "tool.run.created",
    "tool.run.queued",
    "tool.run.dispatching",
    "tool.run.started",
    "tool.run.heartbeated",
    "tool.run.succeeded",
    "tool.run.failed",
    "tool.run.requeued",
    "tool.run.cancel_requested",
    "tool.run.cancelled",
    "tool.run.timed_out",
    "tool.assignment.created",
    "tool.assignment.started",
    "tool.assignment.heartbeated",
    "tool.assignment.succeeded",
    "tool.assignment.failed",
    "tool.assignment.cancelled",
    "tool.assignment.expired",
    "tool.worker.registered",
    "tool.worker.capabilities_updated",
    "tool.worker.recovered",
    "tool.worker.pruned",
    "tool.worker.stale",
    "tool.enabled",
    "tool.disabled",
    *TOOL_SOURCE_EVENT_NAMES,
    *TOOL_FUNCTION_EVENT_NAMES,
    *TOOL_CLI_EVENT_NAMES,
)


@dataclass(frozen=True, slots=True)
class ToolOperationsQuery:
    status: str = "all"
    time_window: str = "all"
    search: str = ""
    tool_id: str = "all"
    provider: str = "all"
    mode: str = "all"
    strategy: str = "all"
    environment: str = "all"
    worker_id: str = "all"
    has_artifact: str = "all"
    retryable: str = "all"
    limit: int = 50
    offset: int = 0


@dataclass(frozen=True, slots=True)
class ToolOperationsPage:
    module: str
    title: str
    subtitle: str
    health: str
    updated_at: str
    auto_refresh: bool
    role: OperationsModuleRoleModel
    metrics: tuple[MetricCardModel, ...]
    tabs: tuple[OperationsTabModel, ...]
    active_tab: str
    actions: tuple[RuntimeActionModel, ...]
    active_tool_runs: OperationsTableSectionModel
    tool_queue_runs: OperationsTableSectionModel
    tool_waiting_io: OperationsTableSectionModel
    tool_runs: OperationsTableSectionModel
    tool_types: OperationsChartSectionModel
    source_health: OperationsTableSectionModel
    discovery_failures: OperationsTableSectionModel
    function_catalog: OperationsTableSectionModel
    provider_backend_health: OperationsTableSectionModel
    cli_process_health: OperationsTableSectionModel
    auth_missing: OperationsTableSectionModel
    worker_pool: OperationsChartSectionModel
    workers: OperationsTableSectionModel
    tool_queue: OperationsTableSectionModel
    capability_limits: OperationsTableSectionModel
    provider_limits: OperationsTableSectionModel
    provider_history: OperationsTableSectionModel
    run_blockers: OperationsTableSectionModel
    inline_risk: OperationsKeyValueSectionModel
    recent_artifacts: OperationsTableSectionModel
    tool_lifecycle_events: OperationsTableSectionModel
    strategies: OperationsTableSectionModel
    worker_details: tuple["ToolWorkerDetailModel", ...]
    tool_run_details: tuple["ToolRunDetailModel", ...]


@dataclass(frozen=True, slots=True)
class ToolWorkerDetailModel:
    worker_id: str
    title: str
    status: str
    tone: str
    summary: tuple[OperationsKeyValueItemModel, ...]
    capabilities: OperationsKeyValueSectionModel
    runtimes: OperationsTableSectionModel
    provider_limits: OperationsTableSectionModel
    events: OperationsTableSectionModel
    raw_payload: Any


@dataclass(frozen=True, slots=True)
class ToolRunDetailModel:
    run_id: str
    title: str
    status: str
    tone: str
    summary: tuple[OperationsKeyValueItemModel, ...]
    invocation_context: tuple[OperationsKeyValueItemModel, ...]
    input_payload: Any
    result_payload: Any
    result_summary: str
    error: str
    error_facts: OperationsKeyValueSectionModel
    assignments: OperationsTableSectionModel
    events: OperationsTableSectionModel
    artifacts: OperationsTableSectionModel


def defer_tool_run_details_payload(payload: dict[str, Any]) -> None:
    payload["tool_run_details"] = []


def find_tool_run_detail_payload(
    payload: dict[str, Any],
    run_id: str,
) -> dict[str, Any] | None:
    details = payload.get("tool_run_details")
    if not isinstance(details, list):
        return None
    normalized_run_id = run_id.strip()
    for item in details:
        if isinstance(item, dict) and str(item.get("run_id") or "") == normalized_run_id:
            return item
    return None


@dataclass(slots=True)
class ToolOperationsReadModelProvider:
    tool_service: OperationsToolQueryPort
    access_service: Any | None = None
    artifact_service: Any | None = None
    run_query: Any | None = None
    events_service: Any | None = None
    event_definition_registry: Any | None = None
    operations_observation: Any | None = None
    runtime_metrics: Any | None = None
    runtime_registry: Any | None = None
    runtime_bootstrap_config: Any | None = None

    def overview(self) -> OperationsModuleOverview:
        now = datetime.now(timezone.utc)
        tools = self.tool_service.list_tools()
        runs = self.tool_service.list_tool_runs()
        workers = self.tool_service.list_tool_workers()
        assignments = self.tool_service.list_tool_run_assignments()
        assignment_by_run = _latest_assignment_by_run(assignments)
        active_runs = [run for run in runs if not run.is_terminal()]
        failed_runs = [
            run
            for run in runs
            if run.status in {ToolRunStatus.FAILED, ToolRunStatus.TIMED_OUT}
        ]
        health = _health(
            tools=tools,
            active_runs=active_runs,
            failed_runs=failed_runs,
        )

        return OperationsModuleOverview(
            module="tool",
            title="Tool",
            subtitle="监控工具目录、执行队列、失败运行、授权与确认风险。",
            health=health,
            updated_at=format_datetime_utc(now),
            metrics=_metric_cards(
                tools=tools,
                runs=runs,
                active_runs=active_runs,
                failed_runs=failed_runs,
                health=health,
                workers=workers,
                runtime_bootstrap_config=self.runtime_bootstrap_config,
                now=now,
            ),
            queue=_queue_rows(
                active_runs,
                assignment_by_run=assignment_by_run,
                now=now,
            ),
            lane_locks=_risk_rows(tools),
            executor=_worker_rows(workers, active_runs=active_runs),
            actions=_actions(),
        )

    def page(
        self,
        query: ToolOperationsQuery | None = None,
    ) -> ToolOperationsPage:
        now = datetime.now(timezone.utc)
        query = _normalize_query(query)
        tools = self.tool_service.list_tools()
        runs = self.tool_service.list_tool_runs()
        workers = self.tool_service.list_tool_workers()
        assignments = self.tool_service.list_tool_run_assignments()
        sources = _safe_tool_sources(self.tool_service)
        functions = _safe_tool_functions(self.tool_service)
        provider_backends = _safe_tool_provider_backends(self.tool_service)
        provider_backend_readiness = _safe_tool_provider_backend_readiness(
            self.tool_service,
            provider_backends,
        )
        discovery_runs_by_source = _safe_discovery_runs_by_source(
            self.tool_service,
            sources,
            limit=5,
        )
        assignment_by_run = _latest_assignment_by_run(assignments)
        active_runs = [run for run in runs if not run.is_terminal()]
        running_runs = [
            run for run in active_runs if run.status is ToolRunStatus.RUNNING
        ]
        running_run_ids = {run.id for run in running_runs}
        waiting_runs = [run for run in active_runs if run.id not in running_run_ids]
        failed_runs = [
            run
            for run in runs
            if run.status in {ToolRunStatus.FAILED, ToolRunStatus.TIMED_OUT}
        ]
        long_running_detail_runs = [
            run
            for run in active_runs
            if _duration_seconds(
                run,
                assignment=assignment_by_run.get(run.id),
                now=now,
            )
            >= _LONG_RUNNING_SECONDS
        ]
        artifact_count = sum(
            1
            for run in runs
            for _ in _artifact_refs(run, artifact_service=self.artifact_service)
        )
        observed_events = _recent_tool_events(
            operations_observation=self.operations_observation,
            events_service=self.events_service,
            definition_registry=self.event_definition_registry,
            limit=80,
        )
        risky_tools = _risky_tools(tools)
        concurrency_policy = self.tool_service.concurrency_policy
        provider_history = _provider_history_section(
            tools=tools,
            runs=runs,
            assignment_by_run=assignment_by_run,
            now=now,
        )
        filtered_tool_runs = _filter_tool_runs(
            runs,
            query=query,
            tools=tools,
            assignment_by_run=assignment_by_run,
            artifact_service=self.artifact_service,
            now=now,
        )
        visible_tool_runs = _paginate_runs(filtered_tool_runs, query=query)
        detail_runs = _dedupe_runs(
            (
                *visible_tool_runs,
                *running_runs,
                *waiting_runs,
                *failed_runs,
                *long_running_detail_runs,
            ),
        )
        run_contexts = _tool_run_contexts(self.run_query, detail_runs)
        health = _health(
            tools=tools,
            active_runs=active_runs,
            failed_runs=failed_runs,
        )
        actions = _actions()

        return ToolOperationsPage(
            module="tool",
            title="Tool Runtime",
            subtitle="工具目录、运行队列、worker 占用、权限风险、失败和产物的运维视图。",
            health=health,
            updated_at=format_datetime_utc(now),
            auto_refresh=True,
            role=OperationsModuleRoleModel(
                label="Admin",
                can_operate=True,
                scope="tool",
            ),
            metrics=_metric_cards(
                tools=tools,
                runs=runs,
                active_runs=active_runs,
                failed_runs=failed_runs,
                health=health,
                workers=workers,
                runtime_bootstrap_config=self.runtime_bootstrap_config,
                now=now,
            ),
            tabs=(
                OperationsTabModel(id="runs", label="Tool Runs", count=len(runs)),
                OperationsTabModel(
                    id="sources",
                    label="Sources",
                    count=len(sources),
                    tone=_source_tab_tone(sources, functions),
                ),
                OperationsTabModel(id="workers", label="Workers", count=len(workers)),
                OperationsTabModel(id="queue", label="Queue", count=len(waiting_runs)),
                OperationsTabModel(id="capabilities", label="Capabilities"),
                OperationsTabModel(
                    id="provider_limits",
                    label="Provider Limits",
                ),
                OperationsTabModel(
                    id="provider_history",
                    label="Provider History",
                    count=provider_history.total,
                ),
                OperationsTabModel(
                    id="diagnostics",
                    label="Diagnostics",
                    count=len(active_runs),
                    tone="warning" if active_runs else "neutral",
                ),
                OperationsTabModel(
                    id="risk",
                    label="Risk",
                    count=len(risky_tools),
                    tone="warning" if risky_tools else "neutral",
                ),
                OperationsTabModel(
                    id="artifacts",
                    label="Artifacts",
                    count=artifact_count,
                ),
                OperationsTabModel(
                    id="events",
                    label="Events",
                    count=len(observed_events),
                ),
                OperationsTabModel(id="strategies", label="Strategies"),
            ),
            active_tab="runs",
            actions=actions,
            active_tool_runs=_active_tool_runs_section(
                active_runs,
                tools=tools,
                assignment_by_run=assignment_by_run,
                run_contexts=run_contexts,
                now=now,
            ),
            tool_queue_runs=_tool_queue_runs_section(
                waiting_runs,
                active_runs=active_runs,
                tools=tools,
                workers=workers,
                assignments=assignments,
                assignment_by_run=assignment_by_run,
                concurrency_policy=concurrency_policy,
                now=now,
            ),
            tool_waiting_io=_tool_waiting_io_section(
                waiting_runs,
                active_runs=active_runs,
                tools=tools,
                workers=workers,
                assignments=assignments,
                assignment_by_run=assignment_by_run,
                concurrency_policy=concurrency_policy,
                now=now,
            ),
            tool_runs=_tool_runs_section(
                visible_tool_runs,
                tools=tools,
                assignment_by_run=assignment_by_run,
                artifact_service=self.artifact_service,
                run_contexts=run_contexts,
                now=now,
                total_count=len(filtered_tool_runs),
                empty_state=_tool_runs_empty_state(query),
            ),
            tool_types=_tool_types_section(tools, runs),
            source_health=_source_health_section(
                sources,
                functions=functions,
                discovery_runs_by_source=discovery_runs_by_source,
            ),
            discovery_failures=_discovery_failures_section(
                sources,
                discovery_runs_by_source=discovery_runs_by_source,
            ),
            function_catalog=_function_catalog_section(functions),
            provider_backend_health=_provider_backend_health_section(
                provider_backends,
                runs=runs,
                readiness_by_backend_id=provider_backend_readiness,
                now=now,
            ),
            cli_process_health=_cli_process_health_section(
                sources,
                functions=functions,
            ),
            auth_missing=_auth_missing_section(
                tools,
                runs,
                tool_service=self.tool_service,
                access_service=self.access_service,
                now=now,
            ),
            worker_pool=_worker_pool_section(
                workers,
                active_runs=active_runs,
                now=now,
            ),
            workers=_workers_section(
                workers,
                active_runs=active_runs,
                runs=runs,
                assignment_by_run=assignment_by_run,
                now=now,
            ),
            tool_queue=_tool_queue_section(
                waiting_runs,
                active_runs=active_runs,
                tools=tools,
                workers=workers,
                assignments=assignments,
                assignment_by_run=assignment_by_run,
                concurrency_policy=concurrency_policy,
                now=now,
            ),
            capability_limits=_capability_limits_section(
                tools=tools,
                runs=runs,
                workers=workers,
                assignments=assignments,
                concurrency_policy=concurrency_policy,
                now=now,
            ),
            provider_limits=_provider_limits_section(
                tools=tools,
                runs=runs,
                workers=workers,
                assignments=assignments,
                concurrency_policy=concurrency_policy,
                runtime_metrics=self.runtime_metrics,
                runtime_registry=self.runtime_registry,
                now=now,
            ),
            provider_history=provider_history,
            run_blockers=_run_blockers_section(
                active_runs,
                tools=tools,
                workers=workers,
                assignments=assignments,
                assignment_by_run=assignment_by_run,
                concurrency_policy=concurrency_policy,
                now=now,
            ),
            inline_risk=_inline_risk_section(
                runs,
                active_runs=active_runs,
                assignment_by_run=assignment_by_run,
                now=now,
            ),
            recent_artifacts=_recent_artifacts_section(
                runs,
                tools=tools,
                artifact_service=self.artifact_service,
            ),
            tool_lifecycle_events=_tool_lifecycle_events_section(
                observed_events,
                tools=tools,
                runs=runs,
            ),
            strategies=_strategies_section(runs),
            worker_details=_tool_worker_details(
                workers,
                active_runs=active_runs,
                observed_events=observed_events,
                now=now,
            ),
            tool_run_details=_tool_run_details(
                detail_runs,
                tools=tools,
                assignments=assignments,
                observed_events=observed_events,
                artifact_service=self.artifact_service,
                run_contexts=run_contexts,
                now=now,
            ),
        )


def _health(
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


def _health_label(health: str) -> str:
    return {
        "healthy": "Healthy",
        "warning": "Warning",
        "error": "Error",
    }.get(health, "Unknown")


def _health_delta(health: str) -> str:
    return {
        "healthy": "Tool runtime state is queryable",
        "warning": "Operator attention recommended",
        "error": "Operator action required",
    }.get(health, "Insufficient data")


def _health_tone(health: str) -> str:
    return {
        "healthy": "success",
        "warning": "warning",
        "error": "danger",
    }.get(health, "neutral")


def _metric_cards(
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
    recent_runs = _runs_since(runs, since=now - timedelta(hours=24))
    failed_24h = [
        run
        for run in recent_runs
        if run.status in {ToolRunStatus.FAILED, ToolRunStatus.TIMED_OUT}
    ]
    terminal_durations = [
        duration
        for duration in (
            _terminal_run_duration_seconds(run)
            for run in (recent_runs or runs)
        )
        if duration is not None
    ]
    avg_latency = (
        _duration_label(int(round(sum(terminal_durations) / len(terminal_durations))))
        if terminal_durations
        else "-"
    )
    p95_latency = (
        _duration_label(_percentile_int(terminal_durations, 95))
        if terminal_durations
        else "-"
    )
    throughput = _throughput_label(len(recent_runs))
    online_capacity = sum(
        worker.max_in_flight
        for worker in workers
        if _worker_is_online(worker, now=now)
    )
    runtime_metrics = _runtime_default_metric_cards(runtime_bootstrap_config)
    return (
        MetricCardModel(
            id="health",
            label="Overall Health",
            value=_health_label(health),
            delta=_health_delta(health),
            tone=_health_tone(health),
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
            tone="warning" if terminal_durations and max(terminal_durations) > 120 else "info",
        ),
        MetricCardModel(
            id="p95_latency",
            label="P95 Latency",
            value=p95_latency,
            delta="24h when available",
            tone="warning" if terminal_durations and _percentile_int(terminal_durations, 95) > 120 else "info",
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


def _runtime_default_metric_cards(
    runtime_bootstrap_config: Any | None,
) -> tuple[MetricCardModel, ...]:
    max_in_flight = _runtime_int(runtime_bootstrap_config, "tool_worker_max_in_flight")
    default_concurrency = _runtime_int(
        runtime_bootstrap_config,
        "tool_worker_default_run_concurrency",
    )
    image_concurrency = _runtime_int(
        runtime_bootstrap_config,
        "tool_worker_image_run_concurrency",
    )
    shared_state_concurrency = _runtime_int(
        runtime_bootstrap_config,
        "tool_worker_shared_state_run_concurrency",
    )
    max_attempts = _runtime_int(runtime_bootstrap_config, "tool_run_max_attempts")
    lease_seconds = _runtime_float(runtime_bootstrap_config, "tool_run_lease_seconds")
    heartbeat_seconds = _runtime_float(runtime_bootstrap_config, "tool_run_heartbeat_seconds")
    remote_limit = _runtime_int(
        runtime_bootstrap_config,
        "tool_remote_default_max_concurrency",
    )
    if (
        max_in_flight is None
        and default_concurrency is None
        and image_concurrency is None
        and shared_state_concurrency is None
        and max_attempts is None
        and lease_seconds is None
        and heartbeat_seconds is None
        and remote_limit is None
    ):
        return ()
    return (
        MetricCardModel(
            id="worker_policy",
            label="Worker Policy",
            value=str(max_in_flight) if max_in_flight is not None else "-",
            delta=_worker_policy_delta(
                default_concurrency,
                image_concurrency,
                shared_state_concurrency,
            ),
            tone="info",
        ),
        MetricCardModel(
            id="retry_policy",
            label="Retry Policy",
            value=_retry_policy_value(
                max_attempts=max_attempts,
                lease_seconds=lease_seconds,
                heartbeat_seconds=heartbeat_seconds,
            ),
            delta=f"remote {_display_int(remote_limit)}",
            tone="info",
        ),
    )


def _runtime_int(runtime_bootstrap_config: Any | None, name: str) -> int | None:
    value = getattr(runtime_bootstrap_config, name, None)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _runtime_float(runtime_bootstrap_config: Any | None, name: str) -> float | None:
    value = getattr(runtime_bootstrap_config, name, None)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _display_int(value: int | None) -> str:
    return str(value) if value is not None else "-"


def _worker_policy_delta(
    default_concurrency: int | None,
    image_concurrency: int | None,
    shared_state_concurrency: int | None,
) -> str:
    return (
        f"default {_display_int(default_concurrency)} / "
        f"image {_display_int(image_concurrency)} / "
        f"shared {_display_int(shared_state_concurrency)}"
    )


def _retry_policy_value(
    *,
    max_attempts: int | None,
    lease_seconds: float | None,
    heartbeat_seconds: float | None,
) -> str:
    if max_attempts is None and lease_seconds is None and heartbeat_seconds is None:
        return "-"
    return (
        f"{_display_int(max_attempts)}x / "
        f"{_duration_value(lease_seconds)} / "
        f"{_duration_value(heartbeat_seconds)}"
    )


def _duration_value(seconds: float | None) -> str:
    if seconds is None:
        return "-"
    return _duration_label(round(seconds))


def _actions() -> tuple[RuntimeActionModel, ...]:
    return (
        RuntimeActionModel(
            id="open_tool",
            label="Open Tool",
            owner="tool",
            kind="navigation",
            method="GET",
            endpoint="/operations/tool?tool_id={tool_id}",
        ),
        RuntimeActionModel(
            id="open_trace",
            label="Open Trace",
            owner="events",
            kind="navigation",
            method="GET",
            endpoint="/ui/trace/{trace_id}",
        ),
        RuntimeActionModel(
            id="cancel_tool_run",
            label="Cancel Tool Run",
            owner="tool",
            risk="controlled",
            requires_confirmation=True,
            audit_event="tool.run.cancel",
            method="POST",
            endpoint="/operations/tool/runs/{run_id}/cancel",
        ),
        RuntimeActionModel(
            id="retry_tool_run",
            label="Retry Tool Run",
            owner="tool",
            risk="controlled",
            requires_confirmation=True,
            audit_event="tool.run.retry",
            method="POST",
            endpoint="/operations/tool/runs/{run_id}/retry",
        ),
        RuntimeActionModel(
            id="prune_expired_workers",
            label="Prune Expired Workers",
            owner="tool",
            risk="controlled",
            requires_confirmation=True,
            audit_event="tool.workers.prune_expired",
            method="POST",
            endpoint="/operations/tool/workers/prune-expired",
        ),
        RuntimeActionModel(
            id="open_access",
            label="Open Access",
            owner="access",
            kind="navigation",
            method="GET",
            endpoint="/operations/access",
        ),
    )


def _queue_rows(
    runs: list[ToolRun],
    *,
    now: datetime,
    assignment_by_run: dict[str, ToolRunAssignment] | None = None,
) -> tuple[dict[str, str], ...]:
    assignment_by_run = assignment_by_run or {}
    sorted_runs = sorted(runs, key=lambda run: run.created_at)
    return tuple(
        {
            "Priority": run.target.mode.value,
            "Run ID": run.id,
            "Lane Key": run.tool_id,
            "Wait Reason": _run_reason(
                run,
                assignment=assignment_by_run.get(run.id),
                now=now,
            ),
            "Wait Time": _age_label(run.created_at, now=now),
        }
        for run in sorted_runs[:20]
    )


def _risk_rows(tools: list[Tool]) -> tuple[dict[str, str], ...]:
    return tuple(
        {
            "Lane Key": tool.id,
            "Holder Run ID": "-",
            "TTL": f"{tool.execution_policy.timeout_seconds}s",
            "Expires At": "-",
            "Reason": _tool_risk_reason(tool),
        }
        for tool in sorted(_overview_risky_tools(tools), key=lambda item: item.id)[
            :20
        ]
    )


def _worker_rows(
    workers: list[ToolWorkerRegistration],
    *,
    active_runs: list[ToolRun],
) -> tuple[dict[str, str], ...]:
    rows: list[dict[str, str]] = []
    if workers:
        current_run_by_worker = {
            run.worker_id: run.id
            for run in active_runs
            if run.worker_id is not None and run.worker_id.strip()
        }
        for worker in sorted(workers, key=lambda item: item.id):
            rows.append(
                {
                    "Worker ID": worker.id,
                    "Status": worker.status.value,
                    "Last Heartbeat": format_datetime_utc(worker.heartbeat_at),
                    "Current Run": current_run_by_worker.get(worker.id, "-"),
                    "Load": f"{worker.current_in_flight}/{worker.max_in_flight}",
                },
            )
        return tuple(rows[:20])
    for run in sorted(active_runs, key=lambda item: item.created_at, reverse=True):
        rows.append(
            {
                "Worker ID": run.worker_id or "-",
                "Status": run.status.value,
                "Last Heartbeat": (
                    format_datetime_utc(run.heartbeat_at)
                    if run.heartbeat_at is not None
                    else "-"
                ),
                "Current Run": run.id,
                "Load": "-",
            },
        )
    return tuple(rows[:20])


def _tool_runs_section(
    runs: list[ToolRun],
    *,
    tools: list[Tool],
    assignment_by_run: dict[str, ToolRunAssignment],
    artifact_service: Any | None,
    run_contexts: dict[str, dict[str, str]],
    now: datetime,
    total_count: int | None = None,
    empty_state: str = "No tool runs recorded.",
) -> OperationsTableSectionModel:
    tools_by_id = _tool_lookup(tools)
    rows = tuple(
        _tool_run_row(
            run,
            tools_by_id=tools_by_id,
            assignment=assignment_by_run.get(run.id),
            artifact_service=artifact_service,
            run_context=run_contexts.get(run.id),
            now=now,
        )
        for run in sorted(runs, key=_run_time, reverse=True)[:50]
    )
    return OperationsTableSectionModel(
        id="tool_runs",
        title="Recent Tool Runs",
        columns=_columns(
            ("time", "Time"),
            ("tool", "Tool"),
            ("run_id", "Run ID"),
            ("source", "Source"),
            ("orchestration_run_id", "Turn ID"),
            ("chain_id", "Chain ID"),
            ("step_id", "Step ID"),
            ("browser", "Browser"),
            ("status", "Status"),
            ("assignment_status", "Assignment"),
            ("lease_state", "Lease"),
            ("mode", "Mode"),
            ("strategy", "Strategy"),
            ("environment", "Environment"),
            ("worker", "Worker ID"),
            ("duration", "Duration"),
            ("actions", "Actions"),
        ),
        rows=rows,
        total=total_count if total_count is not None else len(runs),
        view_all_route="/operations/tool?tab=runs",
        empty_state=empty_state,
    )


def _active_tool_runs_section(
    runs: list[ToolRun],
    *,
    tools: list[Tool],
    assignment_by_run: dict[str, ToolRunAssignment],
    run_contexts: dict[str, dict[str, str]],
    now: datetime,
) -> OperationsTableSectionModel:
    tools_by_id = _tool_lookup(tools)
    rows = tuple(
        _tool_run_row(
            run,
            tools_by_id=tools_by_id,
            assignment=assignment_by_run.get(run.id),
            run_context=run_contexts.get(run.id),
            now=now,
        )
        for run in sorted(runs, key=_run_time, reverse=True)[:50]
    )
    return OperationsTableSectionModel(
        id="active_tool_runs",
        title="Active Tool Runs",
        columns=_columns(
            ("run_id", "Tool Run ID"),
            ("tool", "Tool"),
            ("source", "Source"),
            ("orchestration_run_id", "Turn ID"),
            ("chain_id", "Chain ID"),
            ("step_id", "Step ID"),
            ("browser", "Browser"),
            ("worker", "Worker ID"),
            ("duration", "Duration"),
            ("progress", "Progress"),
            ("status", "Status"),
            ("actions", "Actions"),
        ),
        rows=rows,
        total=len(runs),
        view_all_route="/operations/tool?tab=runs&status=active",
        empty_state="No active tool runs.",
    )


def _tool_run_row(
    run: ToolRun,
    *,
    tools_by_id: dict[str, Tool],
    assignment: ToolRunAssignment | None,
    artifact_service: Any | None = None,
    run_context: Mapping[str, str] | None = None,
    now: datetime,
) -> OperationsTableRowModel:
    tool = tools_by_id.get(run.tool_id)
    artifact_count = len(_artifact_refs(run, artifact_service=artifact_service))
    retryable = run.status in {ToolRunStatus.FAILED, ToolRunStatus.TIMED_OUT}
    return (
        OperationsTableRowModel(
            id=run.id,
            cells={
                "time": format_datetime_utc(_run_time(run)),
                "tool": _tool_label(run, tools_by_id),
                "tool_id": run.tool_id,
                "provider": _tool_provider_key(tool).lower(),
                "run_id": run.id,
                "source": _source_label(run, run_context=run_context),
                "orchestration_run_id": _orchestration_run_id(
                    run,
                    run_context=run_context,
                )
                or "-",
                "chain_id": _context_value(run_context, "chain_id"),
                "step_id": _context_value(run_context, "step_id"),
                "browser": _browser_run_label(run),
                "status": _status_label(run.status),
                "assignment_status": _assignment_status_label(assignment),
                "assignment_id": _assignment_id(assignment),
                "lease_state": _lease_state_label(run, assignment=assignment, now=now),
                "lease_expires_at": _lease_expires_label(run, assignment=assignment),
                "mode": run.target.mode.value,
                "strategy": run.target.strategy.value,
                "environment": run.target.environment.value,
                "worker": _display(run.worker_id),
                "worker_id": _display(run.worker_id),
                "duration": _run_duration_label(
                    run,
                    assignment=assignment,
                    now=now,
                ),
                "progress": _run_progress_label(
                    run,
                    tool=tools_by_id.get(run.tool_id),
                    assignment=assignment,
                    now=now,
                ),
                "result": _result_summary(run),
                "has_artifact": "yes" if artifact_count else "no",
                "retryable": "yes" if retryable else "no",
                "actions": _tool_run_actions(run),
                "route": _source_route(run, run_context=run_context),
                "trace": _trace_id(run, run_context=run_context),
                "trace_route": _trace_route(run, run_context=run_context),
                "search_text": _tool_run_search_text(
                    run,
                    tool=tool,
                    run_context=run_context,
                ),
            },
            status=run.status.value,
            tone=_tone_for_status(run.status),
        )
    )


def _tool_run_search_text(
    run: ToolRun,
    *,
    tool: Tool | None,
    run_context: Mapping[str, str] | None = None,
) -> str:
    return " ".join(
        item
        for item in (
            run.id,
            run.tool_id,
            tool.name if tool is not None else "",
            _display(run.worker_id),
            _source_label(run, run_context=run_context),
            _trace_id(run, run_context=run_context),
            _display(run.error_message),
        )
        if item
    )


def _tool_run_actions(run: ToolRun) -> str:
    if not run.is_terminal():
        return "Open / Trace / Cancel"
    if run.status in {ToolRunStatus.FAILED, ToolRunStatus.TIMED_OUT}:
        return "Open / Trace / Retry"
    return "Open / Trace"


def _normalize_query(query: ToolOperationsQuery | None) -> ToolOperationsQuery:
    if query is None:
        return ToolOperationsQuery()
    status = query.status.strip().lower() or "all"
    if status not in {
        "all",
        "active",
        "succeeded",
        "failed",
        "cancelled",
        "created",
        "queued",
        "dispatching",
        "running",
        "waiting",
        "long_running",
        "cancel_requested",
        "timed_out",
    }:
        status = "all"
    time_window = query.time_window.strip().lower() or "all"
    if time_window not in {"all", "24h"}:
        time_window = "all"
    mode = query.mode.strip().lower() or "all"
    if mode not in {"all", *(item.value for item in ToolMode)}:
        mode = "all"
    strategy = query.strategy.strip().lower() or "all"
    if strategy not in {"all", *(item.value for item in ToolExecutionStrategy)}:
        strategy = "all"
    environment = query.environment.strip().lower() or "all"
    if environment not in {"all", *(item.value for item in ToolEnvironment)}:
        environment = "all"
    has_artifact = query.has_artifact.strip().lower() or "all"
    if has_artifact not in {"all", "yes", "no"}:
        has_artifact = "all"
    retryable = query.retryable.strip().lower() or "all"
    if retryable not in {"all", "yes", "no"}:
        retryable = "all"
    return ToolOperationsQuery(
        status=status,
        time_window=time_window,
        search=_truncate(query.search.strip(), 120),
        tool_id=_filter_value(query.tool_id),
        provider=_filter_value(query.provider).lower(),
        mode=mode,
        strategy=strategy,
        environment=environment,
        worker_id=_filter_value(query.worker_id),
        has_artifact=has_artifact,
        retryable=retryable,
        limit=max(1, min(query.limit, 200)),
        offset=max(0, query.offset),
    )


def _filter_tool_runs(
    runs: list[ToolRun],
    *,
    query: ToolOperationsQuery,
    tools: list[Tool],
    assignment_by_run: dict[str, ToolRunAssignment],
    artifact_service: Any | None,
    now: datetime,
) -> list[ToolRun]:
    tools_by_id = _tool_lookup(tools)
    filtered = [
        run
        for run in runs
        if _tool_run_matches_status(
            run,
            query.status,
            assignment=assignment_by_run.get(run.id),
            now=now,
        )
        and _tool_run_matches_filters(
            run,
            query=query,
            tools_by_id=tools_by_id,
            artifact_service=artifact_service,
        )
    ]
    if query.time_window == "24h":
        cutoff = now - timedelta(hours=24)
        filtered = [run for run in filtered if _run_time(run) >= cutoff]
    return sorted(filtered, key=_run_time, reverse=True)


def _filter_value(value: str) -> str:
    normalized = value.strip()
    return normalized if normalized else "all"


def _tool_run_matches_status(
    run: ToolRun,
    status: str,
    *,
    assignment: ToolRunAssignment | None,
    now: datetime,
) -> bool:
    if status == "all":
        return True
    if status == "active":
        return not run.is_terminal()
    if status == "waiting":
        return not run.is_terminal() and run.status is not ToolRunStatus.RUNNING
    if status == "long_running":
        return (
            not run.is_terminal()
            and _duration_seconds(run, assignment=assignment, now=now)
            >= _LONG_RUNNING_SECONDS
        )
    if status == "succeeded":
        return run.status is ToolRunStatus.SUCCEEDED
    if status == "failed":
        return run.status in {ToolRunStatus.FAILED, ToolRunStatus.TIMED_OUT}
    if status == "cancelled":
        return run.status in {
            ToolRunStatus.CANCELLED,
            ToolRunStatus.CANCEL_REQUESTED,
        }
    return run.status.value == status


def _tool_run_matches_filters(
    run: ToolRun,
    *,
    query: ToolOperationsQuery,
    tools_by_id: dict[str, Tool],
    artifact_service: Any | None,
) -> bool:
    tool = tools_by_id.get(run.tool_id)
    if query.tool_id != "all" and query.tool_id != run.tool_id:
        return False
    if query.provider != "all" and query.provider != _tool_provider_key(tool).lower():
        return False
    if query.mode != "all" and query.mode != run.target.mode.value:
        return False
    if query.strategy != "all" and query.strategy != run.target.strategy.value:
        return False
    if query.environment != "all" and query.environment != run.target.environment.value:
        return False
    if query.worker_id != "all" and query.worker_id != _display(run.worker_id):
        return False
    artifact_count = len(_artifact_refs(run, artifact_service=artifact_service))
    if query.has_artifact == "yes" and artifact_count <= 0:
        return False
    if query.has_artifact == "no" and artifact_count > 0:
        return False
    is_retryable = run.status in {ToolRunStatus.FAILED, ToolRunStatus.TIMED_OUT}
    if query.retryable == "yes" and not is_retryable:
        return False
    if query.retryable == "no" and is_retryable:
        return False
    if query.search and not _tool_run_matches_search(
        run,
        query.search,
        tool=tool,
    ):
        return False
    return True


def _tool_run_matches_search(
    run: ToolRun,
    search: str,
    *,
    tool: Tool | None,
) -> bool:
    needle = search.strip().lower()
    if not needle:
        return True
    haystacks = (
        run.id,
        run.tool_id,
        tool.name if tool is not None else "",
        _display(run.worker_id),
        _source_label(run),
        _trace_id(run),
        _display(run.error_message),
    )
    return any(needle in item.lower() for item in haystacks if item)


def _paginate_runs(
    runs: list[ToolRun],
    *,
    query: ToolOperationsQuery,
) -> list[ToolRun]:
    return runs[query.offset : query.offset + query.limit]


def _dedupe_runs(runs: tuple[ToolRun, ...]) -> list[ToolRun]:
    seen: set[str] = set()
    unique: list[ToolRun] = []
    for run in runs:
        if run.id in seen:
            continue
        seen.add(run.id)
        unique.append(run)
    return unique


def _tool_runs_empty_state(query: ToolOperationsQuery) -> str:
    if (
        query.status != "all"
        or query.time_window != "all"
        or query.search
        or query.tool_id != "all"
        or query.provider != "all"
        or query.mode != "all"
        or query.strategy != "all"
        or query.environment != "all"
        or query.worker_id != "all"
        or query.has_artifact != "all"
        or query.retryable != "all"
    ):
        return "No tool runs match the current filters."
    return "No tool runs recorded."


def _tool_types_section(
    tools: list[Tool],
    runs: list[ToolRun],
) -> OperationsChartSectionModel:
    tools_by_id = _tool_lookup(tools)
    counts: Counter[str] = Counter()
    if runs:
        for run in runs:
            counts[run.tool_id] += 1
        total = len(runs)
        title = "Tool Call Share"
        segments = _tool_call_share_segments(counts, tools_by_id=tools_by_id)
    else:
        for tool in tools:
            counts[tool.kind.value] += 1
        total = len(tools)
        title = "Tool Types by Catalog"
        segments = tuple(
            OperationsChartSegmentModel(
                id=kind,
                label=_title_label(kind),
                value=count,
                tone=_tone_for_kind(kind),
            )
            for kind, count in sorted(counts.items())
            if count > 0
        )
    return OperationsChartSectionModel(
        id="tool_types",
        title=title,
        kind="donut",
        total=total,
        segments=segments,
    )


def _tool_call_share_segments(
    counts: Counter[str],
    *,
    tools_by_id: dict[str, Tool],
) -> tuple[OperationsChartSegmentModel, ...]:
    ranked = sorted(
        ((tool_id, count) for tool_id, count in counts.items() if count > 0),
        key=lambda item: (-item[1], _tool_label_from_id(item[0], tools_by_id)),
    )
    visible = ranked[:7]
    hidden = ranked[7:]
    segments = [
        OperationsChartSegmentModel(
            id=tool_id,
            label=_tool_display_name_from_id(tool_id, tools_by_id),
            value=count,
            tone=_tone_for_tool_rank(index),
        )
        for index, (tool_id, count) in enumerate(visible)
    ]
    hidden_total = sum(count for _, count in hidden)
    if hidden_total:
        segments.append(
            OperationsChartSegmentModel(
                id="__other_tools",
                label="Other Tools",
                value=hidden_total,
                tone="neutral",
            ),
        )
    return tuple(segments)


def _safe_tool_sources(tool_service: OperationsToolQueryPort) -> tuple[Any, ...]:
    list_sources = getattr(tool_service, "list_sources", None)
    if not callable(list_sources):
        return ()
    try:
        return tuple(list_sources() or ())
    except Exception:
        return ()


def _safe_tool_functions(tool_service: OperationsToolQueryPort) -> tuple[Any, ...]:
    list_functions = getattr(tool_service, "list_functions", None)
    if not callable(list_functions):
        return ()
    try:
        return tuple(list_functions() or ())
    except Exception:
        return ()


def _safe_tool_provider_backends(
    tool_service: OperationsToolQueryPort,
) -> tuple[Any, ...]:
    list_provider_backends = getattr(tool_service, "list_provider_backends", None)
    if not callable(list_provider_backends):
        return ()
    try:
        return tuple(list_provider_backends() or ())
    except Exception:
        return ()


def _safe_tool_provider_backend_readiness(
    tool_service: OperationsToolQueryPort,
    provider_backends: tuple[Any, ...],
) -> dict[str, dict[str, Any]]:
    check_readiness = getattr(tool_service, "check_provider_backend_readiness", None)
    if not callable(check_readiness):
        return {}
    readiness_by_backend_id: dict[str, dict[str, Any]] = {}
    for backend in provider_backends:
        backend_id = _record_text(backend, "backend_id")
        if not backend_id:
            continue
        try:
            readiness = check_readiness(backend)
        except Exception:
            continue
        payload = _readiness_payload(readiness)
        if payload:
            readiness_by_backend_id[backend_id] = payload
    return readiness_by_backend_id


def _safe_discovery_runs_by_source(
    tool_service: OperationsToolQueryPort,
    sources: tuple[Any, ...],
    *,
    limit: int,
) -> dict[str, tuple[Any, ...]]:
    list_runs = getattr(tool_service, "list_source_discovery_runs", None)
    if not callable(list_runs):
        return {}
    result: dict[str, tuple[Any, ...]] = {}
    for source in sources:
        source_id = _record_text(source, "source_id")
        if not source_id:
            continue
        try:
            result[source_id] = tuple(list_runs(source_id, limit=limit) or ())
        except Exception:
            result[source_id] = ()
    return result


def _source_tab_tone(sources: tuple[Any, ...], functions: tuple[Any, ...]) -> str:
    if any(_record_value(source, "status") == "error" for source in sources):
        return "danger"
    if any(
        _record_value(function, "status") in {"stale", "deprecated"}
        or not bool(getattr(function, "enabled", True))
        for function in functions
    ):
        return "warning"
    return "neutral"


def _source_health_section(
    sources: tuple[Any, ...],
    *,
    functions: tuple[Any, ...],
    discovery_runs_by_source: dict[str, tuple[Any, ...]],
) -> OperationsTableSectionModel:
    function_totals = Counter(_record_text(function, "source_id") for function in functions)
    active_totals = Counter(
        _record_text(function, "source_id")
        for function in functions
        if _record_value(function, "status") == "active"
        and bool(getattr(function, "enabled", True))
    )
    rows = []
    for source in sorted(sources, key=lambda item: _record_text(item, "source_id")):
        source_id = _record_text(source, "source_id")
        latest_discovery = _first(discovery_runs_by_source.get(source_id, ()))
        discovery_status = (
            _record_value(source, "last_discovery_status")
            or _record_value(latest_discovery, "status")
        )
        status = _record_value(source, "status") or "unknown"
        rows.append(
            OperationsTableRowModel(
                id=source_id,
                cells={
                    "source": source_id,
                    "kind": _title_label(_record_value(source, "kind") or "-"),
                    "endpoint": _source_endpoint_label(source),
                    "runtime": _source_runtime_dependency_label(source),
                    "status": _title_label(status),
                    "discovery": _title_label(discovery_status or "not_run"),
                    "tools_list": _source_tools_list_label(
                        source,
                        discovery_status,
                    ),
                    "functions": f"{active_totals[source_id]}/{function_totals[source_id]}",
                    "revision": str(getattr(source, "revision", "-")),
                    "updated": _record_datetime_label(source, "updated_at"),
                },
                status=status,
                tone=_source_health_tone(status, discovery_status),
            ),
        )
    return OperationsTableSectionModel(
        id="source_health",
        title="Source Health",
        columns=_columns(
            ("source", "Source"),
            ("kind", "Kind"),
            ("endpoint", "Endpoint"),
            ("runtime", "Runtime Dependency"),
            ("status", "Status"),
            ("discovery", "Discovery"),
            ("tools_list", "Tools/List"),
            ("functions", "Functions"),
            ("revision", "Revision"),
            ("updated", "Updated"),
        ),
        rows=tuple(rows),
        total=len(rows),
        empty_state="No Tool sources are registered.",
    )


def _source_endpoint_label(source: Any) -> str:
    provider = _source_provider_config(source)
    for key in ("endpoint_url", "base_url", "spec_location"):
        endpoint = _optional_mapping_text(provider, key)
        if endpoint:
            return _truncate(endpoint, 72)
    command = provider.get("command")
    if isinstance(command, tuple | list) and command:
        return _truncate(" ".join(str(item) for item in command), 72)
    return "-"


def _source_runtime_dependency_label(source: Any) -> str:
    if _is_browser_source(source):
        return "Browser profile context"
    runtime_requirements = tuple(
        str(item).strip()
        for item in getattr(source, "runtime_requirements", ())
        if str(item).strip()
    )
    return _truncate(", ".join(runtime_requirements), 72) if runtime_requirements else "-"


def _is_browser_source(source: Any) -> bool:
    if _record_text(source, "source_id") == "bundled.local_package.browser":
        return True
    config = getattr(source, "config", None)
    return (
        isinstance(config, Mapping)
        and config.get("namespace") == "browser"
        and config.get("package_kind") == "local_package"
    )


def _source_tools_list_label(source: Any, discovery_status: str | None) -> str:
    if _record_value(source, "kind") != "mcp":
        return "-"
    if discovery_status == "completed":
        return "Listed"
    if discovery_status == "failed":
        return "Failed"
    return "Not Run"


def _source_provider_config(source: Any) -> Mapping[str, Any]:
    config = getattr(source, "config", None)
    if not isinstance(config, Mapping):
        return {}
    provider = config.get("provider")
    return provider if isinstance(provider, Mapping) else {}


def _optional_mapping_text(mapping: Mapping[str, Any], key: str) -> str | None:
    value = mapping.get(key)
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _discovery_failures_section(
    sources: tuple[Any, ...],
    *,
    discovery_runs_by_source: dict[str, tuple[Any, ...]],
) -> OperationsTableSectionModel:
    source_by_id = {_record_text(source, "source_id"): source for source in sources}
    rows: list[OperationsTableRowModel] = []
    for source_id, runs in discovery_runs_by_source.items():
        for run in runs:
            if _record_value(run, "status") != "failed":
                continue
            rows.append(
                OperationsTableRowModel(
                    id=f"{source_id}:{_record_text(run, 'discovery_run_id')}",
                    cells={
                        "source": source_id,
                        "kind": _title_label(
                            _record_value(source_by_id.get(source_id), "kind") or "-",
                        ),
                        "time": _record_datetime_label(run, "discovered_at"),
                        "error": _truncate(_record_text(run, "error_message") or "-", 120),
                        "functions": str(getattr(run, "function_count", 0)),
                        "backends": str(getattr(run, "provider_backend_count", 0)),
                    },
                    status="failed",
                    tone="danger",
                ),
            )
    return OperationsTableSectionModel(
        id="discovery_failures",
        title="Discovery Failures",
        columns=_columns(
            ("source", "Source"),
            ("kind", "Kind"),
            ("time", "Time"),
            ("error", "Error"),
            ("functions", "Functions"),
            ("backends", "Backends"),
        ),
        rows=tuple(rows[:50]),
        total=len(rows),
        empty_state="No Tool discovery failures recorded.",
    )


def _function_catalog_section(functions: tuple[Any, ...]) -> OperationsTableSectionModel:
    rows: list[OperationsTableRowModel] = []
    for function in sorted(functions, key=lambda item: _record_text(item, "function_id")):
        status = _record_value(function, "status") or "unknown"
        enabled = bool(getattr(function, "enabled", True))
        if status == "active" and enabled:
            continue
        rows.append(
            OperationsTableRowModel(
                id=_record_text(function, "function_id"),
                cells={
                    "function": _record_text(function, "function_id"),
                    "source": _record_text(function, "source_id"),
                    "kind": _title_label(_record_value(function, "runtime_kind") or "-"),
                    "status": _title_label(status),
                    "enabled": "Yes" if enabled else "No",
                    "revision": str(getattr(function, "revision", "-")),
                    "schema": _truncate(_record_text(function, "schema_hash") or "-", 14),
                },
                status=status,
                tone="warning" if status in {"stale", "deprecated"} else "danger",
            ),
        )
    return OperationsTableSectionModel(
        id="function_catalog",
        title="Function Catalog Risks",
        columns=_columns(
            ("function", "Function"),
            ("source", "Source"),
            ("kind", "Kind"),
            ("status", "Status"),
            ("enabled", "Enabled"),
            ("revision", "Revision"),
            ("schema", "Schema"),
        ),
        rows=tuple(rows[:80]),
        total=len(rows),
        empty_state="No stale, deprecated, disabled, or deleted functions.",
    )


def _provider_backend_health_section(
    provider_backends: tuple[Any, ...],
    *,
    runs: list[ToolRun],
    readiness_by_backend_id: Mapping[str, dict[str, Any]],
    now: datetime,
) -> OperationsTableSectionModel:
    run_counts = _provider_backend_run_counts(runs, now=now)
    rows = [
        OperationsTableRowModel(
            id=_record_text(backend, "backend_id"),
            cells={
                "backend": _record_text(backend, "display_name")
                or _record_text(backend, "backend_id"),
                "capability": _title_label(_record_value(backend, "capability")),
                "credential": _provider_backend_credential_label(backend),
                "readiness": _provider_backend_readiness_label(
                    readiness_by_backend_id.get(_record_text(backend, "backend_id")),
                ),
                "calls_24h": str(
                    run_counts.get(_record_text(backend, "backend_id"), {}).get(
                        "calls_24h",
                        0,
                    ),
                ),
                "failures_24h": str(
                    run_counts.get(_record_text(backend, "backend_id"), {}).get(
                        "failures_24h",
                        0,
                    ),
                ),
                "runtime": _provider_backend_runtime_label(backend),
                "status": _provider_backend_status_label(backend),
            },
            status=_record_value(backend, "status") or "unknown",
            tone=_provider_backend_tone(
                backend,
                readiness_by_backend_id.get(_record_text(backend, "backend_id")),
            ),
        )
        for backend in provider_backends
        if _record_text(backend, "backend_id")
    ]
    return OperationsTableSectionModel(
        id="provider_backend_health",
        title="Provider Backend Health",
        columns=_columns(
            ("backend", "Backend"),
            ("capability", "Capability"),
            ("credential", "Credential"),
            ("readiness", "Readiness"),
            ("calls_24h", "Calls 24h"),
            ("failures_24h", "Failures 24h"),
            ("runtime", "Runtime"),
            ("status", "Status"),
        ),
        rows=tuple(rows),
        total=len(rows),
        empty_state="No provider backends are registered.",
    )


def _provider_backend_run_counts(
    runs: list[ToolRun],
    *,
    now: datetime,
) -> dict[str, dict[str, int]]:
    cutoff = now - timedelta(hours=24)
    counts: dict[str, dict[str, int]] = {}
    for run in runs:
        backend_id = _run_provider_backend_id(run)
        if backend_id is None:
            continue
        created_at = _run_created_at(run)
        if created_at is None or created_at < cutoff:
            continue
        bucket = counts.setdefault(
            backend_id,
            {"calls_24h": 0, "failures_24h": 0},
        )
        bucket["calls_24h"] += 1
        if run.status in {ToolRunStatus.FAILED, ToolRunStatus.TIMED_OUT}:
            bucket["failures_24h"] += 1
    return counts


def _run_provider_backend_id(run: ToolRun) -> str | None:
    value = run.metadata.get("provider_backend")
    if not isinstance(value, Mapping):
        return None
    backend_id = str(value.get("backend_id") or "").strip()
    return backend_id or None


def _run_created_at(run: ToolRun) -> datetime | None:
    created_at = getattr(run, "created_at", None)
    return created_at if isinstance(created_at, datetime) else None


def _provider_backend_status_label(backend: Any) -> str:
    status = _record_value(backend, "status") or "unknown"
    if not bool(getattr(backend, "enabled", True)):
        return "Disabled"
    return _title_label(status)


def _provider_backend_credential_label(backend: Any) -> str:
    bindings = _provider_backend_credential_bindings(backend)
    if not bindings:
        return "-"
    return ", ".join(bindings)


def _provider_backend_readiness_label(
    readiness: Mapping[str, Any] | None,
) -> str:
    if readiness is None:
        return "Unknown"
    if bool(readiness.get("ready")):
        return "Ready"
    status = _title_label(readiness.get("status") or "unknown")
    checks = readiness.get("checks")
    if isinstance(checks, list) and checks:
        ready = sum(
            1
            for check in checks
            if isinstance(check, Mapping) and bool(check.get("ready"))
        )
        return f"{status} ({ready}/{len(checks)})"
    return status


def _provider_backend_tone(
    backend: Any,
    readiness: Mapping[str, Any] | None,
) -> str:
    status = _record_value(backend, "status")
    if status in {"error", "deleted"}:
        return "danger"
    if status == "disabled" or not bool(getattr(backend, "enabled", True)):
        return "warning"
    if readiness is None:
        return "warning"
    return "success" if bool(readiness.get("ready")) else "warning"


def _provider_backend_runtime_label(backend: Any) -> str:
    runtime_ref = getattr(backend, "runtime_ref", None)
    if not isinstance(runtime_ref, Mapping):
        return "-"
    runtime_kind = str(runtime_ref.get("runtime_kind") or "").strip()
    ref = str(runtime_ref.get("ref") or "").strip()
    if runtime_kind and ref:
        return f"{runtime_kind}:{ref}"
    return runtime_kind or ref or "-"


def _provider_backend_credential_bindings(backend: Any) -> tuple[str, ...]:
    return tuple(
        binding_id
        for binding_id, _expected_kind in _provider_backend_credential_bindings_with_kind(
            backend,
        )
    )


def _provider_backend_credential_bindings_with_kind(
    backend: Any,
) -> tuple[tuple[str, str | None], ...]:
    pairs: list[tuple[str, str | None]] = []
    for requirement_set in _sequence(getattr(backend, "credential_requirements", ())):
        if not isinstance(requirement_set, Mapping):
            continue
        for requirement in _sequence(requirement_set.get("requirements")):
            if not isinstance(requirement, Mapping):
                continue
            slot = requirement.get("slot")
            if not isinstance(slot, Mapping):
                continue
            binding_id = str(slot.get("binding_id") or "").strip()
            if not binding_id:
                continue
            expected_kind = str(slot.get("expected_kind") or "").strip() or None
            pairs.append((binding_id, expected_kind))
    return tuple(dict.fromkeys(pairs))


def _cli_process_health_section(
    sources: tuple[Any, ...],
    *,
    functions: tuple[Any, ...],
) -> OperationsTableSectionModel:
    cli_source_ids = {
        _record_text(source, "source_id")
        for source in sources
        if _record_value(source, "kind") == "cli"
    }
    cli_source_ids.update(
        _record_text(function, "source_id")
        for function in functions
        if _record_value(function, "runtime_kind") == "cli"
    )
    source_by_id = {_record_text(source, "source_id"): source for source in sources}
    function_counts = Counter(
        _record_text(function, "source_id")
        for function in functions
        if _record_text(function, "source_id") in cli_source_ids
    )
    rows = [
        OperationsTableRowModel(
            id=source_id,
            cells={
                "source": source_id,
                "status": _title_label(_record_value(source_by_id.get(source_id), "status") or "unknown"),
                "functions": str(function_counts[source_id]),
                "policy": "Guided CLI",
            },
            status=_record_value(source_by_id.get(source_id), "status") or "unknown",
            tone=_source_health_tone(
                _record_value(source_by_id.get(source_id), "status") or "unknown",
                _record_value(source_by_id.get(source_id), "last_discovery_status"),
            ),
        )
        for source_id in sorted(cli_source_ids)
        if source_id
    ]
    return OperationsTableSectionModel(
        id="cli_process_health",
        title="CLI Process Health",
        columns=_columns(
            ("source", "Source"),
            ("status", "Status"),
            ("functions", "Functions"),
            ("policy", "Policy"),
        ),
        rows=tuple(rows),
        total=len(rows),
        empty_state="No CLI sources are registered.",
    )


def _auth_missing_section(
    tools: list[Tool],
    runs: list[ToolRun],
    *,
    tool_service: OperationsToolQueryPort | None = None,
    access_service: Any | None,
    now: datetime,
) -> OperationsTableSectionModel:
    failed_by_tool: Counter[str] = Counter(
        run.tool_id for run in runs if _looks_like_access_failure(run)
    )
    recent_by_tool: Counter[str] = Counter(
        run.tool_id for run in _runs_since(runs, since=now - timedelta(hours=24))
    )
    rows: list[OperationsTableRowModel] = []
    for tool in sorted(
        [
            item
            for item in tools
            if item.access_requirement_sets or item.credential_requirements
            or item.runtime_requirement_sets
        ],
        key=lambda item: item.id,
    ):
        readiness = _tool_readiness_risk(
            tool,
            tool_service=tool_service,
            access_service=access_service,
        )
        if readiness["ready"]:
            continue
        rows.append(
            OperationsTableRowModel(
                id=tool.id,
                cells={
                    "tool": tool.id,
                    "category": readiness["category"],
                    "status": readiness["status"],
                    "issue": readiness["reason"],
                    "required_access": readiness["requirements"],
                    "missing_access": readiness["missing"],
                    "affected_24h": str(recent_by_tool[tool.id]),
                    "access_failures": str(failed_by_tool[tool.id]),
                    "setup": readiness["setup"],
                    "action": readiness["action"],
                    "route": readiness["route"],
                },
                status=readiness["status"],
                tone=_readiness_risk_tone(readiness),
            ),
        )
    known_tool_ids = {tool.id for tool in tools}
    row_tool_ids = {row.id for row in rows}
    for tool_id, count in sorted(failed_by_tool.items()):
        if tool_id in row_tool_ids:
            continue
        if tool_id in known_tool_ids:
            tool = next((item for item in tools if item.id == tool_id), None)
            if tool is not None and tool.access_requirement_sets:
                continue
            issue = "access failure observed"
        else:
            issue = "access failure observed for unknown tool"
        if count <= 0:
            continue
        rows.append(
            OperationsTableRowModel(
                id=f"failed-access:{tool_id}",
                cells={
                    "tool": tool_id,
                    "status": "observed_failure",
                    "issue": issue,
                    "required_access": "-",
                    "missing_access": "-",
                    "affected_24h": str(recent_by_tool[tool_id]),
                    "access_failures": str(count),
                    "setup": "-",
                    "action": "Open Trace",
                    "route": "-",
                },
                status="blocked",
                tone="danger",
            ),
        )
    return OperationsTableSectionModel(
        id="auth_missing",
        title="Runtime Risk / Access",
        columns=_columns(
            ("tool", "Tool"),
            ("category", "Category"),
            ("status", "Status"),
            ("issue", "Issue"),
            ("required_access", "Required Access"),
            ("missing_access", "Missing Access"),
            ("affected_24h", "Affected (24h)"),
            ("access_failures", "Access Failures"),
            ("setup", "Setup"),
            ("action", "Action"),
        ),
        rows=tuple(rows[:50]),
        total=len(rows),
        view_all_route="/operations/tool?tab=risk",
        empty_state="No access or runtime readiness risks detected.",
    )


def _worker_pool_section(
    workers: list[ToolWorkerRegistration],
    *,
    active_runs: list[ToolRun],
    now: datetime,
) -> OperationsChartSectionModel:
    counts: Counter[str] = Counter()
    if workers:
        current_workers = [
            worker
            for worker in workers
            if _worker_registration_counts_in_pool(worker, now=now)
        ]
        for worker in current_workers:
            counts[_worker_registration_bucket(worker, now=now)] += 1
        specs = (
            ("idle", "Idle", "success"),
            ("active", "Active", "info"),
            ("busy", "Busy", "warning"),
            ("stale", "Stale", "warning"),
            ("lease_expired", "Lease Expired", "danger"),
        )
        return OperationsChartSectionModel(
            id="worker_pool",
            title="Worker Pool by Current Registrations",
            kind="donut",
            total=len(current_workers),
            segments=tuple(
                OperationsChartSegmentModel(
                    id=item_id,
                    label=label,
                    value=counts[item_id],
                    tone=tone,
                )
                for item_id, label, tone in specs
                if counts[item_id] > 0
            ),
        )
    for run in active_runs:
        counts[_worker_bucket(run, now=now)] += 1
    specs = (
        ("queued", "Queued", "warning"),
        ("dispatching", "Dispatching", "info"),
        ("running", "Running", "success"),
        ("cancel_requested", "Cancel Requested", "warning"),
        ("lease_expired", "Lease Expired", "danger"),
        ("created", "Created", "neutral"),
    )
    return OperationsChartSectionModel(
        id="worker_pool",
        title="Worker Pool by Active Runs",
        kind="donut",
        total=len(active_runs),
        segments=tuple(
            OperationsChartSegmentModel(
                id=item_id,
                label=label,
                value=counts[item_id],
                tone=tone,
            )
            for item_id, label, tone in specs
            if counts[item_id] > 0
        ),
    )


def _workers_section(
    workers: list[ToolWorkerRegistration],
    *,
    active_runs: list[ToolRun],
    runs: list[ToolRun],
    assignment_by_run: dict[str, ToolRunAssignment],
    now: datetime,
) -> OperationsTableSectionModel:
    rows: list[OperationsTableRowModel] = []
    current_run_by_worker = {
        run.worker_id: run.id
        for run in active_runs
        if run.worker_id is not None and run.worker_id.strip()
    }

    if workers:
        for worker in sorted(workers, key=lambda item: item.id):
            bucket = _worker_registration_bucket(worker, now=now)
            status, tone = _worker_registration_status(bucket)
            rows.append(
                OperationsTableRowModel(
                    id=worker.id,
                    cells={
                        "worker": worker.id,
                        "status": status,
                        "last_heartbeat": format_datetime_utc(worker.heartbeat_at),
                        "lease_expires_at": (
                            format_datetime_utc(worker.lease_expires_at)
                            if worker.lease_expires_at is not None
                            else "-"
                        ),
                        "current_run": current_run_by_worker.get(worker.id, "-"),
                        "load": f"{worker.current_in_flight}/{worker.max_in_flight}",
                        "load_percent": _percent_label(
                            worker.current_in_flight,
                            max(worker.max_in_flight, 1),
                        ),
                        "running": str(
                            sum(1 for run in active_runs if run.worker_id == worker.id),
                        ),
                        "success_rate": _worker_success_rate_label(
                            worker.id,
                            runs=runs,
                        ),
                        "avg_duration": _worker_avg_duration_label(
                            worker.id,
                            runs=runs,
                            assignment_by_run=assignment_by_run,
                            now=now,
                        ),
                        "runtimes": _worker_runtime_count(worker),
                        "providers": _worker_provider_summary(worker),
                        "capabilities": _worker_capability_summary(worker),
                    },
                    status=status,
                    tone=tone,
                ),
            )
    else:
        for run in sorted(active_runs, key=lambda item: item.created_at, reverse=True):
            status = _status_label(run.status)
            rows.append(
                OperationsTableRowModel(
                    id=run.worker_id or run.id,
                    cells={
                        "worker": _display(run.worker_id),
                        "status": status,
                        "last_heartbeat": (
                            format_datetime_utc(run.heartbeat_at)
                            if run.heartbeat_at is not None
                            else "-"
                        ),
                        "lease_expires_at": _lease_expires_label(run, assignment=None),
                        "current_run": run.id,
                        "load": "-",
                        "load_percent": "-",
                        "running": "1",
                        "success_rate": _worker_success_rate_label(
                            run.worker_id or "",
                            runs=runs,
                        ),
                        "avg_duration": _worker_avg_duration_label(
                            run.worker_id or "",
                            runs=runs,
                            assignment_by_run=assignment_by_run,
                            now=now,
                        ),
                        "runtimes": "-",
                        "providers": "-",
                        "capabilities": "-",
                    },
                    status=status,
                    tone=_tone_for_status(run.status),
                ),
            )

    return OperationsTableSectionModel(
        id="workers",
        title="Workers",
        columns=_columns(
            ("worker", "Worker ID"),
            ("status", "Status"),
            ("last_heartbeat", "Last Heartbeat"),
            ("lease_expires_at", "Lease Expires At"),
            ("current_run", "Current Run"),
            ("load", "Worker Load"),
            ("load_percent", "Load"),
            ("running", "Running"),
            ("success_rate", "Success Rate"),
            ("avg_duration", "Avg Duration"),
            ("runtimes", "Runtime Count"),
            ("providers", "Providers"),
            ("capabilities", "Capabilities"),
        ),
        rows=tuple(rows[:50]),
        total=len(rows),
        view_all_route="/operations/tool?tab=workers",
        empty_state="No tool workers registered.",
    )


def _tool_queue_section(
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
    tools_by_id = _tool_lookup(tools)
    worker_group_counts, _ = _worker_group_counts(
        runs=active_runs,
        assignments=assignments,
        tools_by_id=tools_by_id,
        concurrency_policy=concurrency_policy,
    )
    grouped: dict[str, list[ToolRun]] = {}
    for run in queue_runs:
        grouped.setdefault(
            _run_blocker_reason(
                run,
                assignment=assignment_by_run.get(run.id),
                workers=workers,
                worker_group_counts=worker_group_counts,
                tools_by_id=tools_by_id,
                concurrency_policy=concurrency_policy,
                now=now,
            ),
            [],
        ).append(run)
    total = len(queue_runs)
    rows = []
    for reason, reason_runs in sorted(
        grouped.items(),
        key=lambda item: (-len(item[1]), item[0]),
    ):
        oldest = min((run.created_at for run in reason_runs), default=None)
        rows.append(
            OperationsTableRowModel(
                id=reason,
                cells={
                    "reason": reason,
                    "count": str(len(reason_runs)),
                    "oldest": _queue_oldest_label(
                        reason_runs,
                        assignment_by_run=assignment_by_run,
                        now=now,
                    )
                    if reason_runs
                    else _age_label(oldest, now=now),
                    "percent": _percent_label(len(reason_runs), total),
                },
                status=reason,
                tone=_queue_reason_tone(reason),
            ),
        )
    return OperationsTableSectionModel(
        id="tool_queue",
        title="Tool Queue",
        columns=_columns(
            ("reason", "Reason"),
            ("count", "Count"),
            ("oldest", "Oldest Wait"),
            ("percent", "% of Queue"),
        ),
        rows=tuple(rows),
        total=total,
        view_all_route="/operations/tool?tab=queue",
        empty_state="No waiting tool runs.",
    )


def _tool_queue_runs_section(
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
    rows = _waiting_run_rows(
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
        columns=_columns(
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


def _tool_waiting_io_section(
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
    rows = tuple(
        row
        for row in _waiting_run_rows(
            queue_runs,
            active_runs=active_runs,
            tools=tools,
            workers=workers,
            assignments=assignments,
            assignment_by_run=assignment_by_run,
            concurrency_policy=concurrency_policy,
            now=now,
        )
        if _is_waiting_io_reason(row.cells.get("reason", ""))
    )
    return OperationsTableSectionModel(
        id="tool_waiting_io",
        title="Waiting IO",
        columns=_columns(
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


def _waiting_run_rows(
    queue_runs: list[ToolRun],
    *,
    active_runs: list[ToolRun],
    tools: list[Tool],
    workers: list[ToolWorkerRegistration],
    assignments: list[ToolRunAssignment],
    assignment_by_run: dict[str, ToolRunAssignment],
    concurrency_policy: ToolRunConcurrencyPolicy,
    now: datetime,
) -> tuple[OperationsTableRowModel, ...]:
    tools_by_id = _tool_lookup(tools)
    worker_group_counts, _ = _worker_group_counts(
        runs=active_runs,
        assignments=assignments,
        tools_by_id=tools_by_id,
        concurrency_policy=concurrency_policy,
    )
    rows: list[OperationsTableRowModel] = []
    for run in sorted(queue_runs, key=lambda item: item.created_at):
        tool = tools_by_id.get(run.tool_id)
        reason = _run_blocker_reason(
            run,
            assignment=assignment_by_run.get(run.id),
            workers=workers,
            worker_group_counts=worker_group_counts,
            tools_by_id=tools_by_id,
            concurrency_policy=concurrency_policy,
            now=now,
        )
        rows.append(
            OperationsTableRowModel(
                id=run.id,
                cells={
                    "run_id": run.id,
                    "tool": _tool_label(run, tools_by_id),
                    "source": _source_label(run),
                    "priority": _run_priority_label(run),
                    "wait_time": _age_label(run.created_at, now=now),
                    "reason": reason,
                    "external_service": _provider_history_label(_tool_provider_key(tool)),
                    "timeout": _duration_label(tool.execution_policy.timeout_seconds)
                    if tool is not None
                    else "-",
                    "actions": "Open / Trace / Cancel",
                    "route": _source_route(run),
                    "trace": _trace_id(run),
                    "trace_route": _trace_route(run),
                },
                status=reason,
                tone=_queue_reason_tone(reason),
            ),
        )
    return tuple(rows[:50])


def _capability_limits_section(
    *,
    tools: list[Tool],
    runs: list[ToolRun],
    workers: list[ToolWorkerRegistration],
    assignments: list[ToolRunAssignment],
    concurrency_policy: ToolRunConcurrencyPolicy,
    now: datetime,
) -> OperationsTableSectionModel:
    tools_by_id = _tool_lookup(tools)
    active_runs = [run for run in runs if not run.is_terminal()]
    worker_group_counts, assigned_run_ids = _worker_group_counts(
        runs=active_runs,
        assignments=assignments,
        tools_by_id=tools_by_id,
        concurrency_policy=concurrency_policy,
    )
    active_by_group = _sum_group_counts(worker_group_counts)
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
        group = _concurrency_group_for_run(
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
            _capability_limit_row(
                group=group,
                catalog_count=catalog_by_group[key],
                active=active_by_group[key],
                waiting=waiting_by_group[key],
                workers=workers,
                worker_group_counts=worker_group_counts,
                now=now,
            ),
        )

    if default_catalog_count or default_active or default_waiting:
        default_group = ToolRunConcurrencyGroup(
            key="tool:*",
            max_in_flight=concurrency_policy.default_max_in_flight,
        )
        rows.append(
            _capability_limit_row(
                group=default_group,
                catalog_count=default_catalog_count,
                active=default_active,
                waiting=default_waiting,
                workers=workers,
                worker_group_counts=worker_group_counts,
                now=now,
            ),
        )

    return OperationsTableSectionModel(
        id="capability_limits",
        title="Capability Concurrency",
        columns=_columns(
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


def _capability_limit_row(
    *,
    group: ToolRunConcurrencyGroup,
    catalog_count: int,
    active: int,
    waiting: int,
    workers: list[ToolWorkerRegistration],
    worker_group_counts: dict[str, Counter[str]],
    now: datetime,
) -> OperationsTableRowModel:
    capacity = _group_worker_capacity(group, workers=workers, now=now)
    available_workers = _available_worker_count_for_group(
        group,
        workers=workers,
        worker_group_counts=worker_group_counts,
        now=now,
    )
    if waiting and capacity <= 0:
        state = "no worker"
        tone = "danger"
        reason = "waiting for online worker"
    elif waiting and available_workers <= 0:
        state = "saturated"
        tone = "warning"
        reason = "waiting for capability capacity"
    elif active:
        state = "active"
        tone = "info"
        reason = "capacity available" if available_workers else "worker slots full"
    else:
        state = "ready"
        tone = "success"
        reason = "capacity available" if capacity else "no online worker"
    return OperationsTableRowModel(
        id=group.key,
        cells={
            "capability": _capability_label(group.key),
            "capability_key": group.key,
            "limit": f"{group.max_in_flight}/worker",
            "capacity": str(capacity),
            "active": str(active),
            "waiting": str(waiting),
            "available_workers": str(available_workers),
            "tools": str(catalog_count),
            "state": _title_label(state),
            "reason": reason,
        },
        status=state,
        tone=tone,
    )


def _provider_limits_section(
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
    snapshots = _provider_metric_snapshots(
        workers=workers,
        runtime_metrics=runtime_metrics,
        now=now,
    )
    grouped: dict[str, dict[str, Any]] = {}
    for source, snapshot in _provider_limiter_configuration_snapshots(
        workers=workers,
        runtime_registry=runtime_registry,
        now=now,
    ):
        for provider_key, config in _provider_limiter_configurations(snapshot):
            bucket = grouped.setdefault(provider_key, _provider_metric_bucket())
            bucket["sources"].add(source)
            bucket["runtime_keys"].update(config.get("runtime_keys", set()))
            limit = config.get("limit")
            if limit is not None:
                limit_value = _int_value(limit)
                bucket["configured_capacity"] += limit_value
                bucket["configured_limit_entries"].add(("proc", limit_value))
                bucket["process_limits"].add(limit_value)
    for provider_key, config in _provider_local_capacity_configurations(
        tools=tools,
        runs=runs,
        workers=workers,
        assignments=assignments,
        concurrency_policy=concurrency_policy,
        now=now,
    ):
        bucket = grouped.setdefault(provider_key, _provider_metric_bucket())
        bucket["sources"].update(config.get("sources", set()))
        bucket["runtime_keys"].update(config.get("runtime_keys", set()))
        bucket["configured_capacity"] += _int_value(config.get("capacity"))
        bucket["active"] += _float(config.get("active"))
        bucket["waiting"] += _float(config.get("waiting"))
        limit = config.get("limit")
        if limit is not None:
            bucket["configured_limit_entries"].add(("worker", _int_value(limit)))
    for source, snapshot in snapshots:
        for item in _metric_items(snapshot, "gauges"):
            name = _optional_str(item.get("name"))
            provider_key = _metric_provider_key(item)
            if provider_key is None:
                continue
            bucket = grouped.setdefault(provider_key, _provider_metric_bucket())
            bucket["sources"].add(source)
            if name == _TOOL_PROVIDER_LIMITER_ACTIVE:
                bucket["active"] += _float(item.get("value"))
            elif name == _TOOL_PROVIDER_LIMITER_WAITERS:
                bucket["waiting"] += _float(item.get("value"))
        for item in _metric_items(snapshot, "timings"):
            if _optional_str(item.get("name")) != _TOOL_PROVIDER_LIMITER_WAIT_SECONDS:
                continue
            provider_key = _metric_provider_key(item)
            if provider_key is None:
                continue
            bucket = grouped.setdefault(provider_key, _provider_metric_bucket())
            bucket["sources"].add(source)
            count = _int_value(item.get("count"))
            total = _float(item.get("total_seconds"))
            bucket["wait_count"] += count
            bucket["total_wait_seconds"] += total
            bucket["max_wait_seconds"] = max(
                bucket["max_wait_seconds"],
                _float(item.get("max_seconds")),
            )

    rows = tuple(
        _provider_limit_row(provider_key, bucket)
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
        columns=_columns(
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


def _provider_metric_snapshots(
    *,
    workers: list[ToolWorkerRegistration],
    runtime_metrics: Any | None,
    now: datetime,
) -> tuple[tuple[str, dict[str, Any]], ...]:
    snapshots: list[tuple[str, dict[str, Any]]] = []
    local_snapshot = _runtime_metrics_snapshot(runtime_metrics)
    if local_snapshot:
        snapshots.append(("api-process", local_snapshot))
    for worker in workers:
        if not _worker_is_online(worker, now=now):
            continue
        snapshot = worker.capabilities_payload.get("runtime_metrics")
        if isinstance(snapshot, dict):
            snapshots.append((worker.id, snapshot))
    return tuple(snapshots)


def _runtime_metrics_snapshot(runtime_metrics: Any | None) -> dict[str, Any]:
    snapshot = getattr(runtime_metrics, "snapshot", None)
    if not callable(snapshot):
        return {}
    try:
        payload = snapshot(prefixes=(_TOOL_PROVIDER_LIMITER_PREFIX,))
    except Exception:
        return {}
    return dict(payload) if isinstance(payload, dict) else {}


def _provider_metric_bucket() -> dict[str, Any]:
    return {
        "configured_capacity": 0,
        "configured_limit_entries": set(),
        "process_limits": set(),
        "runtime_keys": set(),
        "active": 0.0,
        "waiting": 0.0,
        "wait_count": 0,
        "total_wait_seconds": 0.0,
        "max_wait_seconds": 0.0,
        "sources": set(),
    }


def _provider_limit_row(
    provider_key: str,
    bucket: dict[str, Any],
) -> OperationsTableRowModel:
    configured_limit_entries = {
        (str(scope), _int_value(limit))
        for scope, limit in bucket.get("configured_limit_entries", set())
        if _int_value(limit) > 0
    }
    configured_capacity = max(_int_value(bucket.get("configured_capacity")), 0)
    active = max(int(round(_float(bucket.get("active")))), 0)
    waiting = max(int(round(_float(bucket.get("waiting")))), 0)
    wait_count = max(_int_value(bucket.get("wait_count")), 0)
    total_wait = _float(bucket.get("total_wait_seconds"))
    max_wait = _float(bucket.get("max_wait_seconds"))
    avg_wait = total_wait / wait_count if wait_count else 0.0
    state, tone = _provider_limit_state(
        active=active,
        waiting=waiting,
        has_config_drift=len(bucket.get("process_limits", set())) > 1,
    )
    sources = sorted(str(item) for item in bucket.get("sources", set()) if item)
    return OperationsTableRowModel(
        id=provider_key,
        cells={
            "provider": _provider_label(provider_key),
            "provider_key": provider_key,
            "state": state,
            "limit": _provider_limit_label(configured_limit_entries),
            "capacity": (
                f"{active}/{configured_capacity}"
                if configured_capacity
                else f"{active}/-"
            ),
            "active": str(active),
            "waiting": str(waiting),
            "runtimes": str(len(bucket.get("runtime_keys", set()))),
            "wait_count": str(wait_count),
            "avg_wait": _seconds_label(avg_wait),
            "max_wait": _seconds_label(max_wait),
            "total_wait": _seconds_label(total_wait),
            "sources": _join_values(tuple(sources)),
        },
        status=state,
        tone=tone,
    )


def _provider_limit_state(
    *,
    active: int,
    waiting: int,
    has_config_drift: bool = False,
) -> tuple[str, str]:
    if waiting > 0:
        return "Waiting", "warning"
    if has_config_drift:
        return "Config Drift", "warning"
    if active > 0:
        return "Active", "info"
    return "Ready", "success"


def _provider_label(provider_key: str) -> str:
    if provider_key.startswith("provider:"):
        return provider_key.removeprefix("provider:")
    if provider_key.startswith("openapi:"):
        return f"openapi / {provider_key.removeprefix('openapi:')}"
    if provider_key.startswith("mcp:"):
        return f"mcp / {provider_key.removeprefix('mcp:')}"
    return provider_key


def _metric_items(snapshot: dict[str, Any], group: str) -> tuple[dict[str, Any], ...]:
    items = snapshot.get(group)
    if not isinstance(items, list):
        return ()
    return tuple(item for item in items if isinstance(item, dict))


def _metric_provider_key(item: dict[str, Any]) -> str | None:
    labels = item.get("labels")
    if not isinstance(labels, dict):
        return None
    return _optional_str(labels.get("provider_key"))


def _provider_limiter_configuration_snapshots(
    *,
    workers: list[ToolWorkerRegistration],
    runtime_registry: Any | None,
    now: datetime,
) -> tuple[tuple[str, dict[str, Any]], ...]:
    snapshots: list[tuple[str, dict[str, Any]]] = []
    local_snapshot = _runtime_registry_snapshot(runtime_registry)
    if local_snapshot:
        snapshots.append(("api-process", local_snapshot))
    for worker in workers:
        if not _worker_is_online(worker, now=now):
            continue
        snapshot = worker.capabilities_payload.get("runtime_registry")
        if isinstance(snapshot, dict):
            snapshots.append((worker.id, snapshot))
    return tuple(snapshots)


def _runtime_registry_snapshot(runtime_registry: Any | None) -> dict[str, Any]:
    snapshot = getattr(runtime_registry, "snapshot", None)
    if callable(snapshot):
        try:
            payload = snapshot()
        except Exception:
            return {}
        return dict(payload) if isinstance(payload, dict) else {}
    registrations_fn = getattr(runtime_registry, "registrations", None)
    if not callable(registrations_fn):
        return {}
    try:
        registrations = registrations_fn()
    except Exception:
        return {}
    return {
        "registrations": [
            {
                "runtime_key": getattr(registration, "runtime_key", None),
                "concurrency_key": getattr(registration, "concurrency_key", None),
                "max_concurrency": getattr(registration, "max_concurrency", None),
            }
            for registration in registrations
        ],
    }


def _provider_limiter_configurations(
    snapshot: dict[str, Any],
) -> tuple[tuple[str, dict[str, Any]], ...]:
    registrations = snapshot.get("registrations")
    if not isinstance(registrations, list):
        return ()
    grouped: dict[str, dict[str, Any]] = {}
    for registration in registrations:
        if not isinstance(registration, dict):
            continue
        runtime_key = _optional_str(registration.get("runtime_key"))
        concurrency_key = _optional_str(registration.get("concurrency_key"))
        provider_key = concurrency_key or runtime_key
        if provider_key is None:
            continue
        limit = registration.get("max_concurrency")
        bucket = grouped.setdefault(provider_key, {"runtime_keys": set(), "limit": None})
        if runtime_key is not None:
            bucket["runtime_keys"].add(runtime_key)
        if limit is not None:
            bucket["limit"] = max(
                _int_value(bucket.get("limit")),
                _int_value(limit),
            )
    return tuple(sorted(grouped.items()))


def _provider_local_capacity_configurations(
    *,
    tools: list[Tool],
    runs: list[ToolRun],
    workers: list[ToolWorkerRegistration],
    assignments: list[ToolRunAssignment],
    concurrency_policy: ToolRunConcurrencyPolicy,
    now: datetime,
) -> tuple[tuple[str, dict[str, Any]], ...]:
    tools_by_id = _tool_lookup(tools)
    active_runs = [run for run in runs if not run.is_terminal()]
    _, assigned_run_ids = _worker_group_counts(
        runs=active_runs,
        assignments=assignments,
        tools_by_id=tools_by_id,
        concurrency_policy=concurrency_policy,
    )
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for tool in tools:
        if ToolMode.BACKGROUND not in tool.execution_support.supported_modes:
            continue
        provider_key = _tool_provider_key(tool)
        group = concurrency_policy.group_for_tool(tool)
        if not _is_provider_limiter_key(provider_key) or not group.key.startswith(
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
        if group.max_in_flight > _int_value(bucket.get("limit")):
            bucket["limit"] = group.max_in_flight
            bucket["group"] = group

    for run in active_runs:
        tool = tools_by_id.get(run.tool_id)
        if tool is None:
            continue
        provider_key = _tool_provider_key(tool)
        group = _concurrency_group_for_run(
            run,
            tools_by_id=tools_by_id,
            concurrency_policy=concurrency_policy,
        )
        if not _is_provider_limiter_key(provider_key) or not group.key.startswith(
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

    online_workers = _online_workers(workers, now=now)
    worker_sources = {worker.id for worker in online_workers}
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
                    "capacity": _group_worker_capacity(
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


def _is_provider_limiter_key(provider_key: str) -> bool:
    return provider_key.startswith(("provider:", "openapi:", "mcp:"))


def _provider_limit_label(limit_entries: set[tuple[str, int]]) -> str:
    if not limit_entries:
        return "-"
    if len(limit_entries) == 1:
        scope, limit = next(iter(limit_entries))
        return f"{limit}/{scope}"
    return "mixed"


def _provider_history_section(
    *,
    tools: list[Tool],
    runs: list[ToolRun],
    assignment_by_run: dict[str, ToolRunAssignment],
    now: datetime,
) -> OperationsTableSectionModel:
    tools_by_id = _tool_lookup(tools)
    grouped: dict[str, dict[str, Any]] = {}
    for tool in tools:
        bucket = grouped.setdefault(_tool_provider_key(tool), _provider_history_bucket())
        bucket["tools"].add(tool.id)

    for run in runs:
        tool = tools_by_id.get(run.tool_id)
        bucket = grouped.setdefault(_tool_provider_key(tool), _provider_history_bucket())
        bucket["tools"].add(run.tool_id)
        bucket["runs"] += 1
        bucket["last_run"] = _latest_datetime(bucket.get("last_run"), _run_time(run))
        if run.is_terminal():
            bucket["terminal"] += 1
            if run.status is ToolRunStatus.SUCCEEDED:
                bucket["succeeded"] += 1
            elif run.status in {ToolRunStatus.FAILED, ToolRunStatus.TIMED_OUT}:
                bucket["failures"] += 1
            elif run.status is ToolRunStatus.CANCELLED:
                bucket["cancelled"] += 1
            duration_seconds = _terminal_run_duration_seconds(run)
            if duration_seconds is not None:
                bucket["duration_count"] += 1
                bucket["total_duration_seconds"] += duration_seconds
                bucket["max_duration_seconds"] = max(
                    bucket["max_duration_seconds"],
                    duration_seconds,
                )
        else:
            bucket["active"] += 1
            bucket["active_duration_seconds"] = max(
                bucket["active_duration_seconds"],
                _duration_seconds(
                    run,
                    assignment=assignment_by_run.get(run.id),
                    now=now,
                ),
            )

    rows = tuple(
        _provider_history_row(provider_key, bucket)
        for provider_key, bucket in sorted(
            grouped.items(),
            key=lambda item: (-int(item[1]["runs"]), _provider_history_label(item[0])),
        )
        if bucket["tools"] or bucket["runs"]
    )
    return OperationsTableSectionModel(
        id="provider_history",
        title="Provider History",
        columns=_columns(
            ("provider", "Provider"),
            ("state", "State"),
            ("tools", "Tools"),
            ("runs", "Runs"),
            ("active", "Active"),
            ("failures", "Failures"),
            ("success_rate", "Success Rate"),
            ("avg_duration", "Avg Duration"),
            ("max_duration", "Max Duration"),
            ("last_run", "Last Run"),
        ),
        rows=rows,
        total=len(rows),
        view_all_route="/operations/tool?tab=provider_history",
        empty_state="No provider runtime history observed.",
    )


def _provider_history_bucket() -> dict[str, Any]:
    return {
        "tools": set(),
        "runs": 0,
        "active": 0,
        "terminal": 0,
        "succeeded": 0,
        "failures": 0,
        "cancelled": 0,
        "duration_count": 0,
        "total_duration_seconds": 0,
        "max_duration_seconds": 0,
        "active_duration_seconds": 0,
        "last_run": None,
    }


def _provider_history_row(
    provider_key: str,
    bucket: dict[str, Any],
) -> OperationsTableRowModel:
    tool_count = len(bucket.get("tools", set()))
    runs = _int_value(bucket.get("runs"))
    active = _int_value(bucket.get("active"))
    terminal = _int_value(bucket.get("terminal"))
    succeeded = _int_value(bucket.get("succeeded"))
    failures = _int_value(bucket.get("failures"))
    duration_count = _int_value(bucket.get("duration_count"))
    total_duration_seconds = _int_value(bucket.get("total_duration_seconds"))
    avg_duration_seconds = (
        total_duration_seconds / duration_count if duration_count else None
    )
    state, tone = _provider_history_state(
        runs=runs,
        active=active,
        failures=failures,
    )
    last_run = bucket.get("last_run")
    return OperationsTableRowModel(
        id=provider_key,
        cells={
            "provider": _provider_history_label(provider_key),
            "provider_key": provider_key,
            "state": state,
            "tools": str(tool_count),
            "runs": str(runs),
            "active": str(active),
            "failures": str(failures),
            "success_rate": _percent_label(succeeded, terminal) if terminal else "-",
            "avg_duration": (
                _duration_label(int(round(avg_duration_seconds)))
                if avg_duration_seconds is not None
                else "-"
            ),
            "max_duration": (
                _duration_label(_int_value(bucket.get("max_duration_seconds")))
                if duration_count
                else "-"
            ),
            "last_run": (
                format_datetime_utc(last_run) if isinstance(last_run, datetime) else "-"
            ),
        },
        status=state,
        tone=tone,
    )


def _provider_history_state(
    *,
    runs: int,
    active: int,
    failures: int,
) -> tuple[str, str]:
    if failures > 0:
        return "Warning", "warning"
    if active > 0:
        return "Active", "info"
    if runs > 0:
        return "Healthy", "success"
    return "Ready", "neutral"


def _tool_provider_key(tool: Tool | None) -> str:
    if tool is None:
        return "unknown"
    runtime_key = tool.resolved_runtime_key().strip()
    runtime_key_lower = runtime_key.lower()
    for prefix in ("openapi.", "mcp."):
        if runtime_key_lower.startswith(prefix):
            parts = runtime_key.split(".")
            if len(parts) >= 2 and parts[1].strip():
                return f"{prefix.removesuffix('.')}:{parts[1].strip().lower()}"
    for tag in tool.tags:
        if tag.startswith("provider:") and tag.removeprefix("provider:").strip():
            return f"provider:{tag.removeprefix('provider:').strip().lower()}"
    provider_tag = next((tag for tag in tool.tags if tag in _KNOWN_PROVIDER_TAGS), None)
    if provider_tag is not None:
        return f"provider:{provider_tag}"
    if runtime_key_lower.startswith("openai_") or tool.id.lower().startswith("openai_"):
        return "provider:openai"
    if tool.definition_origin is ToolDefinitionOrigin.LOCAL_DISCOVERY:
        return "local"
    if tool.definition_origin is ToolDefinitionOrigin.REMOTE_DISCOVERY:
        return "remote"
    return tool.definition_origin.value or "unknown"


def _provider_history_label(provider_key: str) -> str:
    if provider_key.startswith("provider:"):
        return provider_key.removeprefix("provider:")
    if provider_key.startswith("openapi:"):
        return f"openapi / {provider_key.removeprefix('openapi:')}"
    if provider_key.startswith("mcp:"):
        return f"mcp / {provider_key.removeprefix('mcp:')}"
    if provider_key in {"local", "remote", "unknown"}:
        return _title_label(provider_key)
    return provider_key


def _terminal_run_duration_seconds(run: ToolRun) -> int | None:
    if not run.is_terminal() or run.started_at is None or run.completed_at is None:
        return None
    return max(
        int(
            (
                coerce_utc_datetime(run.completed_at)
                - coerce_utc_datetime(run.started_at)
            ).total_seconds(),
        ),
        0,
    )


def _percentile_int(values: list[int], percentile: int) -> int:
    if not values:
        return 0
    ordered = sorted(values)
    pct = min(max(int(percentile), 0), 100)
    index = round((pct / 100) * (len(ordered) - 1))
    return ordered[index]


def _throughput_label(count_24h: int) -> str:
    per_hour = count_24h / 24
    if per_hour <= 0:
        return "0/h"
    if per_hour < 1:
        return f"{per_hour:.1f}/h"
    return f"{int(round(per_hour))}/h"


def _latest_datetime(
    left: object | None,
    right: datetime,
) -> datetime:
    if not isinstance(left, datetime):
        return right
    return max(coerce_utc_datetime(left), coerce_utc_datetime(right))


def _run_blockers_section(
    active_runs: list[ToolRun],
    *,
    tools: list[Tool],
    workers: list[ToolWorkerRegistration],
    assignments: list[ToolRunAssignment],
    assignment_by_run: dict[str, ToolRunAssignment],
    concurrency_policy: ToolRunConcurrencyPolicy,
    now: datetime,
) -> OperationsTableSectionModel:
    tools_by_id = _tool_lookup(tools)
    worker_group_counts, _ = _worker_group_counts(
        runs=active_runs,
        assignments=assignments,
        tools_by_id=tools_by_id,
        concurrency_policy=concurrency_policy,
    )
    rows = tuple(
        _run_blocker_row(
            run,
            tools_by_id=tools_by_id,
            assignment=assignment_by_run.get(run.id),
            workers=workers,
            worker_group_counts=worker_group_counts,
            concurrency_policy=concurrency_policy,
            now=now,
        )
        for run in sorted(active_runs, key=_run_time, reverse=True)[:50]
    )
    return OperationsTableSectionModel(
        id="run_blockers",
        title="Run Scheduling Diagnostics",
        columns=_columns(
            ("time", "Time"),
            ("tool", "Tool"),
            ("run_id", "Run ID"),
            ("capability", "Capability"),
            ("status", "Status"),
            ("reason", "Reason"),
            ("assignment_status", "Assignment"),
            ("lease_state", "Lease"),
            ("retry_budget", "Retry Budget"),
            ("candidate_workers", "Candidate Workers"),
            ("blocked_by", "Blocked By"),
            ("next_step", "Next Step"),
            ("active", "Active"),
            ("limit", "Limit"),
            ("available_workers", "Available Workers"),
            ("worker", "Worker ID"),
            ("age", "Age"),
            ("actions", "Actions"),
        ),
        rows=rows,
        total=len(active_runs),
        view_all_route="/operations/tool?tab=diagnostics",
        empty_state="No active tool runs need scheduling diagnostics.",
    )


def _run_blocker_row(
    run: ToolRun,
    *,
    tools_by_id: dict[str, Tool],
    assignment: ToolRunAssignment | None,
    workers: list[ToolWorkerRegistration],
    worker_group_counts: dict[str, Counter[str]],
    concurrency_policy: ToolRunConcurrencyPolicy,
    now: datetime,
) -> OperationsTableRowModel:
    group = _concurrency_group_for_run(
        run,
        tools_by_id=tools_by_id,
        concurrency_policy=concurrency_policy,
    )
    active = sum(counts[group.key] for counts in worker_group_counts.values())
    available_workers = _available_worker_count_for_group(
        group,
        workers=workers,
        worker_group_counts=worker_group_counts,
        now=now,
    )
    reason = _run_blocker_reason(
        run,
        assignment=assignment,
        workers=workers,
        worker_group_counts=worker_group_counts,
        tools_by_id=tools_by_id,
        concurrency_policy=concurrency_policy,
        now=now,
    )
    return OperationsTableRowModel(
        id=run.id,
        cells={
            "time": format_datetime_utc(_run_time(run)),
            "tool": _tool_label(run, tools_by_id),
            "run_id": run.id,
            "source": _source_label(run),
            "capability": _capability_label(group.key),
            "capability_key": group.key,
            "status": _status_label(run.status),
            "reason": reason,
            "assignment_status": _assignment_status_label(assignment),
            "assignment_id": _assignment_id(assignment),
            "lease_state": _lease_state_label(run, assignment=assignment, now=now),
            "lease_expires_at": _lease_expires_label(run, assignment=assignment),
            "retry_budget": _retry_budget_label(run),
            "candidate_workers": str(available_workers),
            "blocked_by": _run_blocked_by_label(
                reason,
                run=run,
                assignment=assignment,
            ),
            "next_step": _run_next_step_label(
                reason,
                run=run,
                assignment=assignment,
                available_workers=available_workers,
            ),
            "active": str(active),
            "limit": f"{group.max_in_flight}/worker",
            "available_workers": str(available_workers),
            "mode": run.target.mode.value,
            "strategy": run.target.strategy.value,
            "worker": _display(run.worker_id),
            "age": _age_label(run.created_at, now=now),
            "actions": "Open / Trace / Cancel",
            "route": _source_route(run),
            "trace": _trace_id(run),
            "trace_route": _trace_route(run),
        },
        status=run.status.value,
        tone=_run_blocker_tone(reason, run.status),
    )


def _inline_risk_section(
    runs: list[ToolRun],
    *,
    active_runs: list[ToolRun],
    assignment_by_run: dict[str, ToolRunAssignment],
    now: datetime,
) -> OperationsKeyValueSectionModel:
    inline_runs = [run for run in runs if run.target.mode.value == "inline"]
    active_inline_runs = [
        run for run in active_runs if run.target.mode.value == "inline"
    ]
    failed_inline_runs = [
        run
        for run in inline_runs
        if run.status in {ToolRunStatus.FAILED, ToolRunStatus.TIMED_OUT}
    ]
    longest_inline_seconds = max(
        (
            _duration_seconds(
                run,
                assignment=assignment_by_run.get(run.id),
                now=now,
            )
            for run in inline_runs
        ),
        default=0,
    )
    inline_share = _percent_label(len(inline_runs), len(runs))
    return OperationsKeyValueSectionModel(
        id="inline_risk",
        title="Inline Risk",
        items=(
            OperationsKeyValueItemModel(
                label="Active Inline Runs",
                value=str(len(active_inline_runs)),
                tone="warning" if active_inline_runs else "success",
            ),
            OperationsKeyValueItemModel(
                label="Inline Share",
                value=f"{inline_share} ({len(inline_runs)} / {len(runs)})",
                tone=(
                    "warning"
                    if inline_runs and len(inline_runs) == len(runs)
                    else "neutral"
                ),
            ),
            OperationsKeyValueItemModel(
                label="Inline Failures",
                value=str(len(failed_inline_runs)),
                tone="danger" if failed_inline_runs else "success",
            ),
            OperationsKeyValueItemModel(
                label="Longest Inline Duration",
                value=_duration_label(longest_inline_seconds),
                tone=(
                    "warning"
                    if longest_inline_seconds >= _LONG_RUNNING_SECONDS
                    else "neutral"
                ),
            ),
        ),
    )


def _recent_artifacts_section(
    runs: list[ToolRun],
    *,
    tools: list[Tool],
    artifact_service: Any | None,
) -> OperationsTableSectionModel:
    tools_by_id = _tool_lookup(tools)
    rows: list[OperationsTableRowModel] = []
    for run in sorted(runs, key=_run_time, reverse=True):
        for artifact in _artifact_refs(run, artifact_service=artifact_service):
            artifact_id = artifact["artifact_id"]
            rows.append(
                OperationsTableRowModel(
                    id=f"{run.id}:{artifact_id}",
                    cells={
                        "name": artifact["name"],
                        "kind": artifact["kind"],
                        "artifact_id": artifact_id,
                        "mime_type": artifact["mime_type"],
                        "size": artifact["size"],
                        "dimensions": artifact["dimensions"],
                        "tool": _tool_label(run, tools_by_id),
                        "run_id": run.id,
                        "time": format_datetime_utc(_run_time(run)),
                        "actions": "Open / Trace",
                        "route": (
                            artifact["preview_url"]
                            or artifact["download_url"]
                            or "-"
                        ),
                        "trace": _trace_id(run),
                        "trace_route": _trace_route(run),
                    },
                    status=artifact["kind"],
                    tone="info",
                ),
            )
    return OperationsTableSectionModel(
        id="recent_artifacts",
        title="Recent Artifacts",
        columns=_columns(
            ("name", "Name"),
            ("kind", "Kind"),
            ("artifact_id", "Artifact ID"),
            ("mime_type", "Mime Type"),
            ("size", "Size"),
            ("dimensions", "Dimensions"),
            ("tool", "Tool"),
            ("run_id", "Run ID"),
            ("time", "Time"),
            ("actions", "Actions"),
        ),
        rows=tuple(rows[:50]),
        total=len(rows),
        view_all_route="/operations/tool?tab=artifacts",
        empty_state="No tool artifacts observed.",
    )


def _recent_tool_events(
    *,
    operations_observation: Any | None,
    events_service: Any | None,
    definition_registry: Any | None,
    limit: int,
) -> tuple[OperationsObservedEvent, ...]:
    event_limit = max(int(limit), 1)
    return _dedupe_tool_events(
        (
            *_recent_tool_events_from_bus(
                events_service,
                definition_registry=definition_registry,
                limit=event_limit,
            ),
            *_recent_tool_events_from_observation(
                operations_observation,
                limit=event_limit,
            ),
        ),
        limit=event_limit,
    )


def _recent_tool_events_from_observation(
    observation: Any | None,
    *,
    limit: int,
) -> tuple[OperationsObservedEvent, ...]:
    if observation is None or not hasattr(observation, "get_module_observation"):
        return ()
    try:
        observation = observation.get_module_observation("tool")
    except Exception:
        return ()
    if observation is None:
        return ()
    recent_events = getattr(observation, "recent_events", ())
    return tuple(
        event
        for event in tuple(recent_events)[: max(int(limit), 1)]
        if isinstance(event, OperationsObservedEvent)
    )


def _recent_tool_events_from_bus(
    events_service: Any | None,
    *,
    definition_registry: Any | None,
    limit: int,
) -> tuple[OperationsObservedEvent, ...]:
    if events_service is None:
        return ()
    topics = _dedupe_topic_names(
        (
            *_TOOL_DIRECT_EVENT_TOPICS,
            *(
                topic
                for topic in _safe_list_event_topics(events_service)
                if _is_tool_event_topic(topic)
            ),
        ),
    )[:_MAX_TOOL_EVENT_TOPICS]
    read_recent = getattr(events_service, "read_recent_event_topic", None)
    if not callable(read_recent):
        return ()
    events: list[OperationsObservedEvent] = []
    topic_limit = min(
        max(_RECENT_TOOL_TOPIC_LIMIT, int(limit)),
        _MAX_RECENT_TOOL_EVENTS,
    )
    for topic in topics:
        try:
            records = tuple(read_recent(topic, limit=topic_limit) or ())
        except Exception:
            continue
        for record in records:
            try:
                observed = observed_event_from_record(
                    record,
                    definition_registry=definition_registry,
                )
            except Exception:
                continue
            if _is_tool_observed_event(observed):
                events.append(observed)
    events.sort(key=lambda event: coerce_utc_datetime(event.occurred_at), reverse=True)
    return tuple(events[:_MAX_RECENT_TOOL_EVENTS])


def _safe_list_event_topics(events_service: Any) -> tuple[str, ...]:
    list_topics = getattr(events_service, "list_event_topics", None)
    if not callable(list_topics):
        return ()
    try:
        return tuple(str(topic) for topic in list_topics() or () if str(topic))
    except Exception:
        return ()


def _is_tool_event_topic(topic: str) -> bool:
    normalized = topic.strip().lower()
    return normalized.startswith("tool.") or normalized.startswith("events.named.tool.")


def _is_tool_observed_event(event: OperationsObservedEvent) -> bool:
    owner = event.owner.strip().lower()
    module = event.module.strip().lower()
    event_name = event.event_name.strip().lower()
    return owner == "tool" or module == "tool" or event_name.startswith("tool.")


def _dedupe_tool_events(
    events: tuple[OperationsObservedEvent, ...],
    *,
    limit: int,
) -> tuple[OperationsObservedEvent, ...]:
    result: list[OperationsObservedEvent] = []
    seen: set[tuple[str, str]] = set()
    for event in sorted(
        events,
        key=lambda item: coerce_utc_datetime(item.occurred_at),
        reverse=True,
    ):
        key = (event.topic, event.cursor or event.id)
        if key in seen:
            continue
        seen.add(key)
        result.append(event)
    return tuple(result[: min(max(int(limit), 1), _MAX_RECENT_TOOL_EVENTS)])


def _dedupe_topic_names(values: tuple[str, ...]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip()
        if not normalized:
            continue
        key = normalized.lower()
        if key in seen:
            continue
        seen.add(key)
        result.append(normalized)
    return tuple(result)


def _tool_lifecycle_events_section(
    events: tuple[OperationsObservedEvent, ...],
    *,
    tools: list[Tool],
    runs: list[ToolRun],
) -> OperationsTableSectionModel:
    tools_by_id = _tool_lookup(tools)
    runs_by_id = {run.id: run for run in runs}
    visible_events = sorted(
        events,
        key=lambda event: (
            _tool_lifecycle_display_priority(event.event_name),
            -coerce_utc_datetime(event.occurred_at).timestamp(),
        ),
    )
    rows = tuple(
        _tool_lifecycle_event_row(
            event,
            tools_by_id=tools_by_id,
            runs_by_id=runs_by_id,
        )
        for event in visible_events[:80]
    )
    return OperationsTableSectionModel(
        id="tool_lifecycle_events",
        title="Tool Lifecycle Events",
        columns=_columns(
            ("time", "Time"),
            ("level", "Level"),
            ("event", "Event"),
            ("tool", "Tool"),
            ("run_id", "Run ID"),
            ("assignment", "Assignment"),
            ("worker", "Worker ID"),
            ("status", "Status"),
            ("source", "Source"),
            ("details", "Details"),
            ("trace", "Trace"),
        ),
        rows=rows,
        total=len(events),
        view_all_route="/operations/tool?tab=events",
        empty_state="No tool lifecycle events observed yet.",
    )


def _tool_lifecycle_display_priority(event_name: str) -> int:
    normalized = event_name.strip().lower()
    if normalized.startswith(("tool.run.", "tool.assignment.", "tool.worker.")):
        return 0
    if normalized.startswith(("tool.source.", "tool.function.")):
        return 1
    return 2


def _tool_lifecycle_event_row(
    event: OperationsObservedEvent,
    *,
    tools_by_id: dict[str, Tool],
    runs_by_id: dict[str, ToolRun],
) -> OperationsTableRowModel:
    payload = dict(event.payload)
    run_id = event.run_id or _optional_str(payload.get("run_id"))
    run = runs_by_id.get(run_id or "")
    tool_id = _optional_str(payload.get("tool_id")) or (
        run.tool_id if run is not None else None
    )
    assignment_id = _optional_str(payload.get("assignment_id"))
    worker_id = _optional_str(payload.get("worker_id")) or (
        run.worker_id if run is not None else None
    )
    trace_id = _tool_event_trace_id(event, run)
    route = _source_route(run) if run is not None else "-"
    return OperationsTableRowModel(
        id=_display(event.cursor or event.id),
        cells={
            "time": format_datetime_utc(event.occurred_at),
            "level": _title_label(event.level),
            "event": _short_tool_event_name(event.event_name),
            "tool": (
                _tool_label(run, tools_by_id)
                if run is not None
                else _tool_label_from_id(tool_id, tools_by_id)
            ),
            "run_id": _display(run_id),
            "assignment": _display(assignment_id),
            "worker": _display(worker_id),
            "status": _display(event.status),
            "source": _source_label(run) if run is not None else "Event Bus",
            "details": _tool_event_details(payload),
            "trace": _display(trace_id),
            "route": route,
            "trace_route": _trace_route_from_id(trace_id),
        },
        status=event.status,
        tone=_tool_event_tone(event),
    )


def _tool_label_from_id(
    tool_id: str | None,
    tools_by_id: dict[str, Tool],
) -> str:
    if tool_id is None:
        return "-"
    tool = tools_by_id.get(tool_id)
    if tool is None:
        return tool_id
    return tool.id if tool.id == tool.name else f"{tool.name} ({tool.id})"


def _tool_display_name_from_id(
    tool_id: str | None,
    tools_by_id: dict[str, Tool],
) -> str:
    if tool_id is None:
        return "-"
    tool = tools_by_id.get(tool_id)
    if tool is None:
        return tool_id
    return tool.name


def _tool_event_trace_id(
    event: OperationsObservedEvent,
    run: ToolRun | None,
) -> str | None:
    if event.trace_id:
        return event.trace_id
    if run is None:
        return None
    return _context_str(run, "trace_id") or _context_str(run, "correlation_id")


def _trace_route_from_id(trace_id: str | None) -> str:
    return f"/ui/trace/{trace_id}" if trace_id else "-"


def _short_tool_event_name(event_name: str) -> str:
    return event_name.removeprefix("tool.")


def _tool_event_details(payload: dict[str, Any]) -> str:
    keys = (
        "error_message",
        "reason",
        "terminal_reason",
        "attempt_count",
        "mode",
        "strategy",
        "environment",
        "assignment_id",
        "worker_id",
        "previous_status",
        "max_in_flight",
        "current_in_flight",
        "retention_seconds",
    )
    parts = [
        f"{key}={_display(payload.get(key))}"
        for key in keys
        if _display(payload.get(key)) != "-"
    ]
    return _truncate(", ".join(parts), 128) if parts else "-"


def _tool_event_tone(event: OperationsObservedEvent) -> str:
    status = event.status.lower()
    level = event.level.lower()
    if level == "error" or status in {"failed", "timed-out", "timed_out"}:
        return "danger"
    if level == "warning" or status in {
        "cancelled",
        "cancel-requested",
        "cancel_requested",
        "expired",
        "requeued",
        "stale",
    }:
        return "warning"
    if status in {"succeeded", "created", "queued", "started", "running"}:
        return "success"
    return "info"


def _tool_worker_details(
    workers: list[ToolWorkerRegistration],
    *,
    active_runs: list[ToolRun],
    observed_events: tuple[OperationsObservedEvent, ...],
    now: datetime,
) -> tuple[ToolWorkerDetailModel, ...]:
    active_runs_by_worker: dict[str, list[ToolRun]] = {}
    for run in active_runs:
        if run.worker_id:
            active_runs_by_worker.setdefault(run.worker_id, []).append(run)

    events_by_worker: dict[str, list[OperationsObservedEvent]] = {}
    for event in observed_events:
        worker_id = _optional_str(event.payload.get("worker_id"))
        if worker_id is None and event.event_name.startswith("tool.worker."):
            worker_id = event.entity_id
        if worker_id:
            events_by_worker.setdefault(worker_id, []).append(event)

    return tuple(
        _tool_worker_detail(
            worker,
            active_runs=active_runs_by_worker.get(worker.id, []),
            events=events_by_worker.get(worker.id, []),
            now=now,
        )
        for worker in sorted(workers, key=lambda item: item.id)[:50]
    )


def _tool_worker_detail(
    worker: ToolWorkerRegistration,
    *,
    active_runs: list[ToolRun],
    events: list[OperationsObservedEvent],
    now: datetime,
) -> ToolWorkerDetailModel:
    bucket = _worker_registration_bucket(worker, now=now)
    status, tone = _worker_registration_status(bucket)
    return ToolWorkerDetailModel(
        worker_id=worker.id,
        title=worker.id,
        status=status,
        tone=tone,
        summary=_tool_worker_detail_summary(
            worker,
            status=status,
            active_runs=active_runs,
            now=now,
        ),
        capabilities=_tool_worker_capabilities_section(worker),
        runtimes=_tool_worker_runtimes_section(worker),
        provider_limits=_tool_worker_provider_limits_section(worker),
        events=_tool_worker_events_section(events),
        raw_payload=_json_safe_payload(worker.capabilities_payload),
    )


def _tool_worker_detail_summary(
    worker: ToolWorkerRegistration,
    *,
    status: str,
    active_runs: list[ToolRun],
    now: datetime,
) -> tuple[OperationsKeyValueItemModel, ...]:
    current_runs = tuple(sorted(run.id for run in active_runs))
    return (
        OperationsKeyValueItemModel(label="Worker ID", value=worker.id),
        OperationsKeyValueItemModel(
            label="Status",
            value=status,
            tone=_worker_registration_status(
                _worker_registration_bucket(worker, now=now),
            )[1],
        ),
        OperationsKeyValueItemModel(
            label="Worker Load",
            value=f"{worker.current_in_flight}/{worker.max_in_flight}",
        ),
        OperationsKeyValueItemModel(
            label="Current Run",
            value=_join_values(list(current_runs)),
        ),
        OperationsKeyValueItemModel(
            label="Last Heartbeat",
            value=format_datetime_utc(worker.heartbeat_at),
        ),
        OperationsKeyValueItemModel(
            label="Lease Expires At",
            value=(
                format_datetime_utc(worker.lease_expires_at)
                if worker.lease_expires_at is not None
                else "-"
            ),
        ),
        OperationsKeyValueItemModel(
            label="Registered At",
            value=format_datetime_utc(worker.registered_at),
        ),
        OperationsKeyValueItemModel(
            label="Age",
            value=_age_label(worker.registered_at, now=now),
        ),
        OperationsKeyValueItemModel(
            label="Runtime Count",
            value=_worker_runtime_count(worker),
        ),
        OperationsKeyValueItemModel(
            label="Providers",
            value=_worker_provider_summary(worker),
        ),
    )


def _tool_worker_capabilities_section(
    worker: ToolWorkerRegistration,
) -> OperationsKeyValueSectionModel:
    policy = worker.capabilities_payload.get("concurrency_policy")
    if not isinstance(policy, dict):
        policy = {}
    return OperationsKeyValueSectionModel(
        id="worker_capabilities",
        title="Worker Capabilities",
        items=(
            OperationsKeyValueItemModel(
                label="Max In Flight",
                value=str(worker.max_in_flight),
            ),
            OperationsKeyValueItemModel(
                label="Current In Flight",
                value=str(worker.current_in_flight),
            ),
            OperationsKeyValueItemModel(
                label="Default Max In Flight",
                value=_display(policy.get("default_max_in_flight")),
            ),
            OperationsKeyValueItemModel(
                label="Image Max In Flight",
                value=_display(policy.get("image_max_in_flight")),
            ),
            OperationsKeyValueItemModel(
                label="Shared State Max In Flight",
                value=_display(policy.get("shared_state_max_in_flight")),
            ),
            OperationsKeyValueItemModel(
                label="Capability Groups",
                value=_worker_capability_summary(worker),
            ),
        ),
    )


def _tool_worker_runtimes_section(
    worker: ToolWorkerRegistration,
) -> OperationsTableSectionModel:
    registrations = _worker_runtime_registrations(worker)
    rows = tuple(
        OperationsTableRowModel(
            id=f"{worker.id}:{index}:{_display(registration.get('runtime_key'))}",
            cells={
                "runtime_key": _display(registration.get("runtime_key")),
                "provider": _provider_label(
                    _optional_str(registration.get("concurrency_key"))
                    or _provider_key_from_runtime_key(
                        _optional_str(registration.get("runtime_key")),
                    )
                    or "-",
                ),
                "concurrency_key": _display(registration.get("concurrency_key")),
                "max_concurrency": _display(registration.get("max_concurrency")),
            },
            status="registered",
            tone="info",
        )
        for index, registration in enumerate(
            sorted(
                registrations,
                key=lambda item: (
                    _display(item.get("runtime_key")),
                    _display(item.get("concurrency_key")),
                ),
            ),
        )
    )
    return OperationsTableSectionModel(
        id="worker_runtimes",
        title="Worker Runtime Registry",
        columns=_columns(
            ("runtime_key", "Runtime Key"),
            ("provider", "Provider"),
            ("concurrency_key", "Concurrency Key"),
            ("max_concurrency", "Max Concurrency"),
        ),
        rows=rows,
        total=len(registrations),
        empty_state="No runtime registrations reported by this worker.",
    )


def _tool_worker_provider_limits_section(
    worker: ToolWorkerRegistration,
) -> OperationsTableSectionModel:
    snapshot = worker.capabilities_payload.get("runtime_metrics")
    registry = worker.capabilities_payload.get("runtime_registry")
    grouped: dict[str, dict[str, Any]] = {}
    if isinstance(registry, dict):
        for provider_key, config in _provider_limiter_configurations(registry):
            bucket = grouped.setdefault(provider_key, _provider_metric_bucket())
            limit = _int_value(config.get("limit"))
            runtime_keys = config.get("runtime_keys")
            if isinstance(runtime_keys, set):
                bucket["runtime_keys"].update(runtime_keys)
            if limit:
                bucket["configured_capacity"] += limit
                bucket["configured_limit_entries"].add(("worker", limit))
    if isinstance(snapshot, dict):
        for item in _metric_items(snapshot, "gauges"):
            provider_key = _metric_provider_key(item)
            if provider_key is None:
                continue
            bucket = grouped.setdefault(provider_key, _provider_metric_bucket())
            bucket["sources"].add(worker.id)
            name = _optional_str(item.get("name"))
            if name == _TOOL_PROVIDER_LIMITER_ACTIVE:
                bucket["active"] += _float(item.get("value"))
            elif name == _TOOL_PROVIDER_LIMITER_WAITERS:
                bucket["waiting"] += _float(item.get("value"))
        for item in _metric_items(snapshot, "timings"):
            if _optional_str(item.get("name")) != _TOOL_PROVIDER_LIMITER_WAIT_SECONDS:
                continue
            provider_key = _metric_provider_key(item)
            if provider_key is None:
                continue
            bucket = grouped.setdefault(provider_key, _provider_metric_bucket())
            bucket["sources"].add(worker.id)
            count = _int_value(item.get("count"))
            total = _float(item.get("total_seconds"))
            bucket["wait_count"] += count
            bucket["total_wait_seconds"] += total
            bucket["max_wait_seconds"] = max(
                bucket["max_wait_seconds"],
                _float(item.get("max_seconds")),
            )
    rows = tuple(
        _provider_limit_row(provider_key, bucket)
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
        columns=_columns(
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


def _tool_worker_events_section(
    events: list[OperationsObservedEvent],
) -> OperationsTableSectionModel:
    rows = tuple(
        _tool_lifecycle_event_row(
            event,
            tools_by_id={},
            runs_by_id={},
        )
        for event in sorted(events, key=lambda item: item.occurred_at, reverse=True)[:20]
    )
    return OperationsTableSectionModel(
        id="worker_events",
        title="Worker Events",
        columns=_columns(
            ("time", "Time"),
            ("level", "Level"),
            ("event", "Event"),
            ("status", "Status"),
            ("details", "Details"),
            ("trace", "Trace"),
        ),
        rows=rows,
        total=len(events),
        empty_state="No observed events retained for this worker.",
    )


def _tool_run_details(
    runs: list[ToolRun],
    *,
    tools: list[Tool],
    assignments: list[ToolRunAssignment],
    observed_events: tuple[OperationsObservedEvent, ...],
    artifact_service: Any | None,
    run_contexts: dict[str, dict[str, str]],
    now: datetime,
) -> tuple[ToolRunDetailModel, ...]:
    tools_by_id = _tool_lookup(tools)
    assignments_by_run: dict[str, list[ToolRunAssignment]] = {}
    for assignment in assignments:
        assignments_by_run.setdefault(assignment.run_id, []).append(assignment)
    events_by_run: dict[str, list[OperationsObservedEvent]] = {}
    for event in observed_events:
        if event.run_id:
            events_by_run.setdefault(event.run_id, []).append(event)

    return tuple(
        _tool_run_detail(
            run,
            tools_by_id=tools_by_id,
            assignments=assignments_by_run.get(run.id, []),
            events=events_by_run.get(run.id, []),
            artifact_service=artifact_service,
            run_context=run_contexts.get(run.id),
            now=now,
        )
        for run in sorted(runs, key=_run_time, reverse=True)[:50]
    )


def _tool_run_detail(
    run: ToolRun,
    *,
    tools_by_id: dict[str, Tool],
    assignments: list[ToolRunAssignment],
    events: list[OperationsObservedEvent],
    artifact_service: Any | None,
    run_context: Mapping[str, str] | None,
    now: datetime,
) -> ToolRunDetailModel:
    assignment = _latest_assignment_by_run(assignments).get(run.id)
    return ToolRunDetailModel(
        run_id=run.id,
        title=_tool_label(run, tools_by_id),
        status=run.status.value,
        tone=_tone_for_status(run.status),
        summary=_tool_run_detail_summary(
            run,
            tools_by_id=tools_by_id,
            assignment=assignment,
            run_context=run_context,
            now=now,
        ),
        invocation_context=_invocation_context_items(run),
        input_payload=_json_safe_payload(run.input_payload),
        result_payload=_json_safe_payload(run.result_payload),
        result_summary=_result_summary(run),
        error=_display(run.error_message),
        error_facts=_tool_run_error_facts(run, tools_by_id.get(run.tool_id)),
        assignments=_assignment_history_section(assignments),
        events=_tool_run_events_section(events, tools_by_id=tools_by_id, run=run),
        artifacts=_tool_run_artifacts_section(
            run,
            tools_by_id=tools_by_id,
            artifact_service=artifact_service,
        ),
    )


def _tool_run_error_facts(
    run: ToolRun,
    tool: Tool | None,
) -> OperationsKeyValueSectionModel:
    if not run.error_message and run.status is not ToolRunStatus.TIMED_OUT:
        return OperationsKeyValueSectionModel(
            id="error_facts",
            title="Error Facts",
            items=(),
        )
    family, code, tone = _tool_error_classification(run)
    http_status = _error_http_status(run.error_message)
    return OperationsKeyValueSectionModel(
        id="error_facts",
        title="Error Facts",
        items=(
            OperationsKeyValueItemModel(
                label="Error Family",
                value=family,
                tone=tone,
            ),
            OperationsKeyValueItemModel(
                label="Error Code",
                value=code,
                tone=tone,
            ),
            OperationsKeyValueItemModel(
                label="Provider",
                value=_provider_history_label(_tool_provider_key(tool)),
            ),
            OperationsKeyValueItemModel(
                label="HTTP Status",
                value=http_status or "-",
                tone="danger" if http_status and http_status.startswith(("4", "5")) else "neutral",
            ),
            OperationsKeyValueItemModel(
                label="Retryable",
                value="Yes" if run.can_retry() and run.status in {ToolRunStatus.FAILED, ToolRunStatus.TIMED_OUT} else "No",
                tone=(
                    "warning"
                    if run.can_retry()
                    and run.status in {ToolRunStatus.FAILED, ToolRunStatus.TIMED_OUT}
                    else "neutral"
                ),
            ),
            OperationsKeyValueItemModel(
                label="Root Cause",
                value=_tool_error_root_cause(run),
                tone=tone,
            ),
        ),
    )


def _tool_error_classification(run: ToolRun) -> tuple[str, str, str]:
    message = (run.error_message or "").lower()
    if run.status is ToolRunStatus.TIMED_OUT or "timeout" in message or "timed out" in message:
        return ("timeout", "tool_timeout", "warning")
    if _looks_like_access_failure(run):
        return ("access", "access_denied", "danger")
    if "rate limit" in message or "429" in message or "too many requests" in message:
        return ("provider_limit", "rate_limited", "warning")
    if "lease expired" in message or "retry budget exhausted" in message:
        return ("worker_lease", "lease_expired", "danger")
    if any(marker in message for marker in ("connection", "network", "dns", "socket")):
        return ("network", "network_error", "warning")
    if any(marker in message for marker in ("schema", "validation", "invalid")):
        return ("validation", "invalid_payload", "danger")
    return ("execution", "tool_execution_failed", "danger")


def _error_http_status(message: str | None) -> str | None:
    if not message:
        return None
    match = re.search(r"\b([45][0-9]{2})\b", message)
    return match.group(1) if match else None


def _tool_error_root_cause(run: ToolRun) -> str:
    if run.status is ToolRunStatus.TIMED_OUT:
        return "tool run timed out"
    if not run.error_message:
        return "-"
    return _truncate(run.error_message, 160)


def _tool_run_detail_summary(
    run: ToolRun,
    *,
    tools_by_id: dict[str, Tool],
    assignment: ToolRunAssignment | None,
    run_context: Mapping[str, str] | None,
    now: datetime,
) -> tuple[OperationsKeyValueItemModel, ...]:
    return (
        OperationsKeyValueItemModel(label="Tool", value=_tool_label(run, tools_by_id)),
        OperationsKeyValueItemModel(
            label="Status",
            value=_status_label(run.status),
            tone=_tone_for_status(run.status),
        ),
        *_browser_profile_summary_items(run),
        OperationsKeyValueItemModel(label="Mode", value=run.target.mode.value),
        OperationsKeyValueItemModel(label="Strategy", value=run.target.strategy.value),
        OperationsKeyValueItemModel(
            label="Environment",
            value=run.target.environment.value,
        ),
        OperationsKeyValueItemModel(
            label="Attempt",
            value=f"{run.attempt_count}/{run.max_attempts}",
        ),
        OperationsKeyValueItemModel(label="Worker ID", value=_display(run.worker_id)),
        OperationsKeyValueItemModel(
            label="Assignment",
            value=_assignment_id(assignment),
        ),
        OperationsKeyValueItemModel(
            label="Lease",
            value=_lease_state_label(run, assignment=assignment, now=now),
        ),
        OperationsKeyValueItemModel(
            label="Duration",
            value=_run_duration_label(run, assignment=assignment, now=now),
        ),
        OperationsKeyValueItemModel(
            label="Source",
            value=_source_label(run, run_context=run_context),
        ),
        OperationsKeyValueItemModel(
            label="Turn ID",
            value=_orchestration_run_id(run, run_context=run_context) or "-",
        ),
        OperationsKeyValueItemModel(
            label="Chain ID",
            value=_context_value(run_context, "chain_id"),
        ),
        OperationsKeyValueItemModel(
            label="Step ID",
            value=_context_value(run_context, "step_id"),
        ),
        OperationsKeyValueItemModel(
            label="Step Kind",
            value=_context_value(run_context, "step_kind"),
        ),
        OperationsKeyValueItemModel(
            label="Trace",
            value=_trace_id(run, run_context=run_context),
        ),
    )


def _browser_profile_summary_items(run: ToolRun) -> tuple[OperationsKeyValueItemModel, ...]:
    if not _is_browser_tool_run(run):
        return ()
    metadata = _result_metadata(run)
    profile_name = _optional_metadata_text(metadata.get("profile_name"))
    profile_source = _optional_metadata_text(metadata.get("profile_source"))
    if profile_name is None:
        profile_name = _optional_metadata_text(run.input_payload.get("profile"))
    if profile_name is None:
        profile_name = _optional_metadata_text(run.input_payload.get("profile_name"))
    if profile_source is None and profile_name is not None:
        profile_source = _input_profile_source(run) or "browser.default_profile"
    items = [
        OperationsKeyValueItemModel(
            label="Browser Profile",
            value=profile_name or "-",
        ),
        OperationsKeyValueItemModel(
            label="Profile Source",
            value=profile_source or "-",
        ),
    ]
    for label, key in (
        ("Browser Profile Pool", "browser_profile_pool"),
        ("Browser Allocation", "browser_allocation_id"),
        ("Host Service", "browser_host_service_key"),
        ("Target Host", "browser_target_host"),
        ("Host Generation", "browser_host_generation"),
        ("Target", "browser_target_id"),
        ("Page Generation", "browser_page_generation"),
        ("Snapshot Generation", "browser_snapshot_generation"),
        ("Ref Generation", "browser_current_ref_generation"),
    ):
        value = _optional_metadata_text(metadata.get(key))
        if value is not None:
            items.append(OperationsKeyValueItemModel(label=label, value=value))
    return tuple(items)


def _browser_run_label(run: ToolRun) -> str:
    if not _is_browser_tool_run(run):
        return "-"
    metadata = _result_metadata(run)
    profile_name = _optional_metadata_text(metadata.get("profile_name"))
    if profile_name is None:
        profile_name = _optional_metadata_text(run.input_payload.get("profile"))
    if profile_name is None:
        profile_name = _optional_metadata_text(run.input_payload.get("profile_name"))
    pool_id = _optional_metadata_text(metadata.get("browser_profile_pool"))
    if pool_id is None:
        pool_id = _optional_metadata_text(run.input_payload.get("profile_pool"))
    allocation_id = _optional_metadata_text(metadata.get("browser_allocation_id"))
    target_host = _optional_metadata_text(metadata.get("browser_target_host"))
    parts = [profile_name or "-"]
    if pool_id is not None:
        parts.append(f"pool:{pool_id}")
    if allocation_id is not None:
        parts.append(f"alloc:{_short_browser_identifier(allocation_id)}")
    if target_host is not None:
        parts.append(target_host)
    return " · ".join(parts)


def _is_browser_tool_run(run: ToolRun) -> bool:
    metadata = _result_metadata(run)
    result_tool = _optional_metadata_text(metadata.get("tool"))
    return any(
        value.startswith("browser.")
        for value in (
            run.tool_id,
            run.function_id or "",
            run.source_id or "",
            result_tool or "",
        )
    ) or run.source_id == "bundled.local_package.browser"


def _result_metadata(run: ToolRun) -> dict[str, Any]:
    payload = _result_payload(run)
    metadata = payload.get("metadata")
    return dict(metadata) if isinstance(metadata, Mapping) else {}


def _optional_metadata_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _short_browser_identifier(value: str) -> str:
    if len(value) <= 18:
        return value
    return f"{value[:10]}...{value[-6:]}"


def _input_profile_source(run: ToolRun) -> str | None:
    for key in ("profile", "profile_name"):
        if _optional_metadata_text(run.input_payload.get(key)) is not None:
            return f"input.{key}"
    return None


def _invocation_context_items(run: ToolRun) -> tuple[OperationsKeyValueItemModel, ...]:
    payload = run.invocation_context_payload
    if not isinstance(payload, dict) or not payload:
        return ()
    return tuple(
        OperationsKeyValueItemModel(
            label=str(key),
            value=_detail_value(value),
        )
        for key, value in sorted(payload.items(), key=lambda item: str(item[0]))
    )


def _assignment_history_section(
    assignments: list[ToolRunAssignment],
) -> OperationsTableSectionModel:
    rows = tuple(
        OperationsTableRowModel(
            id=assignment.id,
            cells={
                "assignment": assignment.id,
                "worker": assignment.worker_id,
                "status": _title_label(assignment.status.value),
                "attempt": str(assignment.attempt_count),
                "assigned_at": format_datetime_utc(assignment.assigned_at),
                "started_at": (
                    format_datetime_utc(assignment.started_at)
                    if assignment.started_at is not None
                    else "-"
                ),
                "completed_at": (
                    format_datetime_utc(assignment.completed_at)
                    if assignment.completed_at is not None
                    else "-"
                ),
                "lease_expires_at": (
                    format_datetime_utc(assignment.lease_expires_at)
                    if assignment.lease_expires_at is not None
                    else "-"
                ),
                "reason": _display(assignment.terminal_reason),
            },
            status=assignment.status.value,
            tone=_assignment_tone(assignment.status),
        )
        for assignment in sorted(assignments, key=lambda item: item.assigned_at, reverse=True)
    )
    return OperationsTableSectionModel(
        id="assignment_history",
        title="Assignment History",
        columns=_columns(
            ("assignment", "Assignment"),
            ("worker", "Worker ID"),
            ("status", "Status"),
            ("attempt", "Attempt"),
            ("assigned_at", "Assigned At"),
            ("started_at", "Started At"),
            ("completed_at", "Completed At"),
            ("lease_expires_at", "Lease Expires At"),
            ("reason", "Reason"),
        ),
        rows=rows,
        total=len(assignments),
        empty_state="No assignments recorded for this run.",
    )


def _tool_run_events_section(
    events: list[OperationsObservedEvent],
    *,
    tools_by_id: dict[str, Tool],
    run: ToolRun,
) -> OperationsTableSectionModel:
    rows = tuple(
        _tool_lifecycle_event_row(
            event,
            tools_by_id=tools_by_id,
            runs_by_id={run.id: run},
        )
        for event in sorted(events, key=lambda item: item.occurred_at, reverse=True)[:20]
    )
    return OperationsTableSectionModel(
        id="run_events",
        title="Run Events",
        columns=_columns(
            ("time", "Time"),
            ("level", "Level"),
            ("event", "Event"),
            ("status", "Status"),
            ("worker", "Worker ID"),
            ("assignment", "Assignment"),
            ("details", "Details"),
            ("trace", "Trace"),
        ),
        rows=rows,
        total=len(events),
        empty_state="No observed events retained for this run.",
    )


def _tool_run_artifacts_section(
    run: ToolRun,
    *,
    tools_by_id: dict[str, Tool],
    artifact_service: Any | None,
) -> OperationsTableSectionModel:
    rows = tuple(
        OperationsTableRowModel(
            id=f"{run.id}:{artifact['artifact_id']}",
            cells={
                "name": artifact["name"],
                "kind": artifact["kind"],
                "artifact_id": artifact["artifact_id"],
                "mime_type": artifact["mime_type"],
                "size": artifact["size"],
                "dimensions": artifact["dimensions"],
                "tool": _tool_label(run, tools_by_id),
                "actions": "Open",
                "route": artifact["preview_url"] or artifact["download_url"] or "-",
                "trace": _trace_id(run),
                "trace_route": _trace_route(run),
            },
            status=artifact["kind"],
            tone="info",
        )
        for artifact in _artifact_refs(run, artifact_service=artifact_service)
    )
    return OperationsTableSectionModel(
        id="run_artifacts",
        title="Artifacts",
        columns=_columns(
            ("name", "Name"),
            ("kind", "Kind"),
            ("artifact_id", "Artifact ID"),
            ("mime_type", "Mime Type"),
            ("size", "Size"),
            ("dimensions", "Dimensions"),
            ("actions", "Actions"),
        ),
        rows=rows,
        total=len(rows),
        empty_state="No artifacts recorded for this run.",
    )


def _assignment_tone(status: ToolRunAssignmentStatus) -> str:
    if status is ToolRunAssignmentStatus.SUCCEEDED:
        return "success"
    if status in {ToolRunAssignmentStatus.FAILED, ToolRunAssignmentStatus.EXPIRED}:
        return "danger"
    if status is ToolRunAssignmentStatus.CANCELLED:
        return "warning"
    if status is ToolRunAssignmentStatus.RUNNING:
        return "info"
    return "neutral"


def _detail_value(value: Any) -> str:
    if isinstance(value, str):
        return _truncate(value, 160)
    return _truncate(
        json.dumps(_json_safe_payload(value), ensure_ascii=False, sort_keys=True),
        160,
    )


def _json_safe_payload(value: Any, *, depth: int = 0) -> Any:
    if depth >= 6:
        return _truncate(str(value), 240)
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, datetime):
        return format_datetime_utc(value)
    if isinstance(value, dict):
        return {
            str(key): _json_safe_payload(item, depth=depth + 1)
            for key, item in list(value.items())[:80]
        }
    if isinstance(value, (list, tuple, set)):
        return [
            _json_safe_payload(item, depth=depth + 1)
            for item in list(value)[:80]
        ]
    return _truncate(str(value), 240)


def _strategies_section(runs: list[ToolRun]) -> OperationsTableSectionModel:
    grouped: dict[tuple[str, str, str], list[ToolRun]] = {}
    for run in runs:
        key = (
            run.target.mode.value,
            run.target.strategy.value,
            run.target.environment.value,
        )
        grouped.setdefault(key, []).append(run)
    rows = []
    for (mode, strategy, environment), strategy_runs in sorted(grouped.items()):
        active = [run for run in strategy_runs if not run.is_terminal()]
        failures = [
            run
            for run in strategy_runs
            if run.status in {ToolRunStatus.FAILED, ToolRunStatus.TIMED_OUT}
        ]
        succeeded_count = len(
            [run for run in strategy_runs if run.status is ToolRunStatus.SUCCEEDED],
        )
        rows.append(
            OperationsTableRowModel(
                id=f"{mode}:{strategy}:{environment}",
                cells={
                    "mode": mode,
                    "strategy": strategy,
                    "environment": environment,
                    "runs": str(len(strategy_runs)),
                    "active": str(len(active)),
                    "failures": str(len(failures)),
                    "success_rate": _percent_label(
                        succeeded_count,
                        len(strategy_runs),
                    ),
                },
                status="active" if active else "retained",
                tone="warning" if active else "danger" if failures else "success",
            ),
        )
    return OperationsTableSectionModel(
        id="strategies",
        title="Execution Strategies",
        columns=_columns(
            ("mode", "Mode"),
            ("strategy", "Strategy"),
            ("environment", "Environment"),
            ("runs", "Runs"),
            ("active", "Active"),
            ("failures", "Failures"),
            ("success_rate", "Success Rate"),
        ),
        rows=tuple(rows),
        total=len(rows),
        view_all_route="/operations/tool?tab=strategies",
        empty_state="No tool execution strategies observed.",
    )


def _run_reason(
    run: ToolRun,
    *,
    assignment: ToolRunAssignment | None = None,
    now: datetime | None = None,
) -> str:
    if run.error_message:
        return _truncate(run.error_message, 64)
    if assignment is not None and not assignment.is_terminal():
        if now is not None and _assignment_lease_expired(assignment, now=now):
            return "assignment lease expired"
        if assignment.status is ToolRunAssignmentStatus.ASSIGNED:
            return "assigned to worker"
        if assignment.status is ToolRunAssignmentStatus.RUNNING:
            return "running on worker"
    if run.status is ToolRunStatus.CANCEL_REQUESTED:
        return "cancel requested"
    if run.status is ToolRunStatus.DISPATCHING:
        return "dispatching to worker"
    if (
        run.status in {ToolRunStatus.DISPATCHING, ToolRunStatus.RUNNING}
        and run.worker_id
        and assignment is None
    ):
        return "worker assignment missing"
    if run.status is ToolRunStatus.CREATED:
        return "created"
    if run.status is ToolRunStatus.RUNNING:
        return "running"
    return run.status.value


def _tool_readiness_risk(
    tool: Tool,
    *,
    tool_service: OperationsToolQueryPort | None = None,
    access_service: Any | None,
) -> dict[str, Any]:
    if tool_service is not None and hasattr(tool_service, "check_readiness"):
        readiness = tool_service.check_readiness(tool.id)
        if isinstance(readiness, dict):
            return _tool_combined_readiness_payload(tool, readiness)
    return _tool_access_readiness(
        tool,
        tool_service=tool_service,
        access_service=access_service,
    )


def _tool_access_readiness(
    tool: Tool,
    *,
    tool_service: OperationsToolQueryPort | None = None,
    access_service: Any | None,
) -> dict[str, Any]:
    if tool_service is not None and hasattr(tool_service, "check_access_readiness"):
        readiness = tool_service.check_access_readiness(tool.id)
        if readiness is not None:
            return _tool_access_readiness_payload(tool, readiness.to_payload())
    requirement_sets = tuple(
        tuple(requirement for requirement in item if requirement.strip())
        for item in tool.access_requirement_sets
        if item
    )
    all_requirements = tuple(
        dict.fromkeys(
            requirement
            for requirement_set in requirement_sets
            for requirement in requirement_set
        ),
    )
    if not requirement_sets:
        return {
            "ready": True,
            "status": "ready",
            "reason": "No access requirement declared",
            "category": "-",
            "requirements": "-",
            "missing": "-",
            "setup": "-",
            "action": "-",
            "route": "-",
        }
    if access_service is None or not hasattr(access_service, "check_requirements"):
        return {
            "ready": False,
            "status": "unknown",
            "reason": "access readiness service is not connected",
            "category": "Access",
            "requirements": _join_values(all_requirements),
            "missing": _join_values(all_requirements),
            "setup": "-",
            "action": "Open Access",
            "route": "/operations/access",
        }

    checked_sets: list[tuple[dict[str, Any], ...]] = []
    for requirement_set in requirement_sets:
        read_items = tuple(
            _readiness_payload(item)
            for item in access_service.check_requirements(requirement_set)
        )
        checked_sets.append(read_items)
        if all(bool(item.get("ready")) for item in read_items):
            return {
                "ready": True,
                "status": "ready",
                "reason": "All requirements are ready",
                "category": "Access",
                "requirements": _join_values(all_requirements),
                "missing": "-",
                "setup": "-",
                "action": "-",
                "route": "-",
            }

    missing = tuple(
        dict.fromkeys(
            str(item.get("requirement") or "").strip()
            for checked_set in checked_sets
            for item in checked_set
            if not bool(item.get("ready")) and str(item.get("requirement") or "").strip()
        ),
    )
    reasons = tuple(
        dict.fromkeys(
            str(item.get("reason") or "").strip()
            for checked_set in checked_sets
            for item in checked_set
            if not bool(item.get("ready")) and str(item.get("reason") or "").strip()
        ),
    )
    setup_available = any(
        bool(item.get("setup_available"))
        for checked_set in checked_sets
        for item in checked_set
        if not bool(item.get("ready"))
    )
    unsupported = any(
        str(item.get("status") or "") == "unsupported"
        for checked_set in checked_sets
        for item in checked_set
        if not bool(item.get("ready"))
    )
    return {
        "ready": False,
        "status": "unsupported" if unsupported else "setup_needed",
        "reason": _join_values(reasons) if reasons else "access setup is required",
        "category": "Access",
        "requirements": _join_values(all_requirements),
        "missing": _join_values(missing),
        "setup": "available" if setup_available else "unavailable",
        "action": "Open Access",
        "route": "/operations/access",
    }


def _tool_combined_readiness_payload(
    tool: Tool,
    payload: dict[str, Any],
) -> dict[str, Any]:
    checks = tuple(
        dict(item)
        for item in payload.get("checks", [])
        if isinstance(item, dict)
    )
    blocked_checks = tuple(item for item in checks if not bool(item.get("ready")))
    categories = tuple(
        dict.fromkeys(
            str(item.get("category") or "").strip()
            for item in blocked_checks
            if str(item.get("category") or "").strip()
        ),
    )
    requirements = _readiness_requirements(checks=checks, tool=tool)
    missing = tuple(
        dict.fromkeys(
            str(item.get("binding_id") or item.get("requirement") or "").strip()
            for item in blocked_checks
            if str(item.get("binding_id") or item.get("requirement") or "").strip()
        ),
    )
    action, route = _readiness_action(categories)
    return {
        "ready": bool(payload.get("ready")),
        "status": str(payload.get("status") or "unknown"),
        "reason": str(payload.get("reason") or "tool readiness unknown"),
        "category": _readiness_category_label(categories),
        "requirements": _join_values(requirements) if requirements else "-",
        "missing": _join_values(missing) if missing else "-",
        "setup": "available" if bool(payload.get("setup_available")) else "unavailable",
        "action": action,
        "route": route,
    }


def _tool_access_readiness_payload(
    tool: Tool,
    payload: dict[str, Any],
) -> dict[str, Any]:
    checks = tuple(
        dict(item)
        for item in payload.get("checks", [])
        if isinstance(item, dict)
    )
    requirements = tuple(
        dict.fromkeys(
            str(item.get("binding_id") or item.get("requirement") or "").strip()
            for item in checks
            if str(item.get("binding_id") or item.get("requirement") or "").strip()
        ),
    )
    missing = tuple(
        dict.fromkeys(
            str(item.get("binding_id") or item.get("requirement") or "").strip()
            for item in checks
            if not bool(item.get("ready"))
            and str(item.get("binding_id") or item.get("requirement") or "").strip()
        ),
    )
    if not requirements:
        requirements = tuple(
            dict.fromkeys(
                requirement
                for requirement_set in tool.access_requirement_sets
                for requirement in requirement_set
                if requirement.strip()
            ),
        )
    return {
        "ready": bool(payload.get("ready")),
        "status": str(payload.get("status") or "unknown"),
        "reason": str(payload.get("reason") or "access readiness unknown"),
        "category": "Access",
        "requirements": _join_values(requirements) if requirements else "-",
        "missing": _join_values(missing) if missing else "-",
        "setup": "available" if bool(payload.get("setup_available")) else "unavailable",
        "action": "Open Access",
        "route": "/operations/access",
    }


def _readiness_requirements(
    *,
    checks: tuple[dict[str, Any], ...],
    tool: Tool,
) -> tuple[str, ...]:
    requirements = tuple(
        dict.fromkeys(
            str(item.get("binding_id") or item.get("requirement") or "").strip()
            for item in checks
            if str(item.get("binding_id") or item.get("requirement") or "").strip()
        ),
    )
    if requirements:
        return requirements
    declared = (
        *(
            requirement
            for requirement_set in tool.access_requirement_sets
            for requirement in requirement_set
            if requirement.strip()
        ),
        *(
            requirement
            for requirement_set in tool.runtime_requirement_sets
            for requirement in requirement_set
            if requirement.strip()
        ),
    )
    return tuple(dict.fromkeys(declared))


def _readiness_category_label(categories: tuple[str, ...]) -> str:
    normalized = set(categories)
    if not normalized:
        return "-"
    if normalized == {"access"}:
        return "Access"
    if normalized == {"runtime"}:
        return "Runtime"
    return "Mixed"


def _readiness_action(categories: tuple[str, ...]) -> tuple[str, str]:
    normalized = set(categories)
    if normalized == {"runtime"}:
        return "Open Daemon", "/operations/daemon"
    if "access" in normalized:
        return "Open Access", "/operations/access"
    if "runtime" in normalized:
        return "Open Daemon", "/operations/daemon"
    return "Inspect Tool", "/operations/tool"


def _readiness_risk_tone(readiness: dict[str, Any]) -> str:
    status = str(readiness.get("status") or "")
    if status in {"unsupported", "unknown"}:
        return "danger"
    if status == "degraded":
        return "warning"
    return "warning" if readiness.get("setup") == "available" else "danger"


def _readiness_payload(readiness: Any) -> dict[str, Any]:
    if hasattr(readiness, "to_payload"):
        payload = readiness.to_payload()
        if isinstance(payload, dict):
            return dict(payload)
    return {
        "requirement": _display(getattr(readiness, "requirement", None)),
        "ready": bool(getattr(readiness, "ready", False)),
        "setup_available": bool(getattr(readiness, "setup_available", False)),
        "status": _display(getattr(getattr(readiness, "status", None), "value", None)),
        "reason": _display(getattr(readiness, "reason", None)),
    }


def _tool_risk_reason(tool: Tool) -> str:
    reasons: list[str] = []
    if tool.execution_policy.requires_confirmation:
        reasons.append("confirmation")
    if tool.execution_policy.mutates_state:
        reasons.append("mutates state")
    if tool.access_requirement_sets:
        requirement_sets = [
            "+".join(requirements)
            for requirements in tool.access_requirement_sets
            if requirements
        ]
        if requirement_sets:
            reasons.append(f"access: {' OR '.join(requirement_sets)}")
        else:
            reasons.append("access gated")
    if tool.runtime_requirement_sets:
        requirement_sets = [
            "+".join(requirements)
            for requirements in tool.runtime_requirement_sets
            if requirements
        ]
        if requirement_sets:
            reasons.append(f"runtime: {' OR '.join(requirement_sets)}")
        else:
            reasons.append("runtime gated")
    if tool.required_effect_ids:
        reasons.append(f"effects: {', '.join(tool.required_effect_ids)}")
    return ", ".join(reasons) or "standard"


def _risky_tools(tools: list[Tool]) -> list[Tool]:
    return [
        tool
        for tool in tools
        if tool.execution_policy.requires_confirmation
        or tool.execution_policy.mutates_state
        or tool.access_requirement_sets
        or tool.runtime_requirement_sets
        or tool.required_effect_ids
    ]


def _overview_risky_tools(tools: list[Tool]) -> list[Tool]:
    return [
        tool
        for tool in tools
        if tool.execution_policy.requires_confirmation
        or tool.execution_policy.mutates_state
        or tool.access_requirement_sets
        or tool.runtime_requirement_sets
    ]


def _latest_assignment_by_run(
    assignments: list[ToolRunAssignment],
) -> dict[str, ToolRunAssignment]:
    latest: dict[str, ToolRunAssignment] = {}
    for assignment in sorted(
        assignments,
        key=lambda item: item.assigned_at,
        reverse=True,
    ):
        latest.setdefault(assignment.run_id, assignment)
    return latest


def _worker_group_counts(
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
        group = _concurrency_group_for_run(
            run,
            tools_by_id=tools_by_id,
            concurrency_policy=concurrency_policy,
        )
        counts.setdefault(assignment.worker_id, Counter())[group.key] += 1
        counted_run_ids.add(run.id)

    for run in runs:
        if run.id in counted_run_ids or run.is_terminal() or not run.worker_id:
            continue
        group = _concurrency_group_for_run(
            run,
            tools_by_id=tools_by_id,
            concurrency_policy=concurrency_policy,
        )
        counts.setdefault(run.worker_id, Counter())[group.key] += 1
        counted_run_ids.add(run.id)
    return counts, counted_run_ids


def _sum_group_counts(worker_group_counts: dict[str, Counter[str]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    for worker_counts in worker_group_counts.values():
        counts.update(worker_counts)
    return counts


def _concurrency_group_for_run(
    run: ToolRun,
    *,
    tools_by_id: dict[str, Tool],
    concurrency_policy: ToolRunConcurrencyPolicy,
) -> ToolRunConcurrencyGroup:
    return concurrency_policy.group_for(run=run, tool=tools_by_id.get(run.tool_id))


def _online_workers(
    workers: list[ToolWorkerRegistration],
    *,
    now: datetime,
) -> list[ToolWorkerRegistration]:
    return [worker for worker in workers if _worker_is_online(worker, now=now)]


def _worker_is_online(worker: ToolWorkerRegistration, *, now: datetime) -> bool:
    if worker.status is not ToolWorkerStatus.ONLINE:
        return False
    if worker.lease_expires_at is None:
        return True
    return coerce_utc_datetime(worker.lease_expires_at) > coerce_utc_datetime(now)


def _group_worker_capacity(
    group: ToolRunConcurrencyGroup,
    *,
    workers: list[ToolWorkerRegistration],
    now: datetime,
) -> int:
    return sum(
        min(max(worker.max_in_flight, 0), group.max_in_flight)
        for worker in _online_workers(workers, now=now)
    )


def _available_worker_count_for_group(
    group: ToolRunConcurrencyGroup,
    *,
    workers: list[ToolWorkerRegistration],
    worker_group_counts: dict[str, Counter[str]],
    now: datetime,
) -> int:
    return sum(
        1
        for worker in _online_workers(workers, now=now)
        if _worker_can_start_group(
            worker,
            group,
            worker_group_counts=worker_group_counts,
        )
    )


def _worker_can_start_group(
    worker: ToolWorkerRegistration,
    group: ToolRunConcurrencyGroup,
    *,
    worker_group_counts: dict[str, Counter[str]],
) -> bool:
    if worker.current_in_flight >= worker.max_in_flight:
        return False
    return worker_group_counts.get(worker.id, Counter())[group.key] < group.max_in_flight


def _run_blocker_reason(
    run: ToolRun,
    *,
    assignment: ToolRunAssignment | None,
    workers: list[ToolWorkerRegistration],
    worker_group_counts: dict[str, Counter[str]],
    tools_by_id: dict[str, Tool],
    concurrency_policy: ToolRunConcurrencyPolicy,
    now: datetime,
) -> str:
    if run.error_message:
        return _truncate(run.error_message, 64)
    if assignment is not None and not assignment.is_terminal():
        if _assignment_lease_expired(assignment, now=now):
            return "assignment lease expired"
        if assignment.status is ToolRunAssignmentStatus.ASSIGNED:
            return "assigned to worker"
        if assignment.status is ToolRunAssignmentStatus.RUNNING:
            return "running on worker"
    if run.target.mode.value == "inline":
        return "inline execution"

    online_workers = _online_workers(workers, now=now)
    if not online_workers:
        return "waiting for online worker"
    if not any(worker.current_in_flight < worker.max_in_flight for worker in online_workers):
        return "waiting for worker slot"

    group = _concurrency_group_for_run(
        run,
        tools_by_id=tools_by_id,
        concurrency_policy=concurrency_policy,
    )
    if not any(
        _worker_can_start_group(
            worker,
            group,
            worker_group_counts=worker_group_counts,
        )
        for worker in online_workers
    ):
        return "waiting for capability capacity"
    if run.status is ToolRunStatus.QUEUED:
        return "waiting for scheduler"
    if run.status is ToolRunStatus.CREATED:
        return "created"
    if run.status is ToolRunStatus.DISPATCHING:
        return "dispatching to worker"
    if run.status is ToolRunStatus.CANCEL_REQUESTED:
        return "cancel requested"
    return _run_reason(run, assignment=assignment, now=now)


def _retry_budget_label(run: ToolRun) -> str:
    remaining = max(run.max_attempts - run.attempt_count, 0)
    return f"{remaining} left ({run.attempt_count}/{run.max_attempts})"


def _run_blocked_by_label(
    reason: str,
    *,
    run: ToolRun,
    assignment: ToolRunAssignment | None,
) -> str:
    normalized = reason.lower()
    if run.error_message:
        return "error"
    if assignment is not None and not assignment.is_terminal():
        return f"worker:{assignment.worker_id}"
    if "online worker" in normalized:
        return "worker_pool"
    if "worker slot" in normalized:
        return "worker_capacity"
    if "capability capacity" in normalized:
        return "capability_limit"
    if "scheduler" in normalized or run.status is ToolRunStatus.QUEUED:
        return "scheduler"
    if run.target.mode is ToolMode.INLINE:
        return "inline_runtime"
    if run.status is ToolRunStatus.CANCEL_REQUESTED:
        return "cancellation"
    return "-"


def _run_next_step_label(
    reason: str,
    *,
    run: ToolRun,
    assignment: ToolRunAssignment | None,
    available_workers: int,
) -> str:
    normalized = reason.lower()
    if run.error_message:
        return "inspect error"
    if assignment is not None and not assignment.is_terminal():
        if "expired" in normalized:
            return "recover expired assignment"
        if assignment.status is ToolRunAssignmentStatus.ASSIGNED:
            return "wait for worker start"
        return "monitor worker heartbeat"
    if "online worker" in normalized:
        return "start or recover worker"
    if "worker slot" in normalized or "capability capacity" in normalized:
        return "wait for capacity"
    if run.status is ToolRunStatus.QUEUED and available_workers > 0:
        return "scheduler dispatch"
    if run.status is ToolRunStatus.DISPATCHING:
        return "wait for assignment"
    if run.status is ToolRunStatus.CANCEL_REQUESTED:
        return "finish cancellation"
    if run.target.mode is ToolMode.INLINE:
        return "execute inline"
    return "monitor"


def _run_blocker_tone(reason: str, status: ToolRunStatus) -> str:
    normalized = reason.lower()
    if "expired" in normalized or "missing" in normalized:
        return "danger"
    if "waiting" in normalized or status is ToolRunStatus.CANCEL_REQUESTED:
        return "warning"
    if status in {ToolRunStatus.RUNNING, ToolRunStatus.DISPATCHING}:
        return "info"
    return "neutral"


def _capability_label(group_key: str) -> str:
    if group_key == "tool:*":
        return "Default tool groups"
    if group_key.startswith("tool:"):
        return group_key.removeprefix("tool:")
    if group_key == "capability:image":
        return "Image generation"
    if group_key == "capability:browser":
        return "Browser shared state"
    if group_key == "capability:workspace":
        return "Workspace shared state"
    if group_key == "capability:mobile":
        return "Mobile shared state"
    if group_key == "capability:session":
        return "Session shared state"
    if group_key == "capability:command":
        return "Command shared state"
    if group_key == "capability:system":
        return "System shared state"
    return _title_label(group_key.removeprefix("capability:"))


def _worker_registration_bucket(
    worker: ToolWorkerRegistration,
    *,
    now: datetime,
) -> str:
    if worker.lease_expires_at is not None and coerce_utc_datetime(
        worker.lease_expires_at,
    ) <= coerce_utc_datetime(now):
        return "lease_expired"
    if worker.status.value == "stale":
        return "stale"
    if worker.current_in_flight >= worker.max_in_flight:
        return "busy"
    if worker.current_in_flight > 0:
        return "active"
    return "idle"


def _worker_registration_counts_in_pool(
    worker: ToolWorkerRegistration,
    *,
    now: datetime,
) -> bool:
    if worker.lease_expires_at is not None:
        expires_at = coerce_utc_datetime(worker.lease_expires_at)
        if expires_at > coerce_utc_datetime(now):
            return True
        return expires_at >= coerce_utc_datetime(now) - timedelta(
            seconds=_WORKER_POOL_EXPIRED_GRACE_SECONDS,
        )
    if worker.status is ToolWorkerStatus.STALE:
        return coerce_utc_datetime(worker.heartbeat_at) >= coerce_utc_datetime(
            now,
        ) - timedelta(seconds=_WORKER_POOL_EXPIRED_GRACE_SECONDS)
    return True


def _worker_registration_status(bucket: str) -> tuple[str, str]:
    return {
        "idle": ("Online", "success"),
        "active": ("Active", "info"),
        "busy": ("Busy", "warning"),
        "stale": ("Stale", "warning"),
        "lease_expired": ("Lease Expired", "danger"),
    }.get(bucket, ("Unknown", "neutral"))


def _worker_runtime_count(worker: ToolWorkerRegistration) -> str:
    return str(len(_worker_runtime_registrations(worker)))


def _worker_provider_summary(worker: ToolWorkerRegistration) -> str:
    providers: set[str] = set()
    for registration in _worker_runtime_registrations(worker):
        concurrency_key = _optional_str(registration.get("concurrency_key"))
        runtime_key = _optional_str(registration.get("runtime_key"))
        provider_key = concurrency_key or _provider_key_from_runtime_key(runtime_key)
        if provider_key:
            providers.add(_provider_label(provider_key))
    return _join_values(tuple(sorted(providers))) or "-"


def _worker_capability_summary(worker: ToolWorkerRegistration) -> str:
    policy = worker.capabilities_payload.get("concurrency_policy")
    if not isinstance(policy, dict):
        return "-"
    parts: list[str] = []
    image_limit = _int_value(policy.get("image_max_in_flight"))
    shared_limit = _int_value(policy.get("shared_state_max_in_flight"))
    default_limit = _int_value(policy.get("default_max_in_flight"))
    if image_limit:
        parts.append(f"image {image_limit}/worker")
    if shared_limit:
        parts.append(f"shared {shared_limit}/worker")
    if default_limit:
        parts.append(f"default {default_limit}/worker")
    return _join_values(tuple(parts)) or "-"


def _worker_runtime_registrations(
    worker: ToolWorkerRegistration,
) -> tuple[dict[str, Any], ...]:
    registry = worker.capabilities_payload.get("runtime_registry")
    if not isinstance(registry, dict):
        return ()
    registrations = registry.get("registrations")
    if not isinstance(registrations, list):
        return ()
    return tuple(item for item in registrations if isinstance(item, dict))


def _provider_key_from_runtime_key(runtime_key: str | None) -> str | None:
    if runtime_key is None:
        return None
    runtime_key_lower = runtime_key.strip().lower()
    for prefix in ("openapi.", "mcp."):
        if runtime_key_lower.startswith(prefix):
            parts = runtime_key_lower.split(".")
            if len(parts) >= 2 and parts[1].strip():
                return f"{prefix.removesuffix('.')}:{parts[1].strip()}"
    if runtime_key_lower.startswith("openai_"):
        return "provider:openai"
    return runtime_key_lower or None


def _worker_bucket(run: ToolRun, *, now: datetime) -> str:
    if (
        run.status
        in {
            ToolRunStatus.DISPATCHING,
            ToolRunStatus.RUNNING,
            ToolRunStatus.CANCEL_REQUESTED,
        }
        and run.lease_expires_at is not None
        and coerce_utc_datetime(run.lease_expires_at) < coerce_utc_datetime(now)
    ):
        return "lease_expired"
    return run.status.value


def _assignment_status_label(assignment: ToolRunAssignment | None) -> str:
    if assignment is None:
        return "-"
    return _title_label(assignment.status.value)


def _assignment_id(assignment: ToolRunAssignment | None) -> str:
    return assignment.id if assignment is not None else "-"


def _lease_state_label(
    run: ToolRun,
    *,
    assignment: ToolRunAssignment | None,
    now: datetime,
) -> str:
    if assignment is not None:
        if assignment.lease_expires_at is None:
            return "Released" if assignment.is_terminal() else "-"
        if _assignment_lease_expired(assignment, now=now):
            return "Expired"
        return "Active"
    if run.lease_expires_at is None:
        return "Released" if run.is_terminal() else "-"
    if coerce_utc_datetime(run.lease_expires_at) <= coerce_utc_datetime(now):
        return "Expired"
    return "Active"


def _lease_expires_label(
    run: ToolRun,
    *,
    assignment: ToolRunAssignment | None,
) -> str:
    value = (
        assignment.lease_expires_at
        if assignment is not None
        else run.lease_expires_at
    )
    return format_datetime_utc(value) if value is not None else "-"


def _assignment_lease_expired(
    assignment: ToolRunAssignment,
    *,
    now: datetime,
) -> bool:
    return (
        assignment.lease_expires_at is not None
        and coerce_utc_datetime(assignment.lease_expires_at)
        <= coerce_utc_datetime(now)
    )


def _run_time(run: ToolRun) -> datetime:
    return run.completed_at or run.heartbeat_at or run.started_at or run.created_at


def _runs_since(runs: list[ToolRun], *, since: datetime) -> list[ToolRun]:
    threshold = coerce_utc_datetime(since)
    return [
        run
        for run in runs
        if coerce_utc_datetime(_run_time(run)) >= threshold
    ]


def _run_duration_label(
    run: ToolRun,
    *,
    assignment: ToolRunAssignment | None = None,
    now: datetime,
) -> str:
    return _duration_label(_duration_seconds(run, assignment=assignment, now=now))


def _run_progress_label(
    run: ToolRun,
    *,
    tool: Tool | None,
    assignment: ToolRunAssignment | None,
    now: datetime,
) -> str:
    return f"{_run_progress_percent(run, tool=tool, assignment=assignment, now=now)}%"


def _run_progress_percent(
    run: ToolRun,
    *,
    tool: Tool | None,
    assignment: ToolRunAssignment | None,
    now: datetime,
) -> int:
    if run.status is ToolRunStatus.SUCCEEDED:
        return 100
    if run.status in {
        ToolRunStatus.FAILED,
        ToolRunStatus.CANCELLED,
        ToolRunStatus.TIMED_OUT,
    }:
        return 100
    if run.status is ToolRunStatus.CREATED:
        return 0
    if run.status is ToolRunStatus.QUEUED:
        return 5
    if run.status is ToolRunStatus.DISPATCHING:
        return 15
    if run.status is ToolRunStatus.CANCEL_REQUESTED:
        return 95
    timeout = max(
        int(tool.execution_policy.timeout_seconds) if tool is not None else 30,
        1,
    )
    elapsed = _duration_seconds(run, assignment=assignment, now=now)
    return min(95, max(20, int(round((elapsed / timeout) * 100))))


def _duration_seconds(
    run: ToolRun,
    *,
    assignment: ToolRunAssignment | None = None,
    now: datetime,
) -> int:
    if assignment is not None:
        start = assignment.started_at or assignment.assigned_at
        end = (
            assignment.completed_at
            if assignment.is_terminal() and assignment.completed_at
            else now
        )
    else:
        start = run.started_at or run.created_at
        end = run.completed_at if run.is_terminal() and run.completed_at else now
    return max(
        int((coerce_utc_datetime(end) - coerce_utc_datetime(start)).total_seconds()),
        0,
    )


def _age_label(value: datetime | None, *, now: datetime) -> str:
    if value is None:
        return "-"
    seconds = max(
        int((coerce_utc_datetime(now) - coerce_utc_datetime(value)).total_seconds()),
        0,
    )
    return _duration_label(seconds)


def _duration_label(seconds: int) -> str:
    seconds = max(seconds, 0)
    if seconds < 60:
        return f"{seconds}s"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {seconds}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m"


def _seconds_label(seconds: float) -> str:
    value = max(float(seconds), 0.0)
    if value <= 0:
        return "0s"
    if value < 1:
        return f"{int(round(value * 1000))}ms"
    if value < 60:
        return f"{value:.1f}s" if value < 10 else f"{int(round(value))}s"
    return _duration_label(int(round(value)))


def _run_priority_label(run: ToolRun) -> str:
    for key in ("priority", "run_priority", "queue_priority"):
        value = _context_str(run, key)
        if value:
            return value
    return "-"


def _is_waiting_io_reason(reason: str) -> bool:
    normalized = reason.lower()
    return any(
        token in normalized
        for token in (
            "provider",
            "limiter",
            "rate",
            "capability capacity",
            "external",
            "io",
        )
    )


def _worker_success_rate_label(worker_id: str, *, runs: list[ToolRun]) -> str:
    terminal_runs = [
        run
        for run in runs
        if run.worker_id == worker_id and run.is_terminal()
    ]
    if not terminal_runs:
        return "-"
    successes = sum(1 for run in terminal_runs if run.status is ToolRunStatus.SUCCEEDED)
    return _percent_label(successes, len(terminal_runs))


def _worker_avg_duration_label(
    worker_id: str,
    *,
    runs: list[ToolRun],
    assignment_by_run: dict[str, ToolRunAssignment],
    now: datetime,
) -> str:
    durations = [
        _duration_seconds(run, assignment=assignment_by_run.get(run.id), now=now)
        for run in runs
        if run.worker_id == worker_id and run.is_terminal()
    ]
    if not durations:
        return "-"
    return _duration_label(int(round(sum(durations) / len(durations))))


def _percent_label(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "0%"
    return f"{round((numerator / denominator) * 100)}%"


def _queue_oldest_label(
    runs: list[ToolRun],
    *,
    assignment_by_run: dict[str, ToolRunAssignment],
    now: datetime,
) -> str:
    starts: list[datetime] = []
    for run in runs:
        assignment = assignment_by_run.get(run.id)
        if assignment is not None and not assignment.is_terminal():
            starts.append(assignment.started_at or assignment.assigned_at)
            continue
        starts.append(run.created_at)
    return _age_label(min(starts), now=now) if starts else "-"


def _queue_reason_tone(reason: str) -> str:
    normalized = reason.lower()
    if "expired" in normalized or "missing" in normalized:
        return "danger"
    if "assigned" in normalized or "running" in normalized:
        return "info"
    if "queued" in normalized or "cancel" in normalized:
        return "warning"
    return "neutral"


def _result_summary(run: ToolRun) -> str:
    if run.error_message:
        return _truncate(run.error_message, 96)
    payload = _result_payload(run)
    blocks = payload.get("content")
    if blocks:
        return _truncate(describe_content_for_text_fallback(blocks), 96)
    details = payload.get("details")
    if details is not None:
        return _truncate(_payload_summary(details), 96)
    if run.status is ToolRunStatus.SUCCEEDED:
        return "Completed"
    return "-"


def _payload_summary(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        for key in ("output_text", "message", "summary", "text"):
            item = value.get(key)
            if isinstance(item, str) and item.strip():
                return item.strip()
        return f"{len(value)} fields"
    if isinstance(value, list):
        return f"{len(value)} items"
    return str(value)


def _result_payload(run: ToolRun) -> dict[str, Any]:
    payload = run.result_payload
    if isinstance(payload, dict):
        return payload
    return {}


def _artifact_refs(
    run: ToolRun,
    *,
    artifact_service: Any | None,
) -> list[dict[str, str]]:
    payload = _result_payload(run)
    refs: list[dict[str, str]] = []
    seen: set[str] = set()

    for block in _result_blocks(payload):
        artifact = _artifact_from_mapping(block, artifact_service=artifact_service)
        if artifact is None or artifact["artifact_id"] in seen:
            continue
        refs.append(artifact)
        seen.add(artifact["artifact_id"])

    metadata = payload.get("metadata")
    if isinstance(metadata, dict):
        for artifact in _artifact_refs_from_metadata(
            metadata,
            artifact_service=artifact_service,
        ):
            if artifact["artifact_id"] in seen:
                continue
            refs.append(artifact)
            seen.add(artifact["artifact_id"])

    return refs


def _result_blocks(payload: dict[str, Any]) -> list[dict[str, Any]]:
    blocks = payload.get("content")
    if not isinstance(blocks, list):
        return []
    return [dict(block) for block in blocks if isinstance(block, dict)]


def _artifact_refs_from_metadata(
    metadata: dict[str, Any],
    *,
    artifact_service: Any | None,
) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    artifact_id = metadata.get("artifact_id")
    if isinstance(artifact_id, str) and artifact_id.strip():
        refs.append(
            _artifact_ref(
                artifact_id=artifact_id.strip(),
                name=_optional_str(metadata.get("name")) or artifact_id.strip(),
                kind=_optional_str(metadata.get("kind")) or "artifact",
                mime_type=_optional_str(metadata.get("mime_type")) or "-",
                size_bytes=_optional_int(metadata.get("size_bytes")),
                width=_optional_int(metadata.get("width")),
                height=_optional_int(metadata.get("height")),
                preview_url=_optional_str(metadata.get("preview_url")),
                download_url=_optional_str(metadata.get("download_url")),
                artifact_service=artifact_service,
            ),
        )
    artifact_ids = metadata.get("artifact_ids")
    if isinstance(artifact_ids, list):
        for item in artifact_ids:
            if isinstance(item, str) and item.strip():
                refs.append(
                    _artifact_ref(
                        artifact_id=item.strip(),
                        name=item.strip(),
                        kind="artifact",
                        mime_type="-",
                        artifact_service=artifact_service,
                    ),
                )
    artifacts = metadata.get("artifacts")
    if isinstance(artifacts, list):
        for item in artifacts:
            if isinstance(item, dict):
                artifact = _artifact_from_mapping(
                    item,
                    artifact_service=artifact_service,
                )
                if artifact is not None:
                    refs.append(artifact)
    return refs


def _artifact_from_mapping(
    value: dict[str, Any],
    *,
    artifact_service: Any | None,
) -> dict[str, str] | None:
    artifact_id = _optional_str(value.get("artifact_id"))
    if artifact_id is None:
        return None
    block_type = _optional_str(value.get("type")) or "artifact"
    if block_type == "image_ref":
        kind = "image"
    elif block_type == "file_ref":
        kind = "file"
    else:
        kind = block_type
    return _artifact_ref(
        artifact_id=artifact_id,
        name=_optional_str(value.get("name")) or artifact_id,
        kind=kind,
        mime_type=_optional_str(value.get("mime_type")) or "-",
        size_bytes=_optional_int(value.get("size_bytes")),
        width=_optional_int(value.get("width")),
        height=_optional_int(value.get("height")),
        preview_url=_optional_str(value.get("preview_url")),
        download_url=_optional_str(value.get("download_url")),
        artifact_service=artifact_service,
    )


def _artifact_ref(
    *,
    artifact_id: str,
    name: str,
    kind: str,
    mime_type: str,
    size_bytes: int | None = None,
    width: int | None = None,
    height: int | None = None,
    preview_url: str | None = None,
    download_url: str | None = None,
    artifact_service: Any | None = None,
) -> dict[str, str]:
    artifact = _safe_get_artifact(artifact_service, artifact_id)
    if artifact is not None:
        artifact_kind = getattr(artifact, "kind", kind)
        kind = str(getattr(artifact_kind, "value", artifact_kind) or kind)
        name = _optional_str(getattr(artifact, "name", None)) or name
        mime_type = _optional_str(getattr(artifact, "mime_type", None)) or mime_type
        size_bytes = _optional_int(getattr(artifact, "size_bytes", None))
        width = _optional_int(getattr(artifact, "width", None))
        height = _optional_int(getattr(artifact, "height", None))
        preview_url = preview_url or (
            f"/artifacts/{artifact_id}/preview" if kind == "image" else None
        )
        download_url = download_url or f"/artifacts/{artifact_id}/download"
    return {
        "artifact_id": artifact_id,
        "name": name,
        "kind": kind,
        "mime_type": mime_type,
        "size": _bytes_label(size_bytes),
        "dimensions": _dimensions_label(width=width, height=height),
        "preview_url": preview_url or "",
        "download_url": download_url or "",
    }


def _safe_get_artifact(artifact_service: Any | None, artifact_id: str) -> Any | None:
    if artifact_service is None or not hasattr(artifact_service, "get_artifact"):
        return None
    try:
        return artifact_service.get_artifact(artifact_id)
    except Exception:  # noqa: BLE001
        return None


def _bytes_label(size_bytes: int | None) -> str:
    if size_bytes is None or size_bytes < 0:
        return "-"
    if size_bytes < 1024:
        return f"{size_bytes} B"
    kib = size_bytes / 1024
    if kib < 1024:
        return f"{kib:.1f} KiB"
    return f"{kib / 1024:.1f} MiB"


def _dimensions_label(*, width: int | None, height: int | None) -> str:
    if width is None or height is None or width <= 0 or height <= 0:
        return "-"
    return f"{width}x{height}"


def _looks_like_access_failure(run: ToolRun) -> bool:
    message = (run.error_message or "").lower()
    return any(
        marker in message
        for marker in (
            "access",
            "auth",
            "credential",
            "permission",
            "forbidden",
            "api key",
            "login",
            "401",
            "403",
        )
    )


def _tool_run_contexts(
    run_query: Any | None,
    runs: list[ToolRun],
) -> dict[str, dict[str, str]]:
    if run_query is None or not hasattr(run_query, "find_execution_step_items_by_owner"):
        return {}
    contexts: dict[str, dict[str, str]] = {}
    for run in runs:
        context = _execution_owner_context(
            run_query,
            ExecutionOwnerReference(owner_kind="tool_run", owner_id=run.id),
        )
        if not context:
            continue
        existing = contexts.get(run.id)
        if existing is None or context.get("updated_at", "") > existing.get("updated_at", ""):
            contexts[run.id] = context
    return {
        run_id: {
            key: value
            for key, value in context.items()
            if key != "updated_at"
        }
        for run_id, context in contexts.items()
    }


def _execution_owner_context(
    run_query: Any,
    owner: ExecutionOwnerReference,
) -> dict[str, str] | None:
    try:
        items = run_query.find_execution_step_items_by_owner(owner)
    except Exception:
        return None
    if not items:
        return None
    item = max(items, key=_execution_item_updated_at)
    try:
        step = run_query.get_execution_step(item.step_id)
    except Exception:
        step = None
    try:
        run = run_query.get_run(item.turn_id)
    except Exception:
        run = None
    run_id = _optional_metadata_text(getattr(run, "id", None)) or _optional_metadata_text(
        getattr(item, "turn_id", None),
    )
    if run_id is None:
        return None
    metadata = getattr(run, "metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}
    trace_id = _optional_metadata_text(metadata.get("trace_id")) or run_id
    summary_payload = item.summary_payload if isinstance(item.summary_payload, dict) else {}
    tool_call_id = _optional_metadata_text(item.correlation_key) or _optional_metadata_text(
        summary_payload.get("tool_call_id"),
    )
    return {
        "run_id": run_id,
        "turn_id": _optional_metadata_text(metadata.get("turn_id")) or item.turn_id,
        "trace_id": trace_id,
        "session_key": _optional_metadata_text(metadata.get("session_key")) or "-",
        "route": f"/ui/workbench/runs/{run_id}",
        "trace_route": f"/ui/trace/{trace_id}?step_id={item.step_id}",
        "chain_id": item.chain_id,
        "step_id": item.step_id,
        "step_kind": _enum_value(getattr(step, "kind", None)),
        "step_status": _enum_value(getattr(step, "status", None)),
        "item_status": _enum_value(getattr(item, "status", None)),
        "tool_call_id": tool_call_id or "-",
        "updated_at": _execution_item_updated_at(item),
    }


def _execution_item_updated_at(item: Any) -> str:
    updated_at = getattr(item, "updated_at", None)
    if isinstance(updated_at, datetime):
        return format_datetime_utc(updated_at)
    return str(updated_at or "")


def _enum_value(value: Any) -> str:
    raw = getattr(value, "value", value)
    if raw is None:
        return "-"
    normalized = str(raw).strip()
    return normalized or "-"


def _source_label(
    run: ToolRun,
    *,
    run_context: Mapping[str, str] | None = None,
) -> str:
    run_id = _orchestration_run_id(run, run_context=run_context)
    tool_call_id = (
        _context_value(run_context, "tool_call_id", blank_as_none=True)
        or _metadata_str(run, "tool_call_id")
    )
    step_id = _context_value(
        run_context,
        "step_id",
        blank_as_none=True,
    ) or _context_str(run, "step_id")
    turn_id = _context_value(
        run_context,
        "turn_id",
        blank_as_none=True,
    ) or _context_str(run, "turn_id")
    if run_id and tool_call_id:
        return f"{run_id} / {tool_call_id}"
    if run_id and step_id:
        return f"{run_id} / {step_id}"
    if run_id and turn_id:
        return f"{run_id} / {turn_id}"
    return run_id or turn_id or "-"


def _source_route(
    run: ToolRun,
    *,
    run_context: Mapping[str, str] | None = None,
) -> str:
    route = _context_value(run_context, "route", blank_as_none=True)
    if route:
        return route
    run_id = _orchestration_run_id(run, run_context=run_context)
    return f"/ui/workbench/runs/{run_id}" if run_id else "-"


def _trace_id(
    run: ToolRun,
    *,
    run_context: Mapping[str, str] | None = None,
) -> str:
    return (
        _context_value(run_context, "trace_id", blank_as_none=True)
        or _context_str(run, "trace_id")
        or _context_str(run, "correlation_id")
        or _metadata_str(run, "orchestration_run_id")
        or _context_str(run, "run_id")
        or run.id
    )


def _trace_route(
    run: ToolRun,
    *,
    run_context: Mapping[str, str] | None = None,
) -> str:
    route = _context_value(run_context, "trace_route", blank_as_none=True)
    if route:
        return route
    return f"/ui/trace/{_trace_id(run, run_context=run_context)}"


def _orchestration_run_id(
    run: ToolRun,
    *,
    run_context: Mapping[str, str] | None = None,
) -> str | None:
    return (
        _context_value(run_context, "run_id", blank_as_none=True)
        or _metadata_str(run, "orchestration_run_id")
        or _context_str(run, "run_id")
    )


def _context_value(
    run_context: Mapping[str, str] | None,
    key: str,
    *,
    blank_as_none: bool = False,
) -> str | None:
    if run_context is None:
        return None if blank_as_none else "-"
    value = run_context.get(key)
    if value is None:
        return None if blank_as_none else "-"
    normalized = str(value).strip()
    if not normalized or normalized == "-":
        return None if blank_as_none else "-"
    return normalized


def _context_str(run: ToolRun, key: str) -> str | None:
    context = run.invocation_context
    return context.get_str(key) if context is not None else None


def _metadata_str(run: ToolRun, key: str) -> str | None:
    value = run.metadata.get(key)
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _tool_lookup(tools: list[Tool]) -> dict[str, Tool]:
    return {tool.id: tool for tool in tools}


def _tool_label(run: ToolRun, tools_by_id: dict[str, Tool]) -> str:
    tool = tools_by_id.get(run.tool_id)
    if tool is None:
        return run.tool_id
    return tool.id if tool.id == tool.name else f"{tool.name} ({tool.id})"


def _tone_for_status(status: ToolRunStatus) -> str:
    if status is ToolRunStatus.SUCCEEDED:
        return "success"
    if status in {ToolRunStatus.FAILED, ToolRunStatus.TIMED_OUT}:
        return "danger"
    if status in {ToolRunStatus.CANCEL_REQUESTED, ToolRunStatus.CANCELLED}:
        return "warning"
    if status in {ToolRunStatus.RUNNING, ToolRunStatus.DISPATCHING}:
        return "info"
    return "neutral"


def _tone_for_kind(kind: str) -> str:
    return {
        "function": "info",
        "http": "success",
        "mcp": "warning",
        "workflow": "neutral",
        "unknown": "danger",
    }.get(kind, "neutral")


def _tone_for_tool_rank(index: int) -> str:
    return ("info", "success", "warning", "neutral")[index % 4]


def _status_label(status: ToolRunStatus) -> str:
    return _title_label(status.value)


def _title_label(value: str) -> str:
    return value.replace("_", " ").replace("-", " ").title()


def _first(values: tuple[Any, ...] | list[Any]) -> Any | None:
    return values[0] if values else None


def _record_value(record: Any | None, field_name: str) -> str:
    if record is None:
        return ""
    value = getattr(record, field_name, None)
    if value is None:
        return ""
    raw = getattr(value, "value", value)
    return str(raw).strip()


def _record_text(record: Any | None, field_name: str) -> str:
    return _record_value(record, field_name)


def _record_datetime_label(record: Any | None, field_name: str) -> str:
    value = getattr(record, field_name, None) if record is not None else None
    if isinstance(value, datetime):
        return format_datetime_utc(value)
    return _display(value)


def _source_health_tone(status: str, discovery_status: str | None) -> str:
    if status in {"error", "deleted"} or discovery_status == "failed":
        return "danger"
    if status == "disabled":
        return "warning"
    return "success" if status == "active" else "neutral"


def _columns(*items: tuple[str, str]) -> tuple[OperationsTableColumnModel, ...]:
    return tuple(
        OperationsTableColumnModel(key=key, label=label) for key, label in items
    )


def _optional_str(value: object | None) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _sequence(value: object) -> tuple[object, ...]:
    if value is None:
        return ()
    if isinstance(value, tuple | list):
        return tuple(value)
    return (value,)


def _optional_int(value: object | None) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip():
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _int_value(value: object | None) -> int:
    return _optional_int(value) or 0


def _float(value: object | None) -> float:
    if isinstance(value, bool) or value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str) and value.strip():
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0


def _display(value: object | None) -> str:
    if value is None:
        return "-"
    text = str(value).strip()
    return text or "-"


def _join_values(values: tuple[str, ...] | list[str]) -> str:
    normalized = [value.strip() for value in values if value and value.strip()]
    return ", ".join(normalized) if normalized else "-"


def _truncate(value: str, max_length: int) -> str:
    text = value.strip()
    if len(text) <= max_length:
        return text
    return f"{text[: max_length - 3]}..."
