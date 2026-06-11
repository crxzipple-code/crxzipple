from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from crxzipple.modules.dispatch.domain import DispatchTask, DispatchTaskStatus
from crxzipple.modules.orchestration.application.dispatch_owner_kinds import (
    ORCHESTRATION_INGRESS_DISPATCH_OWNER_KIND,
    ORCHESTRATION_STEP_DISPATCH_OWNER_KIND,
)
from crxzipple.modules.orchestration.application.ports import (
    OrchestrationExecutorLeaseQueryPort,
    OrchestrationRunQueryPort,
)
from crxzipple.modules.orchestration.application.coordinators.continuation_tasks import (
    OrchestrationContinuationStatus,
    OrchestrationContinuationTask,
)
from crxzipple.modules.orchestration.domain import (
    ExecutionChain,
    ExecutionStep,
    ExecutionStepItem,
    OrchestrationExecutorLease,
    OrchestrationIngressRequest,
    OrchestrationRun,
)
from crxzipple.modules.orchestration.domain.value_objects import (
    ExecutionChainStatus,
    ExecutionStepItemStatus,
    ExecutionStepStatus,
    OrchestrationIngressStatus,
    OrchestrationRunStage,
    OrchestrationRunStatus,
    utcnow,
)
from crxzipple.modules.operations.application.read_models.models import (
    MetricCardModel,
    OperationsModuleOverview,
    OperationsTabModel,
    RuntimeActionModel,
    OperationsChartSectionModel,
    OperationsChartSegmentModel,
    OperationsKeyValueItemModel,
    OperationsKeyValueSectionModel,
    OperationsModuleRoleModel,
    OperationsTableColumnModel,
    OperationsTableRowModel,
    OperationsTableSectionModel,
)
from crxzipple.modules.operations.application.observation import (
    OperationsObservedEvent,
)
from crxzipple.shared.time import coerce_utc_datetime, format_datetime_utc

_RECENT_FAILURE_HEALTH_SECONDS = 300


class OrchestrationIngressRequestQueryPort(Protocol):
    def list_ingress_requests(
        self,
        *,
        status: OrchestrationIngressStatus | None = None,
    ) -> list[OrchestrationIngressRequest]: ...


class OrchestrationContinuationQueryPort(Protocol):
    def list_continuation_tasks(
        self,
        *,
        status: OrchestrationContinuationStatus | None = None,
    ) -> list[OrchestrationContinuationTask]: ...


class OrchestrationDispatchTaskQueryPort(Protocol):
    def list_dispatch_tasks(
        self,
        *,
        status: DispatchTaskStatus | None = None,
        owner_kind: str | None = None,
        lane_key: str | None = None,
    ) -> list[DispatchTask]: ...


class OperationsObservationReadPort(Protocol):
    def get_module_observation(self, module: str) -> Any | None: ...


@dataclass(frozen=True, slots=True)
class OrchestrationOperationsPage:
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
    scheduler_status: OperationsKeyValueSectionModel
    backpressure: OperationsChartSectionModel
    stuck_runs: OperationsTableSectionModel
    policy_limits: OperationsKeyValueSectionModel
    run_queue: OperationsTableSectionModel
    execution_chains: OperationsTableSectionModel
    repeated_probes: OperationsTableSectionModel
    lane_locks: OperationsTableSectionModel
    executor_overview: OperationsTableSectionModel
    ingress_queue: OperationsTableSectionModel
    recent_failures: OperationsTableSectionModel
    ops_event_log: OperationsTableSectionModel


