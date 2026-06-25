from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from crxzipple.modules.orchestration.application.ports import OrchestrationRunQueryPort
from crxzipple.modules.operations.application.read_models.models import (
    MetricCardModel,
    OperationsChartSectionModel,
    OperationsKeyValueSectionModel,
    OperationsTabModel,
    OperationsTableSectionModel,
)
from crxzipple.modules.operations.application.read_models.orchestration_backpressure_sections import (
    active_lane_keys as _active_lane_keys,
    backpressure_section as _backpressure_section,
)
from crxzipple.modules.operations.application.read_models.orchestration_event_log_sections import (
    ops_event_log_section as _ops_event_log_section,
)
from crxzipple.modules.operations.application.read_models.orchestration_execution_chain_sections import (
    execution_chain_section as _execution_chain_section,
)
from crxzipple.modules.operations.application.read_models.orchestration_failure_sections import (
    recent_failures_section as _recent_failures_section,
    repeated_probe_section as _repeated_probe_section,
)
from crxzipple.modules.operations.application.read_models.orchestration_ingress_sections import (
    ingress_queue_section as _ingress_queue_section,
)
from crxzipple.modules.operations.application.read_models.orchestration_page_facts import (
    OrchestrationPageFacts,
)
from crxzipple.modules.operations.application.read_models.orchestration_page_tabs import (
    page_tabs as _page_tabs,
)
from crxzipple.modules.operations.application.read_models.orchestration_policy_sections import (
    policy_limits_section as _policy_limits_section,
)
from crxzipple.modules.operations.application.read_models.orchestration_queue_sections import (
    run_queue_section as _run_queue_section,
)
from crxzipple.modules.operations.application.read_models.orchestration_status_sections import (
    scheduler_status_section as _scheduler_status_section,
)
from crxzipple.modules.operations.application.read_models.orchestration_stuck_run_sections import (
    stuck_runs_section as _stuck_runs_section,
)
from crxzipple.modules.operations.application.read_models.orchestration_summary_sections import (
    page_metrics as _page_metrics,
)
from crxzipple.modules.operations.application.read_models.orchestration_worker_sections import (
    executor_section as _executor_section,
    lane_locks_section as _lane_locks_section,
)


@dataclass(frozen=True, slots=True)
class OrchestrationPageSections:
    metrics: tuple[MetricCardModel, ...]
    tabs: tuple[OperationsTabModel, ...]
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


def build_orchestration_page_sections(
    *,
    facts: OrchestrationPageFacts,
    run_query: OrchestrationRunQueryPort,
    runtime_bootstrap_config: Any | None = None,
    worker_lease_seconds: int | None = None,
    worker_heartbeat_seconds: float | None = None,
) -> OrchestrationPageSections:
    execution_chains = _execution_chain_section(
        run_query,
        facts.runs,
        dispatch_task_by_run_id=facts.step_dispatch_by_run_id,
        now=facts.now,
    )
    repeated_probes = _repeated_probe_section(facts.runs)
    return OrchestrationPageSections(
        metrics=_page_metrics(
            health=facts.health,
            visible_ingress_count=facts.visible_ingress_count,
            ingress_requests=facts.ingress_requests,
            running_runs=facts.running_runs,
            waiting_runs=facts.waiting_runs,
            queued_runs=facts.queued_runs,
            backpressure_total=facts.backpressure_total,
            approval_waiting_count=facts.approval_waiting_count,
            failed_runs=facts.failed_runs,
            recent_failed_runs=facts.recent_failed_runs,
            cancelled_runs=facts.cancelled_runs,
            runs=facts.runs,
            observer_state=facts.observer_state,
            now=facts.now,
        ),
        tabs=_page_tabs(
            queued_run_count=len(facts.queued_runs),
            execution_chain_count=execution_chains.total,
            repeated_probe_count=repeated_probes.total,
            lane_lock_count=len([run for run in facts.running_runs if run.lane_lock_key]),
            executor_count=len(facts.leases),
            failed_run_count=len(facts.failed_runs),
            has_recent_failures=bool(facts.recent_failed_runs),
        ),
        scheduler_status=_scheduler_status_section(
            runs=facts.runs,
            queued_runs=facts.queued_runs,
            continuation_tasks=facts.continuation_tasks,
            dispatch_tasks=facts.dispatch_tasks,
            event_records=facts.observed_events,
            completed_count=facts.completed_count,
            failed_count=len(facts.failed_runs),
            cancelled_count=len(facts.cancelled_runs),
            available_executor_slots=facts.available,
            observer_state=facts.observer_state,
            now=facts.now,
        ),
        backpressure=_backpressure_section(
            queued_runs=facts.queued_runs,
            waiting_runs=facts.waiting_runs,
            active_lane_keys=_active_lane_keys(facts.running_runs, facts.waiting_runs),
            available_executor_slots=facts.available,
        ),
        stuck_runs=_stuck_runs_section(
            queued_runs=facts.queued_runs,
            running_runs=facts.running_runs,
            waiting_runs=facts.waiting_runs,
            now=facts.now,
        ),
        policy_limits=_policy_limits_section(
            leases=facts.leases,
            online_leases=facts.online_leases,
            capacity=facts.capacity,
            inflight=facts.inflight,
            available=facts.available,
            runtime_bootstrap_config=runtime_bootstrap_config,
            worker_lease_seconds=worker_lease_seconds,
            worker_heartbeat_seconds=worker_heartbeat_seconds,
        ),
        run_queue=_run_queue_section(
            facts.queued_runs,
            dispatch_task_by_run_id=facts.step_dispatch_by_run_id,
            now=facts.now,
        ),
        execution_chains=execution_chains,
        repeated_probes=repeated_probes,
        lane_locks=_lane_locks_section(
            facts.running_runs,
            leases=facts.leases,
            now=facts.now,
        ),
        executor_overview=_executor_section(
            facts.leases,
            runs=facts.runs,
            running_runs=facts.running_runs,
            now=facts.now,
        ),
        ingress_queue=_ingress_queue_section(
            facts.pending_ingress_requests,
            fallback_runs=[],
            run_by_id={run.id: run for run in facts.runs},
            dispatch_task_by_request_id=facts.ingress_dispatch_by_request_id,
            now=facts.now,
        ),
        recent_failures=_recent_failures_section(facts.failed_runs),
        ops_event_log=_ops_event_log_section(event_records=facts.observed_events),
    )
