from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from crxzipple.modules.orchestration.application.dispatch_owner_kinds import (
    ORCHESTRATION_INGRESS_DISPATCH_OWNER_KIND,
    ORCHESTRATION_STEP_DISPATCH_OWNER_KIND,
)
from crxzipple.modules.orchestration.application.ports import (
    OrchestrationExecutorLeaseQueryPort,
    OrchestrationRunQueryPort,
)
from crxzipple.modules.orchestration.domain.value_objects import (
    OrchestrationRunStage,
    OrchestrationRunStatus,
    utcnow,
)
from crxzipple.modules.operations.application.read_models.orchestration_ingress_state import (
    pending_ingress_requests as _pending_ingress_requests,
)
from crxzipple.modules.operations.application.read_models.orchestration_metrics import (
    health as _health,
    recent_failed_runs as _recent_failed_runs,
)
from crxzipple.modules.operations.application.read_models.orchestration_ports import (
    OrchestrationContinuationQueryPort,
    OrchestrationDispatchTaskQueryPort,
    OrchestrationIngressRequestQueryPort,
)
from crxzipple.modules.operations.application.read_models.orchestration_runtime_facts import (
    dispatch_tasks_by_owner as _dispatch_tasks_by_owner,
    dispatch_tasks_by_payload_ref as _dispatch_tasks_by_payload_ref,
    list_continuation_tasks as _list_continuation_tasks,
    list_dispatch_tasks as _list_dispatch_tasks,
    list_ingress_requests as _list_ingress_requests,
    module_observation as _module_observation,
    recent_operations_events as _recent_operations_events,
    run_is_dispatch_queued as _run_is_dispatch_queued,
)
from crxzipple.modules.operations.application.read_models.ports_runtime import (
    OperationsObservationReadPort,
)


@dataclass(frozen=True, slots=True)
class OrchestrationPageFacts:
    now: datetime
    runs: list[Any]
    leases: list[Any]
    ingress_requests: list[Any]
    continuation_tasks: list[Any]
    dispatch_tasks: list[Any]
    ingress_dispatch_by_request_id: dict[str, Any]
    step_dispatch_by_run_id: dict[str, Any]
    observed_events: tuple[Any, ...]
    observer_state: Any | None
    pending_ingress_requests: list[Any]
    visible_ingress_count: int
    queued_runs: list[Any]
    running_runs: list[Any]
    waiting_runs: list[Any]
    failed_runs: list[Any]
    recent_failed_runs: list[Any]
    cancelled_runs: list[Any]
    backpressure_total: int
    completed_count: int
    online_leases: list[Any]
    capacity: int
    inflight: int
    available: int
    health: str
    approval_waiting_count: int
    owner_call_count: int


def collect_orchestration_page_facts(
    *,
    run_query: OrchestrationRunQueryPort,
    executor_lease_query: OrchestrationExecutorLeaseQueryPort,
    ingress_query: OrchestrationIngressRequestQueryPort | None = None,
    continuation_query: OrchestrationContinuationQueryPort | None = None,
    dispatch_query: OrchestrationDispatchTaskQueryPort | None = None,
    operations_observation: OperationsObservationReadPort | None = None,
) -> OrchestrationPageFacts:
    now = utcnow()
    runs = run_query.list_runs()
    leases = executor_lease_query.list_executor_leases(status=None)
    ingress_requests = _list_ingress_requests(ingress_query)
    continuation_tasks = _list_continuation_tasks(continuation_query)
    dispatch_tasks = _list_dispatch_tasks(dispatch_query)
    ingress_dispatch_by_request_id = _dispatch_tasks_by_owner(
        dispatch_tasks,
        owner_kind=ORCHESTRATION_INGRESS_DISPATCH_OWNER_KIND,
    )
    step_dispatch_by_run_id = _dispatch_tasks_by_payload_ref(
        dispatch_tasks,
        owner_kind=ORCHESTRATION_STEP_DISPATCH_OWNER_KIND,
    )
    observed_events = _recent_operations_events(
        observation=operations_observation,
        module="orchestration",
        limit=60,
    )
    observer_state = _module_observation(
        operations_observation,
        module="orchestration",
    )
    pending_ingress_requests = _pending_ingress_requests(
        ingress_requests,
        dispatch_task_by_request_id=ingress_dispatch_by_request_id,
    )
    counts = Counter(run.status for run in runs)
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
    failed_runs = [run for run in runs if run.status is OrchestrationRunStatus.FAILED]
    recent_failed_runs = _recent_failed_runs(failed_runs, now=now)
    cancelled_runs = [
        run for run in runs if run.status is OrchestrationRunStatus.CANCELLED
    ]
    online_leases = [
        lease for lease in leases if lease.counts_toward_capacity(now=now)
    ]
    available = sum(lease.available_assignment_slots(now=now) for lease in online_leases)
    return OrchestrationPageFacts(
        now=now,
        runs=runs,
        leases=leases,
        ingress_requests=ingress_requests,
        continuation_tasks=continuation_tasks,
        dispatch_tasks=dispatch_tasks,
        ingress_dispatch_by_request_id=ingress_dispatch_by_request_id,
        step_dispatch_by_run_id=step_dispatch_by_run_id,
        observed_events=observed_events,
        observer_state=observer_state,
        pending_ingress_requests=pending_ingress_requests,
        visible_ingress_count=len(pending_ingress_requests),
        queued_runs=queued_runs,
        running_runs=running_runs,
        waiting_runs=waiting_runs,
        failed_runs=failed_runs,
        recent_failed_runs=recent_failed_runs,
        cancelled_runs=cancelled_runs,
        backpressure_total=len(queued_runs) + len(waiting_runs),
        completed_count=counts[OrchestrationRunStatus.COMPLETED],
        online_leases=online_leases,
        capacity=sum(lease.max_inflight_assignments for lease in online_leases),
        inflight=sum(lease.inflight_assignment_count for lease in online_leases),
        available=available,
        health=_health(
            queued_runs=queued_runs,
            running_runs=running_runs,
            waiting_runs=waiting_runs,
            failed_runs=recent_failed_runs,
            available_executor_slots=available,
        ),
        approval_waiting_count=len(
            [
                run
                for run in waiting_runs
                if run.stage is OrchestrationRunStage.WAITING_FOR_CONFIRMATION
            ],
        ),
        owner_call_count=(
            2
            + (1 if ingress_query is not None else 0)
            + (1 if continuation_query is not None else 0)
            + (1 if dispatch_query is not None else 0)
            + (1 if operations_observation is not None else 0)
        ),
    )