@dataclass(slots=True)
class OrchestrationOperationsReadModelProvider:
    run_query: OrchestrationRunQueryPort
    executor_lease_query: OrchestrationExecutorLeaseQueryPort
    ingress_query: OrchestrationIngressRequestQueryPort | None = None
    continuation_query: OrchestrationContinuationQueryPort | None = None
    dispatch_query: OrchestrationDispatchTaskQueryPort | None = None
    operations_observation: OperationsObservationReadPort | None = None
    runtime_bootstrap_config: Any | None = None
    worker_lease_seconds: int | None = None
    worker_heartbeat_seconds: float | None = None

    def overview(self) -> OperationsModuleOverview:
        now = utcnow()
        runs = self.run_query.list_runs()
        leases = self.executor_lease_query.list_executor_leases(status=None)
        ingress_requests = _list_ingress_requests(self.ingress_query)
        dispatch_tasks = _list_dispatch_tasks(self.dispatch_query)
        ingress_dispatch_by_request_id = _dispatch_tasks_by_owner(
            dispatch_tasks,
            owner_kind=ORCHESTRATION_INGRESS_DISPATCH_OWNER_KIND,
        )
        step_dispatch_by_run_id = _dispatch_tasks_by_payload_ref(
            dispatch_tasks,
            owner_kind=ORCHESTRATION_STEP_DISPATCH_OWNER_KIND,
        )
        pending_ingress_requests = _pending_ingress_requests(
            ingress_requests,
            dispatch_task_by_request_id=ingress_dispatch_by_request_id,
        )
        visible_ingress_count = len(pending_ingress_requests)
        queued_runs = [
            run
            for run in runs
            if _run_is_dispatch_queued(run, step_dispatch_by_run_id.get(run.id))
        ]
        running_runs = [
            run for run in runs if run.status is OrchestrationRunStatus.RUNNING
        ]
        waiting_runs = [
            run for run in runs if run.status is OrchestrationRunStatus.WAITING
        ]
        failed_runs = [
            run for run in runs if run.status is OrchestrationRunStatus.FAILED
        ]
        recent_failed_runs = _recent_failed_runs(failed_runs, now=now)
        online_leases = [
            lease for lease in leases if lease.counts_toward_capacity(now=now)
        ]
        capacity = sum(lease.max_inflight_assignments for lease in online_leases)
        inflight = sum(lease.inflight_assignment_count for lease in online_leases)
        available = sum(
            lease.available_assignment_slots(now=now) for lease in online_leases
        )
        health = _health(
            queued_runs=queued_runs,
            running_runs=running_runs,
            waiting_runs=waiting_runs,
            failed_runs=recent_failed_runs,
            available_executor_slots=available,
        )

        return OperationsModuleOverview(
            module="orchestration",
            title="Orchestration",
            subtitle="监控调度状态、队列导航、阻塞异常的 Run 与资源分配。",
            health=health,
            updated_at=format_datetime_utc(now),
            metrics=(
                MetricCardModel(
                    id="health",
                    label="Overall Health",
                    value=_health_label(health),
                    delta=_health_delta(health),
                    tone=_health_tone(health),
                ),
                MetricCardModel(
                    id="ingress",
                    label="Ingress Queue",
                    value=str(visible_ingress_count),
                    delta="ingress requests",
                    tone="neutral",
                ),
                MetricCardModel(
                    id="ingress_rate",
                    label="Ingress Rate",
                    value=_ingress_rate_label(
                        ingress_requests,
                        fallback_runs=[],
                        now=now,
                    ),
                    delta="requests/sec",
                    tone="info",
                ),
                MetricCardModel(
                    id="active",
                    label="Active Runs",
                    value=str(len(running_runs)),
                    delta=f"{len(waiting_runs)} waiting",
                    tone="info",
                ),
                MetricCardModel(
                    id="run_queue",
                    label="Run Queue",
                    value=str(len(queued_runs)),
                    delta=f"{available} executor slots available",
                    tone="warning" if queued_runs else "success",
                ),
                MetricCardModel(
                    id="executor_capacity",
                    label="Executor Capacity",
                    value=f"{inflight}/{capacity}",
                    delta=f"{len(online_leases)} online workers",
                    tone="success" if available else "warning",
                ),
                _failed_metric(
                    failed_runs=failed_runs,
                    recent_failed_runs=recent_failed_runs,
                    cancelled_runs=[],
                ),
            ),
            queue=_queue_rows(
                queued_runs,
                dispatch_task_by_run_id=step_dispatch_by_run_id,
                now=now,
            ),
            lane_locks=_lane_lock_rows(running_runs, now=now),
            executor=_executor_rows(leases, running_runs=running_runs, now=now),
            actions=(
                RuntimeActionModel(
                    id="open_run",
                    label="Open Run",
                    owner="orchestration",
                    kind="navigation",
                    method="GET",
                    endpoint="/ui/workbench/runs/{run_id}",
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
                    id="cancel_run",
                    label="Cancel Run",
                    owner="orchestration",
                    risk="controlled",
                    requires_confirmation=True,
                    audit_event="orchestration.run.cancel",
                    method="POST",
                    endpoint="/operations/orchestration/runs/{run_id}/cancel",
                ),
                RuntimeActionModel(
                    id="force_release_lane",
                    label="Force Release Lane",
                    owner="orchestration",
                    risk="dangerous",
                    allowed=False,
                    disabled_reason=(
                        "Lane force-release is not exposed as an operations action; "
                        "recover the owning run or worker lease instead."
                    ),
                    requires_confirmation=True,
                    reason_required=True,
                ),
            ),
        )

    def page(self) -> OrchestrationOperationsPage:
        now = utcnow()
        runs = self.run_query.list_runs()
        leases = self.executor_lease_query.list_executor_leases(status=None)
        ingress_requests = _list_ingress_requests(self.ingress_query)
        continuation_tasks = _list_continuation_tasks(self.continuation_query)
        dispatch_tasks = _list_dispatch_tasks(self.dispatch_query)
        ingress_dispatch_by_request_id = _dispatch_tasks_by_owner(
            dispatch_tasks,
            owner_kind=ORCHESTRATION_INGRESS_DISPATCH_OWNER_KIND,
        )
        step_dispatch_by_run_id = _dispatch_tasks_by_payload_ref(
            dispatch_tasks,
            owner_kind=ORCHESTRATION_STEP_DISPATCH_OWNER_KIND,
        )
        observed_events = _recent_operations_events(
            observation=self.operations_observation,
            module="orchestration",
            limit=60,
        )
        observer_state = _module_observation(
            self.operations_observation,
            module="orchestration",
        )
        operations_event_records: tuple[Any, ...] = observed_events
        pending_ingress_requests = _pending_ingress_requests(
            ingress_requests,
            dispatch_task_by_request_id=ingress_dispatch_by_request_id,
        )
        counts = Counter(run.status for run in runs)
        visible_ingress_count = len(pending_ingress_requests)
        queued_runs = [
            run
            for run in runs
            if _run_is_dispatch_queued(run, step_dispatch_by_run_id.get(run.id))
        ]
        running_runs = [
            run for run in runs if run.status is OrchestrationRunStatus.RUNNING
        ]
        waiting_runs = [
            run for run in runs if run.status is OrchestrationRunStatus.WAITING
        ]
        failed_runs = [
            run for run in runs if run.status is OrchestrationRunStatus.FAILED
        ]
        recent_failed_runs = _recent_failed_runs(failed_runs, now=now)
        cancelled_runs = [
            run for run in runs if run.status is OrchestrationRunStatus.CANCELLED
        ]
        backpressure_total = len(queued_runs) + len(waiting_runs)
        completed_count = counts[OrchestrationRunStatus.COMPLETED]
        online_leases = [
            lease for lease in leases if lease.counts_toward_capacity(now=now)
        ]
        capacity = sum(lease.max_inflight_assignments for lease in online_leases)
        inflight = sum(lease.inflight_assignment_count for lease in online_leases)
        available = sum(
            lease.available_assignment_slots(now=now) for lease in online_leases
        )
        health = _health(
            queued_runs=queued_runs,
            running_runs=running_runs,
            waiting_runs=waiting_runs,
            failed_runs=recent_failed_runs,
            available_executor_slots=available,
        )
        actions = (
            RuntimeActionModel(
                id="open_run",
                label="Open Run",
                owner="orchestration",
                kind="navigation",
                method="GET",
                endpoint="/ui/workbench/runs/{run_id}",
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
                id="cancel_run",
                label="Cancel Run",
                owner="orchestration",
                risk="controlled",
                requires_confirmation=True,
                audit_event="orchestration.run.cancel",
                method="POST",
                endpoint="/operations/orchestration/runs/{run_id}/cancel",
            ),
            RuntimeActionModel(
                id="requeue",
                label="Requeue",
                owner="orchestration",
                risk="controlled",
                requires_confirmation=True,
                audit_event="orchestration.run.resume",
                method="POST",
                endpoint="/operations/orchestration/runs/{run_id}/resume",
            ),
            RuntimeActionModel(
                id="force_release_lane",
                label="Force Release Lane",
                owner="orchestration",
                risk="dangerous",
                allowed=False,
                disabled_reason=(
                    "Lane force-release is not exposed as an operations action; "
                    "recover the owning run or worker lease instead."
                ),
                requires_confirmation=True,
                reason_required=True,
            ),
        )

        approval_waiting_count = len(
            [
                run
                for run in waiting_runs
                if run.stage is OrchestrationRunStage.WAITING_FOR_CONFIRMATION
            ],
        )
        execution_chains = _execution_chain_section(
            self.run_query,
            runs,
            dispatch_task_by_run_id=step_dispatch_by_run_id,
            now=now,
        )
        repeated_probes = _repeated_probe_section(runs)

        return OrchestrationOperationsPage(
            module="orchestration",
            title="Orchestration",
            subtitle="调度器、运行队列、Lane Lock、Executor、故障与操作事件的统一控制台。",
            health=health,
            updated_at=format_datetime_utc(now),
            auto_refresh=True,
            role=OperationsModuleRoleModel(
                label="Admin",
                can_operate=True,
                scope="orchestration",
            ),
            metrics=(
                MetricCardModel(
                    id="health",
                    label="Overall Health",
                    value=_health_label(health),
                    delta=_health_delta(health),
                    tone=_health_tone(health),
                ),
                MetricCardModel(
                    id="ingress",
                    label="Ingress Queue",
                    value=str(visible_ingress_count),
                    delta="ingress requests",
                    tone="neutral",
                ),
                MetricCardModel(
                    id="ingress_rate",
                    label="Ingress Rate",
                    value=_ingress_rate_label(
                        ingress_requests,
                        fallback_runs=[],
                        now=now,
                    ),
                    delta="requests/sec",
                    tone="info",
                ),
                MetricCardModel(
                    id="active",
                    label="Active Runs",
                    value=str(len(running_runs)),
                    delta=f"{len(waiting_runs)} waiting",
                    tone="info",
                ),
                MetricCardModel(
                    id="run_queue",
                    label="Run Queue",
                    value=str(len(queued_runs)),
                    delta=f"{len(waiting_runs)} waiting",
                    tone="warning" if queued_runs else "success",
                ),
                MetricCardModel(
                    id="backpressure",
                    label="Backpressure",
                    value=str(backpressure_total),
                    delta="Waiting runs",
                    tone="warning" if backpressure_total else "success",
                ),
                MetricCardModel(
                    id="approval_waiting",
                    label="Approval Waiting",
                    value=str(approval_waiting_count),
                    delta="Monitoring only",
                    tone="warning" if approval_waiting_count else "success",
                ),
                _failed_metric(
                    failed_runs=failed_runs,
                    recent_failed_runs=recent_failed_runs,
                    cancelled_runs=cancelled_runs,
                ),
                MetricCardModel(
                    id="latency",
                    label="Average Latency",
                    value=_average_latency_label(
                        runs,
                        running_runs=running_runs,
                        now=now,
                    ),
                    delta="avg runtime",
                    tone="info",
                ),
                _observation_metric(observer_state),
            ),
            tabs=(
                OperationsTabModel(id="overview", label="Overview"),
                OperationsTabModel(id="runs", label="Runs", count=len(queued_runs)),
                OperationsTabModel(
                    id="execution_chains",
                    label="Execution",
                    count=execution_chains.total,
                ),
                OperationsTabModel(
                    id="repeated_probes",
                    label="Repeated Probes",
                    count=repeated_probes.total,
                    tone="warning" if repeated_probes.total else "neutral",
                ),
                OperationsTabModel(
                    id="lane_locks",
                    label="Lane Locks",
                    count=len([run for run in running_runs if run.lane_lock_key]),
                ),
                OperationsTabModel(
                    id="executors", label="Executors", count=len(leases)
                ),
                OperationsTabModel(
                    id="failures",
                    label="Failures",
                    count=len(failed_runs),
                    tone="danger" if recent_failed_runs else "neutral",
                ),
                OperationsTabModel(id="events", label="Events"),
            ),
            active_tab="overview",
            actions=actions,
            scheduler_status=_scheduler_status_section(
                runs=runs,
                queued_runs=queued_runs,
                continuation_tasks=continuation_tasks,
                dispatch_tasks=dispatch_tasks,
                event_records=operations_event_records,
                completed_count=completed_count,
                failed_count=len(failed_runs),
                cancelled_count=len(cancelled_runs),
                available_executor_slots=available,
                observer_state=observer_state,
                now=now,
            ),
            backpressure=_backpressure_section(
                queued_runs=queued_runs,
                waiting_runs=waiting_runs,
                active_lane_keys=_active_lane_keys(running_runs, waiting_runs),
                available_executor_slots=available,
            ),
            stuck_runs=_stuck_runs_section(
                queued_runs=queued_runs,
                running_runs=running_runs,
                waiting_runs=waiting_runs,
                now=now,
            ),
            policy_limits=_policy_limits_section(
                leases=leases,
                online_leases=online_leases,
                capacity=capacity,
                inflight=inflight,
                available=available,
                runtime_bootstrap_config=self.runtime_bootstrap_config,
                worker_lease_seconds=self.worker_lease_seconds,
                worker_heartbeat_seconds=self.worker_heartbeat_seconds,
            ),
            run_queue=_run_queue_section(
                queued_runs,
                dispatch_task_by_run_id=step_dispatch_by_run_id,
                now=now,
            ),
            execution_chains=execution_chains,
            repeated_probes=repeated_probes,
            lane_locks=_lane_locks_section(running_runs, leases=leases, now=now),
            executor_overview=_executor_section(
                leases,
                runs=runs,
                running_runs=running_runs,
                now=now,
            ),
            ingress_queue=_ingress_queue_section(
                pending_ingress_requests,
                fallback_runs=[],
                run_by_id={run.id: run for run in runs},
                dispatch_task_by_request_id=ingress_dispatch_by_request_id,
                now=now,
            ),
            recent_failures=_recent_failures_section(failed_runs),
            ops_event_log=_ops_event_log_section(
                event_records=operations_event_records,
            ),
        )


def _health(
    *,
    queued_runs: list[OrchestrationRun],
    running_runs: list[OrchestrationRun],
    waiting_runs: list[OrchestrationRun],
    failed_runs: list[OrchestrationRun],
    available_executor_slots: int,
) -> str:
    if failed_runs:
        return "warning"
    if queued_runs and available_executor_slots <= 0:
        return "warning"
    if running_runs or queued_runs or waiting_runs:
        return "healthy"
    return "healthy"


def _health_label(health: str) -> str:
    return {
        "healthy": "Healthy",
        "warning": "Warning",
        "error": "Error",
    }.get(health, "Unknown")


def _health_delta(health: str) -> str:
    return {
        "healthy": "All systems operational",
        "warning": "Operator attention recommended",
        "error": "Operator action required",
    }.get(health, "Insufficient data")


def _health_tone(health: str) -> str:
    return {
        "healthy": "success",
        "warning": "warning",
        "error": "danger",
    }.get(health, "neutral")


def _failed_metric(
    *,
    failed_runs: list[OrchestrationRun],
    recent_failed_runs: list[OrchestrationRun],
    cancelled_runs: list[OrchestrationRun],
) -> MetricCardModel:
    retained_label = f"{len(failed_runs)} retained"
    if cancelled_runs:
        retained_label = f"{retained_label} / {len(cancelled_runs)} cancelled"
    return MetricCardModel(
        id="failed",
        label="Recent Failed",
        value=str(len(recent_failed_runs)),
        delta=retained_label,
        tone="danger" if recent_failed_runs else "neutral" if failed_runs else "success",
    )


def _ingress_rate_label(
    ingress_requests: list[OrchestrationIngressRequest],
    *,
    fallback_runs: list[OrchestrationRun],
    now: datetime,
) -> str:
    recent_count = len(
        [
            request
            for request in ingress_requests
            if _age_seconds(request.created_at, now=now) <= 60
        ],
    ) + len(
        [
            run
            for run in fallback_runs
            if _age_seconds(run.created_at, now=now) <= 60
        ],
    )
    if recent_count == 0:
        return "0/s"
    rate = recent_count / 60
    return f"{rate:.1f}/s" if rate < 1 else f"{round(rate)}/s"


def _average_latency_label(
    runs: list[OrchestrationRun],
    *,
    running_runs: list[OrchestrationRun],
    now: datetime,
) -> str:
    terminal_latencies = [
        max(
            int(
                (
                    coerce_utc_datetime(run.completed_at)
                    - coerce_utc_datetime(run.started_at or run.created_at)
                ).total_seconds(),
            ),
            0,
        )
        for run in runs
        if run.completed_at is not None
        and _age_seconds(run.completed_at, now=now) <= 86_400
    ]
    if terminal_latencies:
        return _duration_label(round(sum(terminal_latencies) / len(terminal_latencies)))

    running_latencies = [
        _age_seconds(run.started_at or run.created_at, now=now)
        for run in running_runs
    ]
    if running_latencies:
        return _duration_label(round(sum(running_latencies) / len(running_latencies)))
    return "0s"


def _run_type_label(run: OrchestrationRun) -> str:
    if run.stage in {
        OrchestrationRunStage.TOOL,
        OrchestrationRunStage.WAITING_ON_TOOL,
    }:
        return "tool.call"
    return "agent.run"


def _run_progress_label(run: OrchestrationRun) -> str:
    if run.status is OrchestrationRunStatus.COMPLETED:
        return "100%"
    if run.max_steps <= 0:
        return "-"
    return f"{min(round((run.current_step / run.max_steps) * 100), 99)}%"


def _executor_capabilities_label(lease: OrchestrationExecutorLease) -> str:
    metadata = lease.metadata if isinstance(lease.metadata, dict) else {}
    explicit = _metadata_string_list(metadata.get("capabilities"))
    if explicit:
        return ", ".join(explicit[:4])

    runtime_registry = metadata.get("runtime_registry")
    if isinstance(runtime_registry, dict):
        registry_capabilities = _metadata_string_list(
            runtime_registry.get("capabilities"),
        )
        if registry_capabilities:
            return ", ".join(registry_capabilities[:4])
        tool_names = _metadata_string_list(runtime_registry.get("tool_names"))
        if tool_names:
            return ", ".join(tool_names[:4])

    runtime_state = metadata.get("runtime_state")
    if isinstance(runtime_state, dict):
        active = runtime_state.get("max_concurrent_assignments")
        if active is not None:
            return f"slots:{active}"

    service_set = metadata.get("service_set")
    if isinstance(service_set, str) and service_set.strip():
        return service_set.strip()
    return f"slots:{lease.max_inflight_assignments}"


def _metadata_string_list(value: object | None) -> list[str]:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, (list, tuple, set)):
        return [text for item in value for text in (_optional_str(item),) if text]
    return []


def _queue_rows(
    runs: list[OrchestrationRun],
    *,
    dispatch_task_by_run_id: dict[str, DispatchTask],
    now: datetime,
) -> tuple[dict[str, str], ...]:
    sorted_runs = sorted(
        runs,
        key=lambda run: (run.priority, run.queued_at or run.created_at),
    )
    rows: list[dict[str, str]] = []
    for run in sorted_runs[:20]:
        dispatch_task = dispatch_task_by_run_id.get(run.id)
        queued_at = _dispatch_queued_at(dispatch_task) or run.queued_at or run.created_at
        rows.append(
            {
                "Priority": f"P{_dispatch_priority_label(dispatch_task, run.priority)}",
                "Run ID": run.id,
                "Lane Key": (
                    dispatch_task.lane_key
                    if dispatch_task is not None and dispatch_task.lane_key
                    else run.lane_key or "-"
                ),
                "Wait Reason": (
                    _dispatch_wait_reason(dispatch_task) or run.waiting_reason or "-"
                ),
                "Dispatch": (
                    dispatch_task.status.value if dispatch_task is not None else "-"
                ),
                "Wait Time": _age_label(queued_at, now=now),
            },
        )
    return tuple(rows)


def _lane_lock_rows(
    runs: list[OrchestrationRun],
    *,
    now: datetime,
) -> tuple[dict[str, str], ...]:
    lock_runs = [run for run in runs if run.lane_lock_key]
    return tuple(
        {
            "Lane Key": run.lane_lock_key or run.lane_key or "-",
            "Holder Run ID": run.id,
            "TTL": "-",
            "Expires At": "-",
            "Reason": f"active {run.stage.value}",
        }
        for run in sorted(lock_runs, key=lambda item: item.updated_at, reverse=True)[
            :20
        ]
    )


def _executor_rows(
    leases: list[OrchestrationExecutorLease],
    *,
    running_runs: list[OrchestrationRun],
    now: datetime,
) -> tuple[dict[str, str], ...]:
    current_run_by_worker = {
        run.worker_id: run.id
        for run in running_runs
        if run.worker_id is not None and run.worker_id.strip()
    }
    rows = []
    for lease in sorted(leases, key=lambda item: item.worker_id):
        capacity = max(lease.max_inflight_assignments, 1)
        load = round((lease.inflight_assignment_count / capacity) * 100)
        rows.append(
            {
                "Worker ID": lease.worker_id,
                "Status": lease.effective_status(now=now).value,
                "Last Heartbeat": format_datetime_utc(lease.last_heartbeat_at),
                "Current Run": current_run_by_worker.get(lease.worker_id, "-"),
                "Load": f"{load}%",
                "Running": str(lease.inflight_assignment_count),
                "Capacity": str(lease.max_inflight_assignments),
                "Capabilities": _executor_capabilities_label(lease),
                "Actions": "Open",
            },
        )
    return tuple(rows[:20])


def _scheduler_status_section(
    *,
    runs: list[OrchestrationRun],
    queued_runs: list[OrchestrationRun],
    continuation_tasks: list[OrchestrationContinuationTask],
    dispatch_tasks: list[DispatchTask],
    event_records: tuple[Any, ...],
    completed_count: int,
    failed_count: int,
    cancelled_count: int,
    available_executor_slots: int,
    observer_state: Any | None,
    now: datetime,
) -> OperationsKeyValueSectionModel:
    recent_terminal_runs = [
        run
        for run in runs
        if run.status
        in {
            OrchestrationRunStatus.COMPLETED,
            OrchestrationRunStatus.FAILED,
            OrchestrationRunStatus.CANCELLED,
        }
        and _age_seconds(run.completed_at or run.updated_at, now=now) <= 300
    ]
    recent_completed_count = len(
        [
            run
            for run in recent_terminal_runs
            if run.status is OrchestrationRunStatus.COMPLETED
        ],
    )
    latest_update = _latest_event_time(event_records) or _latest_datetime(
        (
            *[run.updated_at for run in runs],
            *[task.updated_at for task in continuation_tasks],
        ),
    )
    queued_continuation_count = len(
        [
            task
            for task in continuation_tasks
            if task.status is OrchestrationContinuationStatus.QUEUED
        ],
    )
    processing_continuation_count = len(
        [
            task
            for task in continuation_tasks
            if task.status is OrchestrationContinuationStatus.PROCESSING
        ],
    )
    event_loop_value = "Observed" if latest_update else "No events"
    event_loop_tone = "success" if latest_update else "warning"
    if latest_update and _age_seconds(latest_update, now=now) > 120:
        event_loop_value = "Stale"
        event_loop_tone = "warning"
    return OperationsKeyValueSectionModel(
        id="scheduler_status",
        title="Scheduler Status",
        items=(
            OperationsKeyValueItemModel(
                label="Event Loop",
                value=event_loop_value,
                tone=event_loop_tone,
            ),
            OperationsKeyValueItemModel(
                label="Last Tick",
                value=format_datetime_utc(latest_update) if latest_update else "-",
            ),
            OperationsKeyValueItemModel(
                label="Tick Lag",
                value=_age_label(latest_update, now=now) if latest_update else "-",
            ),
            OperationsKeyValueItemModel(
                label="Dispatch Latency",
                value=_continuation_latency_label(continuation_tasks),
            ),
            OperationsKeyValueItemModel(
                label="Queue Age (p95)",
                value=_queue_wait_p95(queued_runs, now=now),
                tone="warning" if queued_runs else "success",
            ),
            OperationsKeyValueItemModel(
                label="Throughput (5m)",
                value=f"{len(recent_terminal_runs)} runs",
            ),
            OperationsKeyValueItemModel(
                label="Schedule Success Rate (5m)",
                value=_percent_label(recent_completed_count, len(recent_terminal_runs)),
                tone=(
                    "success"
                    if recent_terminal_runs
                    and recent_completed_count == len(recent_terminal_runs)
                    else "warning"
                    if recent_terminal_runs
                    else "neutral"
                ),
            ),
            OperationsKeyValueItemModel(
                label="Continuation Tasks",
                value=(
                    f"{queued_continuation_count} queued / "
                    f"{processing_continuation_count} processing"
                ),
                tone="warning"
                if queued_continuation_count or processing_continuation_count
                else "success",
            ),
            OperationsKeyValueItemModel(
                label="Dispatch Tasks",
                value=_dispatch_task_breakdown(dispatch_tasks),
                tone="warning" if _active_dispatch_tasks(dispatch_tasks) else "success",
            ),
            OperationsKeyValueItemModel(
                label="Observed Cursor",
                value=_observation_cursor_label(observer_state),
                tone="success" if observer_state is not None else "warning",
            ),
            OperationsKeyValueItemModel(
                label="Observed Entities",
                value=_observation_events_label(observer_state),
                tone="info" if observer_state is not None else "neutral",
            ),
        ),
    )


def _backpressure_section(
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


def _stuck_runs_section(
    *,
    queued_runs: list[OrchestrationRun],
    running_runs: list[OrchestrationRun],
    waiting_runs: list[OrchestrationRun],
    now: datetime,
) -> OperationsTableSectionModel:
    queued_stuck = [
        run
        for run in queued_runs
        if _age_seconds(run.queued_at or run.created_at, now=now) >= 300
    ]
    running_stale = [
        run for run in running_runs if _age_seconds(run.updated_at, now=now) >= 600
    ]
    waiting_approval = [
        run
        for run in waiting_runs
        if run.stage is OrchestrationRunStage.WAITING_FOR_CONFIRMATION
    ]
    waiting_tools = [
        run
        for run in waiting_runs
        if run.stage is OrchestrationRunStage.WAITING_ON_TOOL
        or bool(run.pending_tool_run_ids)
    ]
    buckets = (
        (
            "queued_over_5m",
            "Queued > 5m",
            queued_stuck,
            "Inspect queue policy",
            "warning",
            tuple(run.queued_at or run.created_at for run in queued_stuck),
        ),
        (
            "running_stale",
            "Running stale > 10m",
            running_stale,
            "Open trace",
            "danger",
            tuple(run.updated_at for run in running_stale),
        ),
        (
            "waiting_approval",
            "Waiting approval",
            waiting_approval,
            "Resolve approval",
            "warning",
            tuple(run.updated_at for run in waiting_approval),
        ),
        (
            "waiting_tools",
            "Waiting tool",
            waiting_tools,
            "Inspect tool run",
            "info",
            tuple(run.updated_at for run in waiting_tools),
        ),
    )
    rows = []
    for row_id, issue, bucket_runs, action, tone, timestamps in buckets:
        if not bucket_runs:
            continue
        first_run = sorted(bucket_runs, key=lambda run: run.updated_at, reverse=True)[0]
        approval = first_run.pending_approval_request()
        rows.append(
            OperationsTableRowModel(
                id=row_id,
                cells={
                    "issue": issue,
                    "count": str(len(bucket_runs)),
                    "oldest": _max_age_label(timestamps, now=now),
                    "action": "View",
                    "recommended_action": action,
                    "example_run_id": first_run.id,
                    "approval_request_id": (
                        approval.request_id if approval is not None else "-"
                    ),
                    "approval_effect_id": (
                        approval.effect_id if approval is not None else "-"
                    ),
                    "approval_label": approval.label if approval is not None else "-",
                    "route": _workbench_route(first_run),
                },
                status=row_id,
                tone=tone,
            ),
        )
    return OperationsTableSectionModel(
        id="stuck_runs",
        title="Stuck Runs",
        columns=_columns(
            ("issue", "Issue"),
            ("count", "Count"),
            ("action", "Action"),
        ),
        rows=tuple(rows),
        total=len(rows),
        empty_state="No stuck runs detected.",
    )


def _policy_limits_section(
    *,
    leases: list[OrchestrationExecutorLease],
    online_leases: list[OrchestrationExecutorLease],
    capacity: int,
    inflight: int,
    available: int,
    runtime_bootstrap_config: Any | None,
    worker_lease_seconds: int | None,
    worker_heartbeat_seconds: float | None,
) -> OperationsKeyValueSectionModel:
    lease_seconds = _runtime_int(
        runtime_bootstrap_config,
        "orchestration_run_lease_seconds",
        fallback=worker_lease_seconds,
    )
    heartbeat_seconds = _runtime_float(
        runtime_bootstrap_config,
        "orchestration_run_heartbeat_seconds",
        fallback=worker_heartbeat_seconds,
    )
    executor_limit = _runtime_int(
        runtime_bootstrap_config,
        "orchestration_executor_max_concurrent_assignments",
    )
    compaction_enabled = _runtime_bool(
        runtime_bootstrap_config,
        "orchestration_auto_compaction_enabled",
    )
    compaction_reserve = _runtime_int(
        runtime_bootstrap_config,
        "orchestration_auto_compaction_reserve_tokens",
    )
    compaction_soft = _runtime_int(
        runtime_bootstrap_config,
        "orchestration_auto_compaction_soft_threshold_tokens",
    )
    return OperationsKeyValueSectionModel(
        id="policy_limits",
        title="Policy & Limits",
        items=(
            OperationsKeyValueItemModel(label="Per-lane Concurrency", value="1"),
            OperationsKeyValueItemModel(
                label="Global Run Concurrency",
                value=str(max(capacity, inflight)),
            ),
            OperationsKeyValueItemModel(
                label="Executor Max Assignments",
                value=str(executor_limit) if executor_limit is not None else "-",
            ),
            OperationsKeyValueItemModel(
                label="Worker Capacity (Online / Total)",
                value=f"{len(online_leases)}/{len(leases)}",
                tone="success" if online_leases else "warning",
            ),
            OperationsKeyValueItemModel(
                label="Approval Timeout", value="not configured"
            ),
            OperationsKeyValueItemModel(
                label="Lease Timeout",
                value=_duration_label(round(lease_seconds))
                if lease_seconds is not None
                else "-",
            ),
            OperationsKeyValueItemModel(
                label="Lane Lock TTL",
                value="executor lease",
            ),
            OperationsKeyValueItemModel(
                label="Queue Retention",
                value="retained",
            ),
            OperationsKeyValueItemModel(
                label="Heartbeat Interval",
                value=_duration_label(round(heartbeat_seconds))
                if heartbeat_seconds is not None
                else "-",
            ),
            OperationsKeyValueItemModel(
                label="Auto Compaction",
                value=_enabled_label(compaction_enabled),
                tone="success" if compaction_enabled else "neutral",
            ),
            OperationsKeyValueItemModel(
                label="Compaction Reserve / Soft",
                value=_token_pair_label(compaction_reserve, compaction_soft),
            ),
        ),
    )


def _runtime_int(
    runtime_bootstrap_config: Any | None,
    name: str,
    *,
    fallback: int | float | None = None,
) -> int | None:
    value = getattr(runtime_bootstrap_config, name, fallback)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _runtime_float(
    runtime_bootstrap_config: Any | None,
    name: str,
    *,
    fallback: int | float | None = None,
) -> float | None:
    value = getattr(runtime_bootstrap_config, name, fallback)
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _runtime_bool(runtime_bootstrap_config: Any | None, name: str) -> bool | None:
    value = getattr(runtime_bootstrap_config, name, None)
    if value is None:
        return None
    return bool(value)


def _enabled_label(value: bool | None) -> str:
    if value is None:
        return "-"
    return "enabled" if value else "disabled"


def _token_pair_label(reserve_tokens: int | None, soft_threshold_tokens: int | None) -> str:
    if reserve_tokens is None and soft_threshold_tokens is None:
        return "-"
    reserve = f"{reserve_tokens:,}" if reserve_tokens is not None else "-"
    soft = f"{soft_threshold_tokens:,}" if soft_threshold_tokens is not None else "-"
    return f"{reserve} / {soft} tokens"


def _run_queue_section(
    runs: list[OrchestrationRun],
    *,
    dispatch_task_by_run_id: dict[str, DispatchTask],
    now: datetime,
) -> OperationsTableSectionModel:
    sorted_runs = sorted(
        runs,
        key=lambda run: (run.priority, run.queued_at or run.created_at),
    )
    rows = tuple(
        _run_queue_row(
            run,
            dispatch_task=dispatch_task_by_run_id.get(run.id),
            now=now,
        )
        for run in sorted_runs[:50]
    )
    return OperationsTableSectionModel(
        id="run_queue",
        title="Run Queue",
        columns=_columns(
            ("priority", "Priority"),
            ("run_id", "Run ID"),
            ("lane_key", "Lane Key"),
            ("enqueued_at", "Enqueued At"),
            ("agent_target", "Agent (Target)"),
            ("wait_reason", "Wait Reason"),
            ("dispatch_status", "Dispatch"),
            ("wait_time", "Wait Time"),
            ("actions", "Actions"),
        ),
        rows=rows,
        total=len(runs),
        view_all_route="/operations/orchestration?tab=runs",
        empty_state="Run queue is empty.",
    )


def _run_queue_row(
    run: OrchestrationRun,
    *,
    dispatch_task: DispatchTask | None,
    now: datetime,
) -> OperationsTableRowModel:
    queued_at = _dispatch_queued_at(dispatch_task) or run.queued_at or run.created_at
    status = dispatch_task.status.value if dispatch_task is not None else run.status.value
    return OperationsTableRowModel(
        id=run.id,
        cells={
            "priority": f"P{_dispatch_priority_label(dispatch_task, run.priority)}",
            "run_id": run.id,
            "lane_key": _display(
                dispatch_task.lane_key if dispatch_task is not None else run.lane_key,
            ),
            "enqueued_at": format_datetime_utc(queued_at),
            "agent_target": _display(run.agent_id),
            "wait_reason": _dispatch_wait_reason(dispatch_task) or _run_wait_reason(run),
            "wait_time": _age_label(queued_at, now=now),
            "dispatch_status": status,
            "dispatch_task_id": dispatch_task.id if dispatch_task is not None else "-",
            "dispatch_owner_kind": (
                dispatch_task.owner_kind if dispatch_task is not None else "-"
            ),
            "dispatch_worker": _dispatch_worker(dispatch_task),
            "dispatch_lease_expires_at": _dispatch_lease_expires_at(dispatch_task),
            "actions": "Open / Trace / Cancel / Requeue",
            "policy": (
                dispatch_task.policy.value if dispatch_task is not None else run.queue_policy.value
            ),
            "stage": run.stage.value,
            "trace": _trace_id(run),
            "route": _workbench_route(run),
            "trace_route": _trace_route(run),
        },
        status=status,
        tone=_tone_for_dispatch_or_run_status(dispatch_task, run.status),
    )


def _repeated_probe_section(
    runs: list[OrchestrationRun],
) -> OperationsTableSectionModel:
    rows: list[OperationsTableRowModel] = []
    for run in runs:
        observation = run.metadata.get("repeated_probe_observation")
        if not isinstance(observation, dict):
            continue
        repeated = observation.get("repeated")
        if not isinstance(repeated, list):
            continue
        for index, item in enumerate(repeated[:5]):
            if not isinstance(item, dict):
                continue
            count = _int(item.get("count"), 0)
            if count < 3:
                continue
            target = _probe_target_label(item)
            rows.append(
                OperationsTableRowModel(
                    id=f"{run.id}:{index}:{target}",
                    cells={
                        "run_id": run.id,
                        "tool_id": _display(item.get("tool_id")),
                        "kind": _display(item.get("kind")),
                        "target": target,
                        "count": str(count),
                        "first_seen_step": _display(item.get("first_seen_step")),
                        "last_seen_step": _display(item.get("last_seen_step")),
                        "trace": _trace_id(run),
                        "route": _workbench_route(run),
                        "trace_route": _trace_route(run),
                    },
                    status="repeated_probe",
                    tone="warning",
                ),
            )
    rows.sort(
        key=lambda row: (
            -_int(row.cells.get("count"), 0),
            row.cells.get("run_id", ""),
            row.cells.get("target", ""),
        ),
    )
    return OperationsTableSectionModel(
        id="repeated_probes",
        title="Repeated Probes",
        columns=_columns(
            ("run_id", "Run ID"),
            ("tool_id", "Tool"),
            ("kind", "Kind"),
            ("target", "Target"),
            ("count", "Count"),
            ("last_seen_step", "Last Seen"),
        ),
        rows=tuple(rows[:50]),
        total=len(rows),
        view_all_route="/operations/orchestration?tab=repeated_probes",
        empty_state="No repeated probes detected.",
    )


def _probe_target_label(item: dict[str, Any]) -> str:
    normalized_url = _optional_metadata_text(item.get("normalized_url"))
    if normalized_url is not None:
        return _truncate(normalized_url, limit=120)
    command_fingerprint = _optional_metadata_text(item.get("command_fingerprint"))
    if command_fingerprint is not None:
        return f"command:{command_fingerprint}"
    argument_fingerprint = _optional_metadata_text(item.get("argument_fingerprint"))
    if argument_fingerprint is not None:
        return f"args:{argument_fingerprint}"
    key = _optional_metadata_text(item.get("key"))
    return _truncate(key or "-", limit=120)


def _execution_chain_section(
    run_query: OrchestrationRunQueryPort,
    runs: list[OrchestrationRun],
    *,
    dispatch_task_by_run_id: dict[str, DispatchTask],
    now: datetime,
) -> OperationsTableSectionModel:
    rows: list[OperationsTableRowModel] = []
    total_chains = 0
    for run in _execution_chain_candidate_runs(runs, now=now):
        chains = _safe_execution_chains(run_query, run.id)
        if not chains:
            continue
        total_chains += len(chains)
        for chain in sorted(chains, key=lambda item: item.updated_at, reverse=True)[:2]:
            rows.append(
                _execution_chain_row(
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
            ("dispatch_status", "Dispatch"),
            ("updated_at", "Updated At"),
            ("actions", "Actions"),
        ),
        rows=tuple(rows),
        total=total_chains,
        view_all_route="/operations/orchestration?tab=execution_chains",
        empty_state="No execution chains observed.",
    )


def _execution_chain_candidate_runs(
    runs: list[OrchestrationRun],
    *,
    now: datetime,
) -> list[OrchestrationRun]:
    selected: dict[str, OrchestrationRun] = {}
    active_statuses = {
        OrchestrationRunStatus.ACCEPTED,
        OrchestrationRunStatus.QUEUED,
        OrchestrationRunStatus.RUNNING,
        OrchestrationRunStatus.WAITING,
    }
    for run in sorted(runs, key=lambda item: item.updated_at, reverse=True):
        if run.status in active_statuses:
            selected[run.id] = run
    for run in sorted(runs, key=lambda item: item.updated_at, reverse=True):
        if len(selected) >= 30:
            break
        if run.id in selected:
            continue
        if _age_seconds(run.completed_at or run.updated_at, now=now) <= 900:
            selected[run.id] = run
    return list(selected.values())[:30]


def _execution_chain_row(
    run_query: OrchestrationRunQueryPort,
    run: OrchestrationRun,
    chain: ExecutionChain,
    *,
    dispatch_task: DispatchTask | None,
    now: datetime,
) -> OperationsTableRowModel:
    steps = _safe_execution_steps(run_query, chain.id)
    items = [
        item
        for step in steps
        for item in _safe_execution_step_items(run_query, step.id)
    ]
    active_step = _active_execution_step(chain, steps)
    last_step = max(steps, key=lambda item: item.step_index, default=None)
    active_item_count = len(
        [item for item in items if item.status in _ACTIVE_EXECUTION_ITEM_STATUSES],
    )
    dispatch_status = (
        dispatch_task.status.value if dispatch_task is not None else run.status.value
    )
    return OperationsTableRowModel(
        id=f"{run.id}:{chain.id}",
        cells={
            "run_id": run.id,
            "chain_id": chain.id,
            "chain_status": chain.status.value,
            "active_step": _execution_step_label(active_step),
            "last_step": _execution_step_label(last_step),
            "steps": f"{len(steps)}",
            "items": f"{len(items)} / {active_item_count} active",
            "dispatch_status": dispatch_status,
            "dispatch_task_id": dispatch_task.id if dispatch_task is not None else "-",
            "dispatch_worker": _dispatch_worker(dispatch_task),
            "updated_at": format_datetime_utc(chain.updated_at),
            "started_at": (
                format_datetime_utc(chain.started_at) if chain.started_at else "-"
            ),
            "completed_at": (
                format_datetime_utc(chain.completed_at) if chain.completed_at else "-"
            ),
            "age": _age_label(chain.updated_at, now=now),
            "step_breakdown": _execution_step_breakdown(steps),
            "item_breakdown": _execution_item_breakdown(items),
            "active_step_id": chain.active_step_id or "-",
            "stage": run.stage.value,
            "trace": _trace_id(run),
            "route": _workbench_route(run),
            "trace_route": _trace_route(run),
            "actions": "Open / Trace",
        },
        status=chain.status.value,
        tone=_tone_for_execution_chain_status(chain.status),
    )


_ACTIVE_EXECUTION_ITEM_STATUSES = frozenset(
    {
        ExecutionStepItemStatus.CREATED,
        ExecutionStepItemStatus.RUNNING,
        ExecutionStepItemStatus.WAITING,
    },
)


def _safe_execution_chains(
    run_query: OrchestrationRunQueryPort,
    run_id: str,
) -> list[ExecutionChain]:
    try:
        return run_query.list_execution_chains(run_id)
    except Exception:
        return []


def _safe_execution_steps(
    run_query: OrchestrationRunQueryPort,
    chain_id: str,
) -> list[ExecutionStep]:
    try:
        return run_query.list_execution_steps(chain_id)
    except Exception:
        return []


def _safe_execution_step_items(
    run_query: OrchestrationRunQueryPort,
    step_id: str,
) -> list[ExecutionStepItem]:
    try:
        return run_query.list_execution_step_items(step_id)
    except Exception:
        return []


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


def _execution_step_label(step: ExecutionStep | None) -> str:
    if step is None:
        return "-"
    return f"{step.step_index}:{step.kind.value}/{step.status.value}"


def _execution_step_breakdown(steps: list[ExecutionStep]) -> str:
    if not steps:
        return "-"
    return "; ".join(
        _execution_step_label(step)
        for step in sorted(steps, key=lambda item: item.step_index)[:12]
    )


def _execution_item_breakdown(items: list[ExecutionStepItem]) -> str:
    if not items:
        return "-"
    counts: Counter[str] = Counter(
        f"{item.kind.value}:{item.status.value}" for item in items
    )
    return " / ".join(
        f"{count} {key}" for key, count in sorted(counts.items())
    )


def _tone_for_execution_chain_status(status: ExecutionChainStatus) -> str:
    if status is ExecutionChainStatus.FAILED:
        return "danger"
    if status is ExecutionChainStatus.WAITING:
        return "warning"
    if status is ExecutionChainStatus.RUNNING:
        return "info"
    if status is ExecutionChainStatus.COMPLETED:
        return "success"
    return "neutral"


def _lane_locks_section(
    running_runs: list[OrchestrationRun],
    *,
    leases: list[OrchestrationExecutorLease],
    now: datetime,
) -> OperationsTableSectionModel:
    lock_runs = [run for run in running_runs if run.lane_lock_key]
    leases_by_worker = {lease.worker_id: lease for lease in leases}
    rows = tuple(
        OperationsTableRowModel(
            id=run.lane_lock_key or run.id,
            cells={
                "lane_key": run.lane_lock_key or run.lane_key or "-",
                "holder_run_id": run.id,
                "run_id": run.id,
                "type": _run_type_label(run),
                "worker_id": _display(run.worker_id),
                "duration": _age_label(run.started_at or run.updated_at, now=now),
                "status": run.status.value,
                "progress": _run_progress_label(run),
                "lock_epoch": str(run.current_step),
                "ttl": _lane_lock_ttl_label(
                    leases_by_worker.get(run.worker_id or ""),
                    now=now,
                ),
                "expires_at": _lane_lock_expires_label(
                    leases_by_worker.get(run.worker_id or ""),
                ),
                "renewed_at": format_datetime_utc(
                    _lane_lock_renewed_at(
                        run,
                        leases_by_worker.get(run.worker_id or ""),
                    ),
                ),
                "reason": f"active {run.stage.value}",
                "held_for": _age_label(run.started_at or run.updated_at, now=now),
                "stage": run.stage.value,
                "trace": _trace_id(run),
                "route": _workbench_route(run),
                "trace_route": _trace_route(run),
                "actions": "Open / Trace",
            },
            status=run.status.value,
            tone="info",
        )
        for run in sorted(lock_runs, key=lambda item: item.updated_at, reverse=True)[
            :50
        ]
    )
    return OperationsTableSectionModel(
        id="lane_locks",
        title="Lane Locks",
        columns=_columns(
            ("lane_key", "Lane Key"),
            ("holder_run_id", "Holder Run ID"),
            ("type", "Type"),
            ("worker_id", "Worker ID"),
            ("duration", "Duration"),
            ("status", "Status"),
            ("progress", "Progress"),
            ("lock_epoch", "Lock Epoch"),
            ("ttl", "TTL"),
            ("expires_at", "Expires At"),
            ("renewed_at", "Renewed At"),
            ("reason", "Reason"),
            ("actions", "Actions"),
        ),
        rows=rows,
        total=len(lock_runs),
        view_all_route="/operations/orchestration?tab=lane_locks",
        empty_state="No active lane locks.",
    )


def _executor_section(
    leases: list[OrchestrationExecutorLease],
    *,
    runs: list[OrchestrationRun],
    running_runs: list[OrchestrationRun],
    now: datetime,
) -> OperationsTableSectionModel:
    current_run_by_worker = {
        run.worker_id: run.id
        for run in running_runs
        if run.worker_id is not None and run.worker_id.strip()
    }
    runs_5m_by_worker: Counter[str] = Counter()
    for run in runs:
        if run.worker_id is None or not run.worker_id.strip():
            continue
        if run.status not in {
            OrchestrationRunStatus.COMPLETED,
            OrchestrationRunStatus.FAILED,
            OrchestrationRunStatus.CANCELLED,
        }:
            continue
        if _age_seconds(run.completed_at or run.updated_at, now=now) <= 300:
            runs_5m_by_worker[run.worker_id] += 1
    rows = []
    for lease in sorted(leases, key=lambda item: item.worker_id):
        capacity = max(lease.max_inflight_assignments, 1)
        load = round((lease.inflight_assignment_count / capacity) * 100)
        status = lease.effective_status(now=now).value
        rows.append(
            OperationsTableRowModel(
                id=lease.worker_id,
                cells={
                    "worker_id": lease.worker_id,
                    "status": status,
                    "last_heartbeat": format_datetime_utc(lease.last_heartbeat_at),
                    "lease_expires_at": (
                        format_datetime_utc(lease.lease_expires_at)
                        if lease.lease_expires_at
                        else "-"
                    ),
                    "current_run": current_run_by_worker.get(lease.worker_id, "-"),
                    "load": f"{load}%",
                    "running": str(lease.inflight_assignment_count),
                    "capacity": str(lease.max_inflight_assignments),
                    "available_slots": str(lease.available_assignment_slots(now=now)),
                    "capabilities": _executor_capabilities_label(lease),
                    "runs_5m": str(runs_5m_by_worker[lease.worker_id]),
                    "actions": "Open",
                },
                status=status,
                tone=_tone_for_executor_status(status),
            ),
        )
    return OperationsTableSectionModel(
        id="executor_overview",
        title="Executor Overview",
        columns=_columns(
            ("worker_id", "Worker ID"),
            ("status", "Status"),
            ("last_heartbeat", "Last Heartbeat"),
            ("lease_expires_at", "Lease (Expires At)"),
            ("current_run", "Current Run"),
            ("load", "Load (1m)"),
            ("running", "Running"),
            ("capacity", "Capacity"),
            ("capabilities", "Capabilities"),
            ("runs_5m", "Runs (5m)"),
            ("actions", "Actions"),
        ),
        rows=tuple(rows[:50]),
        total=len(leases),
        view_all_route="/operations/orchestration?tab=executors",
        empty_state="No executor leases registered.",
    )


def _ingress_queue_section(
    requests: list[OrchestrationIngressRequest],
    *,
    fallback_runs: list[OrchestrationRun],
    run_by_id: dict[str, OrchestrationRun],
    dispatch_task_by_request_id: dict[str, DispatchTask],
    now: datetime,
) -> OperationsTableSectionModel:
    fallback_rows = tuple(
        OperationsTableRowModel(
            id=run.id,
            cells={
                "source": run.inbound_instruction.source,
                "intake_key": run.id,
                "received_at": format_datetime_utc(run.created_at),
                "target_lane": _display(run.lane_key),
                "priority": f"P{run.priority}",
                "age": _age_label(run.created_at, now=now),
                "actions": "Open",
                "status": run.status.value,
                "run_id": run.id,
                "session_key": _display(run.session_key),
                "summary": _run_summary(run),
                "trace": _trace_id(run),
                "route": _workbench_route(run),
                "trace_route": _trace_route(run),
            },
            status=run.status.value,
            tone=_tone_for_run_status(run.status),
        )
        for run in sorted(fallback_runs, key=lambda item: item.created_at)[:50]
    )
    if requests:
        request_rows = tuple(
            _ingress_request_row(
                request,
                run_by_id=run_by_id,
                dispatch_task=dispatch_task_by_request_id.get(request.id),
                now=now,
            )
            for request in sorted(requests, key=lambda item: item.created_at)[:50]
        )
        rows = request_rows + fallback_rows[: max(0, 50 - len(request_rows))]
        total = len(requests) + len(fallback_runs)
    else:
        rows = fallback_rows
        total = len(fallback_runs)
    return OperationsTableSectionModel(
        id="ingress_queue",
        title="Ingress Queue",
        columns=_columns(
            ("source", "Source"),
            ("intake_key", "Intake Key"),
            ("received_at", "Received At"),
            ("target_lane", "Target Lane"),
            ("priority", "Priority"),
            ("status", "Status"),
            ("dispatch_worker", "Worker"),
            ("age", "Age"),
            ("actions", "Actions"),
        ),
        rows=rows,
        total=total,
        empty_state="Ingress queue is empty.",
    )


def _recent_failures_section(
    runs: list[OrchestrationRun],
) -> OperationsTableSectionModel:
    rows = tuple(
        OperationsTableRowModel(
            id=run.id,
            cells={
                "time": format_datetime_utc(run.completed_at or run.updated_at),
                "run_id": run.id,
                "error": _run_error_code(run),
                "status": run.status.value,
                "module": "Orchestration",
                "details": _run_error_message(run),
                "trace": _trace_id(run),
                "route": _workbench_route(run),
                "trace_route": _trace_route(run),
                "actions": "Open / Trace / Requeue",
            },
            status=run.status.value,
            tone="danger",
        )
        for run in sorted(runs, key=lambda item: item.updated_at, reverse=True)[:20]
    )
    return OperationsTableSectionModel(
        id="recent_failures",
        title="Recent Failures",
        columns=_columns(
            ("time", "Time"),
            ("run_id", "Run ID"),
            ("error", "Error"),
            ("status", "Status"),
            ("module", "Module"),
            ("details", "Details"),
            ("trace", "Trace"),
            ("actions", "Actions"),
        ),
        rows=rows,
        total=len(runs),
        view_all_route="/operations/orchestration?tab=failures",
        empty_state="No failed runs retained.",
    )


def _ops_event_log_section(
    *,
    event_records: tuple[Any, ...],
) -> OperationsTableSectionModel:
    rows = tuple(_event_record_row(record) for record in event_records[:30])
    return OperationsTableSectionModel(
        id="ops_event_log",
        title="Ops Event Log",
        columns=_columns(
            ("time", "Time"),
            ("level", "Level"),
            ("event", "Event"),
            ("summary", "Summary"),
            ("run_id_entity", "Run ID / Entity"),
            ("source", "Source"),
        ),
        rows=rows,
        total=len(event_records),
        view_all_route="/operations/orchestration?tab=events",
        empty_state="No orchestration events observed yet.",
    )


def _columns(*items: tuple[str, str]) -> tuple[OperationsTableColumnModel, ...]:
    return tuple(
        OperationsTableColumnModel(key=key, label=label) for key, label in items
    )


def _list_ingress_requests(
    query: OrchestrationIngressRequestQueryPort | None,
) -> list[OrchestrationIngressRequest]:
    if query is None:
        return []
    return query.list_ingress_requests(status=None)


def _list_continuation_tasks(
    query: OrchestrationContinuationQueryPort | None,
) -> list[OrchestrationContinuationTask]:
    if query is None:
        return []
    return query.list_continuation_tasks(status=None)


def _list_dispatch_tasks(
    query: OrchestrationDispatchTaskQueryPort | None,
) -> list[DispatchTask]:
    if query is None:
        return []
    return query.list_dispatch_tasks(status=None)


def _dispatch_tasks_by_owner(
    tasks: list[DispatchTask],
    *,
    owner_kind: str,
) -> dict[str, DispatchTask]:
    result: dict[str, DispatchTask] = {}
    for task in tasks:
        if task.owner_kind != owner_kind:
            continue
        previous = result.get(task.owner_id)
        if previous is None or task.updated_at > previous.updated_at:
            result[task.owner_id] = task
    return result


def _dispatch_tasks_by_payload_ref(
    tasks: list[DispatchTask],
    *,
    owner_kind: str,
) -> dict[str, DispatchTask]:
    result: dict[str, DispatchTask] = {}
    for task in tasks:
        if task.owner_kind != owner_kind:
            continue
        if task.payload_ref is None or not task.payload_ref.strip():
            continue
        payload_ref = task.payload_ref.strip()
        previous = result.get(payload_ref)
        if previous is None or task.updated_at > previous.updated_at:
            result[payload_ref] = task
    return result


def _active_dispatch_tasks(tasks: list[DispatchTask]) -> list[DispatchTask]:
    return [task for task in tasks if _is_active_dispatch_status(task.status)]


def _is_active_dispatch_status(status: DispatchTaskStatus) -> bool:
    return status in {
        DispatchTaskStatus.QUEUED,
        DispatchTaskStatus.CLAIMED,
        DispatchTaskStatus.WAITING,
    }


def _dispatch_task_breakdown(tasks: list[DispatchTask]) -> str:
    active_tasks = _active_dispatch_tasks(tasks)
    if not active_tasks:
        return "0 active"
    by_kind: Counter[str] = Counter(task.owner_kind for task in active_tasks)
    return " / ".join(
        f"{count} {owner_kind}"
        for owner_kind, count in sorted(by_kind.items(), key=lambda item: item[0])
    )


def _run_is_dispatch_queued(
    run: OrchestrationRun,
    dispatch_task: DispatchTask | None,
) -> bool:
    if dispatch_task is not None:
        return dispatch_task.status in {
            DispatchTaskStatus.QUEUED,
            DispatchTaskStatus.WAITING,
        }
    return run.status is OrchestrationRunStatus.QUEUED


def _recent_failed_runs(
    failed_runs: list[OrchestrationRun],
    *,
    now: datetime,
) -> list[OrchestrationRun]:
    return [
        run
        for run in failed_runs
        if _age_seconds(run.completed_at or run.updated_at, now=now)
        <= _RECENT_FAILURE_HEALTH_SECONDS
    ]


def _pending_ingress_requests(
    requests: list[OrchestrationIngressRequest],
    *,
    dispatch_task_by_request_id: dict[str, DispatchTask] | None = None,
) -> list[OrchestrationIngressRequest]:
    dispatch_task_by_request_id = dispatch_task_by_request_id or {}
    result: list[OrchestrationIngressRequest] = []
    for request in requests:
        dispatch_task = dispatch_task_by_request_id.get(request.id)
        if dispatch_task is not None:
            if _is_active_dispatch_status(dispatch_task.status):
                result.append(request)
            continue
        if request.status in {
            OrchestrationIngressStatus.QUEUED,
            OrchestrationIngressStatus.PROCESSING,
        }:
            result.append(request)
    return result


def _active_lane_keys(
    running_runs: list[OrchestrationRun],
    waiting_runs: list[OrchestrationRun],
) -> set[str]:
    return {
        run.lane_lock_key
        for run in [*running_runs, *waiting_runs]
        if run.lane_lock_key is not None
    }


def _recent_operations_events(
    *,
    observation: OperationsObservationReadPort | None,
    module: str,
    limit: int,
) -> tuple[OperationsObservedEvent, ...]:
    if observation is None:
        return ()
    try:
        module_observation = observation.get_module_observation(module)
    except Exception:
        return ()
    if module_observation is None:
        return ()
    recent_events = getattr(module_observation, "recent_events", ())
    return tuple(
        event
        for event in tuple(recent_events)[: max(int(limit), 1)]
        if isinstance(event, OperationsObservedEvent)
    )


def _module_observation(
    observation: OperationsObservationReadPort | None,
    *,
    module: str,
) -> Any | None:
    if observation is None:
        return None
    try:
        return observation.get_module_observation(module)
    except Exception:
        return None


def _observation_metric(observer_state: Any | None) -> MetricCardModel:
    if observer_state is None:
        return MetricCardModel(
            id="observed_facts",
            label="Observed Facts",
            value="0",
            delta="runtime facts unavailable",
            tone="warning",
        )
    event_count = _int_from_attr(observer_state, "event_count")
    recent_count = len(getattr(observer_state, "recent_events", ()) or ())
    last_event_name = _display(getattr(observer_state, "last_event_name", None))
    return MetricCardModel(
        id="observed_facts",
        label="Observed Facts",
        value=str(event_count),
        delta=f"{recent_count} recent / last {last_event_name}",
        tone="info",
    )


def _observation_cursor_label(observer_state: Any | None) -> str:
    if observer_state is None:
        return "-"
    return _display(getattr(observer_state, "last_cursor", None))


def _observation_events_label(observer_state: Any | None) -> str:
    if observer_state is None:
        return "-"
    event_count = _int_from_attr(observer_state, "event_count")
    recent_count = len(getattr(observer_state, "recent_events", ()) or ())
    last_event_name = _display(getattr(observer_state, "last_event_name", None))
    return f"{event_count} total / {recent_count} recent / last {last_event_name}"


def _int_from_attr(value: Any, attr: str) -> int:
    raw = getattr(value, attr, 0)
    return raw if isinstance(raw, int) else 0


def _latest_event_time(event_records: tuple[Any, ...]) -> datetime | None:
    timestamps = [_event_record_time(record) for record in event_records]
    return max(timestamps, default=None)


def _latest_datetime(values: tuple[datetime | None, ...]) -> datetime | None:
    timestamps = [
        coerce_utc_datetime(value)
        for value in values
        if isinstance(value, datetime)
    ]
    return max(timestamps, default=None)


def _event_record_time(record: Any) -> datetime:
    occurred_at = getattr(record, "occurred_at", None)
    if isinstance(occurred_at, datetime):
        return coerce_utc_datetime(occurred_at)
    event = getattr(record, "envelope", None)
    occurred_at = getattr(event, "occurred_at", None)
    if isinstance(occurred_at, datetime):
        return coerce_utc_datetime(occurred_at)
    return datetime.min


def _continuation_latency_label(
    continuation_tasks: list[OrchestrationContinuationTask],
) -> str:
    latencies = [
        _age_seconds(task.created_at, now=task.completed_at)
        for task in continuation_tasks
        if task.completed_at is not None
    ]
    if not latencies:
        return "-"
    return f"p95 {_duration_label(_percentile(latencies, 0.95))}"


def _ingress_request_row(
    request: OrchestrationIngressRequest,
    *,
    run_by_id: dict[str, OrchestrationRun],
    dispatch_task: DispatchTask | None,
    now: datetime,
) -> OperationsTableRowModel:
    run = run_by_id.get(request.run_id)
    trace_id = _trace_id(run) if run is not None else request.run_id
    received_at = _dispatch_queued_at(dispatch_task) or request.created_at
    status = (
        dispatch_task.status.value if dispatch_task is not None else request.status.value
    )
    return OperationsTableRowModel(
        id=request.id,
        cells={
            "source": _ingress_source(request, run),
            "intake_key": request.id,
            "received_at": format_datetime_utc(received_at),
            "target_lane": _ingress_target_lane(request, run),
            "priority": _ingress_priority(request, run, dispatch_task=dispatch_task),
            "age": _age_label(received_at, now=now),
            "actions": "Open",
            "status": status,
            "request_status": request.status.value,
            "dispatch_status": status,
            "dispatch_task_id": dispatch_task.id if dispatch_task is not None else "-",
            "dispatch_owner_kind": (
                dispatch_task.owner_kind if dispatch_task is not None else "-"
            ),
            "dispatch_worker": _dispatch_worker(dispatch_task),
            "dispatch_lease_expires_at": _dispatch_lease_expires_at(dispatch_task),
            "kind": request.kind.value,
            "worker_id": _display(request.worker_id),
            "run_id": request.run_id,
            "session_key": _display(run.session_key if run is not None else None),
            "summary": _run_summary(run) if run is not None else request.kind.value,
            "trace": trace_id,
            "route": f"/ui/workbench/runs/{request.run_id}",
            "trace_route": _trace_route_from_id(trace_id),
        },
        status=status,
        tone=_tone_for_dispatch_or_ingress_status(dispatch_task, request.status),
    )


def _ingress_source(
    request: OrchestrationIngressRequest,
    run: OrchestrationRun | None,
) -> str:
    if run is not None:
        return run.inbound_instruction.source
    route_context = request.route_context_payload
    for key in ("surface", "channel", "source"):
        value = route_context.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return request.kind.value


def _ingress_target_lane(
    request: OrchestrationIngressRequest,
    run: OrchestrationRun | None,
) -> str:
    if run is not None:
        return _display(run.lane_key)
    bound_target = request.bound_session_target
    if bound_target is not None and bound_target.lane_key:
        return bound_target.lane_key
    value = request.route_context_payload.get("main_key")
    return _display(value)


def _ingress_priority(
    request: OrchestrationIngressRequest,
    run: OrchestrationRun | None,
    *,
    dispatch_task: DispatchTask | None = None,
) -> str:
    if dispatch_task is not None:
        return f"P{dispatch_task.priority}"
    if request.priority is not None:
        return f"P{request.priority}"
    if run is not None:
        return f"P{run.priority}"
    return "-"


def _tone_for_ingress_status(status: OrchestrationIngressStatus) -> str:
    if status is OrchestrationIngressStatus.FAILED:
        return "danger"
    if status is OrchestrationIngressStatus.COMPLETED:
        return "success"
    if status is OrchestrationIngressStatus.PROCESSING:
        return "info"
    return "neutral"


def _tone_for_dispatch_or_ingress_status(
    dispatch_task: DispatchTask | None,
    ingress_status: OrchestrationIngressStatus,
) -> str:
    if dispatch_task is None:
        return _tone_for_ingress_status(ingress_status)
    return _tone_for_dispatch_status(dispatch_task.status)


def _tone_for_dispatch_or_run_status(
    dispatch_task: DispatchTask | None,
    run_status: OrchestrationRunStatus,
) -> str:
    if dispatch_task is None:
        return _tone_for_run_status(run_status)
    return _tone_for_dispatch_status(dispatch_task.status)


def _tone_for_dispatch_status(status: DispatchTaskStatus) -> str:
    if status is DispatchTaskStatus.FAILED:
        return "danger"
    if status is DispatchTaskStatus.CANCELLED:
        return "neutral"
    if status is DispatchTaskStatus.COMPLETED:
        return "success"
    if status is DispatchTaskStatus.CLAIMED:
        return "info"
    if status in {DispatchTaskStatus.QUEUED, DispatchTaskStatus.WAITING}:
        return "warning"
    return "neutral"


def _dispatch_worker(task: DispatchTask | None) -> str:
    if task is None:
        return "-"
    return _display(task.claimed_by)


def _dispatch_lease_expires_at(task: DispatchTask | None) -> str:
    if task is None or task.lease_expires_at is None:
        return "-"
    return format_datetime_utc(task.lease_expires_at)


def _dispatch_queued_at(task: DispatchTask | None) -> datetime | None:
    if task is None:
        return None
    return task.queued_at or task.created_at


def _dispatch_wait_reason(task: DispatchTask | None) -> str | None:
    if task is None:
        return None
    if task.waiting_reason is not None and task.waiting_reason.strip():
        return task.waiting_reason.strip()
    return task.policy.value


def _dispatch_priority_label(task: DispatchTask | None, fallback: int) -> int:
    return task.priority if task is not None else fallback


def _lane_lock_ttl_label(
    lease: OrchestrationExecutorLease | None,
    *,
    now: datetime,
) -> str:
    if lease is None or lease.lease_expires_at is None:
        return "lease-bound"
    remaining_seconds = int(
        (
            coerce_utc_datetime(lease.lease_expires_at) - coerce_utc_datetime(now)
        ).total_seconds(),
    )
    if remaining_seconds <= 0:
        return "expired"
    return _duration_label(remaining_seconds)


def _lane_lock_expires_label(lease: OrchestrationExecutorLease | None) -> str:
    if lease is None or lease.lease_expires_at is None:
        return "-"
    return format_datetime_utc(lease.lease_expires_at)


def _lane_lock_renewed_at(
    run: OrchestrationRun,
    lease: OrchestrationExecutorLease | None,
) -> datetime:
    if lease is None:
        return run.updated_at
    return max(
        coerce_utc_datetime(run.updated_at),
        coerce_utc_datetime(lease.last_heartbeat_at),
    )


def _event_record_row(record: Any) -> OperationsTableRowModel:
    if isinstance(record, OperationsObservedEvent):
        return _observed_event_row(record)
    event = getattr(record, "envelope", None)
    payload = _event_payload(event)
    event_name = _event_name(event, payload)
    run_id = _optional_str(payload.get("run_id"))
    entity_id = _event_entity_id(payload, fallback=run_id or event_name)
    trace_id = _event_trace_id(event, payload, fallback=run_id)
    return OperationsTableRowModel(
        id=_display(getattr(record, "cursor", None) or getattr(event, "id", None)),
        cells={
            "time": format_datetime_utc(_event_record_time(record)),
            "level": _event_level_from_name(event_name, payload),
            "event": _event_display_label(event_name, payload),
            "event_key": event_name,
            "run_id": _display(run_id),
            "run_id_entity": _display(entity_id),
            "source": _event_source(event_name, payload),
            "summary": _event_summary(event_name, payload),
            "details": _event_details(payload),
            "route": f"/ui/workbench/runs/{run_id}" if run_id else "-",
            "trace_route": _trace_route_from_id(trace_id),
        },
        status=_event_status_from_name(event_name, payload),
        tone=_event_tone_from_name(event_name, payload),
    )


def _observed_event_row(event: OperationsObservedEvent) -> OperationsTableRowModel:
    payload = dict(event.payload)
    run_id = event.run_id or _optional_str(payload.get("run_id"))
    trace_id = event.trace_id or _event_trace_id(event, payload, fallback=run_id)
    return OperationsTableRowModel(
        id=_display(event.cursor or event.id),
        cells={
            "time": format_datetime_utc(event.occurred_at),
            "level": event.level,
            "event": _event_display_label(event.event_name, payload),
            "event_key": event.event_name,
            "run_id": _display(run_id),
            "run_id_entity": _display(event.entity_id),
            "source": _event_source(event.event_name, payload),
            "summary": _event_summary(event.event_name, payload),
            "details": _event_details(payload),
            "route": f"/ui/workbench/runs/{run_id}" if run_id else "-",
            "trace_route": _trace_route_from_id(trace_id),
        },
        status=event.status,
        tone="danger"
        if event.level == "error"
        else "warning"
        if event.level == "warning"
        else "info",
    )


def _event_payload(event: Any) -> dict[str, object]:
    payload = getattr(event, "payload", None)
    return dict(payload) if isinstance(payload, dict) else {}


def _event_name(event: Any, payload: dict[str, object]) -> str:
    event_name = getattr(event, "event_name", None)
    if isinstance(event_name, str) and event_name.strip():
        return event_name.strip()
    raw_name = getattr(event, "name", None)
    if isinstance(raw_name, str) and raw_name.strip():
        return raw_name.strip()
    payload_name = payload.get("event_name")
    if isinstance(payload_name, str) and payload_name.strip():
        return payload_name.strip()
    topic = getattr(event, "topic", None)
    return topic if isinstance(topic, str) and topic.strip() else "event"


def _event_entity_id(
    payload: dict[str, object],
    *,
    fallback: str,
) -> str:
    for key in (
        "run_id",
        "request_id",
        "worker_id",
        "tool_run_id",
        "source_event_id",
    ):
        value = _optional_str(payload.get(key))
        if value:
            return value
    return fallback


def _event_trace_id(
    event: Any,
    payload: dict[str, object],
    *,
    fallback: str | None,
) -> str | None:
    for key in ("trace_id", "correlation_id", "source_event_id"):
        value = _optional_str(payload.get(key))
        if value:
            return value
    trace = getattr(event, "trace", None)
    if isinstance(trace, dict):
        for key in ("trace_id", "correlation_id"):
            value = _optional_str(trace.get(key))
            if value:
                return value
    return fallback


def _event_source(event_name: str, payload: dict[str, object]) -> str:
    source_event_name = _optional_str(payload.get("source_event_name"))
    if source_event_name:
        return _event_source(source_event_name, {})
    if ".ingress." in event_name:
        return "Ingress"
    if ".scheduler." in event_name:
        return "Scheduler"
    if ".executor." in event_name:
        return "Executor"
    if ".runtime." in event_name or "runtime_observation" in event_name:
        return "Runtime"
    if ".run." in event_name:
        return "Run"
    return "Orchestration"


def _event_display_label(event_name: str, payload: dict[str, object]) -> str:
    label = _optional_str(payload.get("display_label"))
    if label:
        return label
    normalized = event_name.strip().lower()
    labels = {
        "orchestration.run.accepted": "Run Accepted",
        "orchestration.run.queued": "Run Queued",
        "orchestration.run.claimed": "Run Claimed",
        "orchestration.run.worker_lease_recovered": "Worker Lease Recovered",
        "orchestration.run.resumed": "Run Resumed",
        "orchestration.run.waiting": "Run Waiting",
        "orchestration.run.completed": "Run Completed",
        "orchestration.run.failed": "Run Failed",
        "orchestration.run.cancelled": "Run Cancelled",
        "orchestration.ingress.requested": "Ingress Requested",
        "orchestration.ingress.queued": "Ingress Queued",
        "orchestration.ingress.claimed": "Ingress Claimed",
        "orchestration.ingress.completed": "Ingress Completed",
        "orchestration.ingress.failed": "Ingress Failed",
        "orchestration.executor.assignment.requested": "Executor Assignment Requested",
        "orchestration.executor.lease.registered": "Executor Registered",
        "orchestration.executor.lease.heartbeated": "Executor Heartbeat",
        "orchestration.executor.lease.expired": "Executor Lease Expired",
        "orchestration.runtime.status": "Runtime Status",
        "orchestration.run.message_appended": "Run Message Appended",
        "orchestration.run.tool_updated": "Tool Updated",
        "orchestration.run.llm_text_delta": "LLM Text Delta",
        "orchestration.llm_resolved": "LLM Resolved",
    }
    if normalized in labels:
        return labels[normalized]
    return _title_from_event_name(event_name)


def _event_summary(event_name: str, payload: dict[str, object]) -> str:
    summary = _optional_str(payload.get("display_summary")) or _optional_str(
        payload.get("summary"),
    )
    if summary:
        return _truncate(summary)
    status = _event_status_from_name(event_name, payload)
    entity = _event_entity_id(payload, fallback="")
    source = _event_source(event_name, payload)
    parts = [_event_display_label(event_name, payload)]
    if status:
        parts.append(f"status {status}")
    if entity:
        parts.append(f"entity {entity}")
    if source and source != "Orchestration":
        parts.append(f"via {source}")
    return _truncate(" / ".join(parts))


def _event_details(payload: dict[str, object]) -> str:
    parts = []
    for key in (
        "code",
        "message",
        "reason",
        "status",
        "worker_id",
        "lane_key",
        "request_id",
        "tool_run_id",
        "source_event_name",
        "event_name",
    ):
        value = _optional_str(payload.get(key))
        if value:
            parts.append(f"{key}={value}")
    return _truncate("; ".join(parts) if parts else "-")


def _event_level_from_name(event_name: str, payload: dict[str, object]) -> str:
    status = _event_status_from_name(event_name, payload)
    if status in {"failed", "error"}:
        return "error"
    if status in {"waiting", "cancelled", "offline"}:
        return "warning"
    return "info"


def _event_status_from_name(event_name: str, payload: dict[str, object]) -> str:
    status = _optional_str(payload.get("status"))
    if status:
        return status
    tail = event_name.rsplit(".", 1)[-1]
    return tail.replace("_", "-")


def _event_tone_from_name(event_name: str, payload: dict[str, object]) -> str:
    display_tone = _optional_str(payload.get("display_tone")) or _optional_str(
        payload.get("tone"),
    )
    if display_tone in {"success", "warning", "danger", "info", "neutral"}:
        return display_tone
    level = _event_level_from_name(event_name, payload)
    if level == "error":
        return "danger"
    if level == "warning":
        return "warning"
    status = _event_status_from_name(event_name, payload)
    if status in {"completed", "heartbeated", "registered"}:
        return "success"
    return "info"


def _title_from_event_name(event_name: str) -> str:
    tail = event_name.removeprefix("orchestration.")
    parts = [
        part
        for segment in tail.split(".")
        for part in segment.split("_")
        if part.strip()
    ]
    if not parts:
        return "Event"
    return " ".join(part[:1].upper() + part[1:] for part in parts)


def _trace_route_from_id(trace_id: str | None) -> str:
    return f"/ui/trace/{trace_id}" if trace_id else "-"


def _optional_str(value: object | None) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _queue_wait_p95(runs: list[OrchestrationRun], *, now: datetime) -> str:
    if not runs:
        return "0s"
    ages = [_age_seconds(run.queued_at or run.created_at, now=now) for run in runs]
    return _duration_label(_percentile(ages, 0.95))


def _percentile(values: list[int], percentile: float) -> int:
    if not values:
        return 0
    sorted_values = sorted(values)
    index = round((len(sorted_values) - 1) * percentile)
    return sorted_values[index]


def _percent_label(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "-"
    return f"{round((numerator / denominator) * 100)}%"


def _next_lease_expiry_label(leases: list[OrchestrationExecutorLease]) -> str:
    expiries = [lease.lease_expires_at for lease in leases if lease.lease_expires_at]
    if not expiries:
        return "-"
    return format_datetime_utc(min(expiries))


def _max_age_label(
    values: tuple[datetime | None, ...],
    *,
    now: datetime,
) -> str:
    ages = [_age_seconds(value, now=now) for value in values if value is not None]
    if not ages:
        return "-"
    return _duration_label(max(ages))


def _age_seconds(value: datetime | None, *, now: datetime) -> int:
    if value is None:
        return 0
    return max(
        int((coerce_utc_datetime(now) - coerce_utc_datetime(value)).total_seconds()),
        0,
    )


def _duration_label(seconds: int) -> str:
    seconds = max(seconds, 0)
    if seconds < 60:
        return f"{seconds}s"
    minutes, seconds = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes}m {seconds}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes}m"


def _display(value: object | None) -> str:
    if value is None:
        return "-"
    text = str(value).strip()
    return text or "-"


def _optional_metadata_text(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int(value: object | None, default: int = 0) -> int:
    if isinstance(value, bool):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _trace_id(run: OrchestrationRun) -> str:
    trace_id = run.metadata.get("trace_id")
    if isinstance(trace_id, str) and trace_id.strip():
        return trace_id.strip()
    correlation_id = run.metadata.get("correlation_id")
    if isinstance(correlation_id, str) and correlation_id.strip():
        return correlation_id.strip()
    return run.id


def _trace_route(run: OrchestrationRun) -> str:
    return f"/ui/trace/{_trace_id(run)}"


def _workbench_route(run: OrchestrationRun) -> str:
    return f"/ui/workbench/runs/{run.id}"


def _run_wait_reason(run: OrchestrationRun) -> str:
    if run.waiting_reason:
        return run.waiting_reason
    if run.stage is OrchestrationRunStage.WAITING_FOR_CONFIRMATION:
        return "Waiting for approval"
    if run.stage is OrchestrationRunStage.WAITING_ON_TOOL:
        return "Waiting for tool"
    if run.lane_key:
        return "Waiting for worker"
    return run.queue_policy.value


def _run_summary(run: OrchestrationRun) -> str:
    content = run.inbound_instruction.content
    if content is None:
        return "-"
    if isinstance(content, str):
        return _truncate(content)
    return _truncate(str(content))


def _run_error_code(run: OrchestrationRun) -> str:
    error = run.error
    if error is None:
        return "-"
    code = getattr(error, "code", None)
    return _display(code)


def _run_error_message(run: OrchestrationRun) -> str:
    error = run.error
    if error is None:
        return "-"
    message = getattr(error, "message", None)
    return _truncate(_display(message))


def _run_event_details(run: OrchestrationRun) -> str:
    details = [f"stage={run.stage.value}"]
    if run.worker_id:
        details.append(f"worker={run.worker_id}")
    if run.lane_key:
        details.append(f"lane={run.lane_key}")
    return "; ".join(details)


def _event_level(status: OrchestrationRunStatus) -> str:
    if status is OrchestrationRunStatus.FAILED:
        return "error"
    if status in {
        OrchestrationRunStatus.CANCELLED,
        OrchestrationRunStatus.WAITING,
    }:
        return "warning"
    return "info"


def _tone_for_run_status(status: OrchestrationRunStatus) -> str:
    if status is OrchestrationRunStatus.FAILED:
        return "danger"
    if status is OrchestrationRunStatus.COMPLETED:
        return "success"
    if status in {
        OrchestrationRunStatus.CANCELLED,
        OrchestrationRunStatus.WAITING,
    }:
        return "warning"
    if status is OrchestrationRunStatus.RUNNING:
        return "info"
    return "neutral"


def _tone_for_executor_status(status: str) -> str:
    if status == "online":
        return "success"
    if status == "draining":
        return "warning"
    if status == "offline":
        return "danger"
    return "neutral"


def _truncate(value: str, *, limit: int = 96) -> str:
    if len(value) <= limit:
        return value
    return f"{value[: limit - 3]}..."


def _age_label(value: datetime | None, *, now: datetime) -> str:
    if value is None:
        return "-"
    return _duration_label(_age_seconds(value, now=now))
