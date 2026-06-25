from __future__ import annotations

from crxzipple.modules.orchestration.application.dispatch_owner_kinds import (
    ORCHESTRATION_INGRESS_DISPATCH_OWNER_KIND,
    ORCHESTRATION_STEP_DISPATCH_OWNER_KIND,
)
from crxzipple.modules.orchestration.application.ports import (
    OrchestrationExecutorLeaseQueryPort,
    OrchestrationRunQueryPort,
)
from crxzipple.modules.orchestration.domain.value_objects import (
    OrchestrationRunStatus,
    utcnow,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsModuleOverview,
)
from crxzipple.modules.operations.application.read_models.orchestration_actions import (
    overview_actions as _overview_actions,
)
from crxzipple.modules.operations.application.read_models.orchestration_ingress_state import (
    pending_ingress_requests as _pending_ingress_requests,
)
from crxzipple.modules.operations.application.read_models.orchestration_metrics import (
    health as _health,
    recent_failed_runs as _recent_failed_runs,
)
from crxzipple.modules.operations.application.read_models.orchestration_overview_rows import (
    executor_rows as _executor_rows,
    lane_lock_rows as _lane_lock_rows,
    queue_rows as _queue_rows,
)
from crxzipple.modules.operations.application.read_models.orchestration_ports import (
    OrchestrationDispatchTaskQueryPort,
    OrchestrationIngressRequestQueryPort,
)
from crxzipple.modules.operations.application.read_models.orchestration_runtime_facts import (
    dispatch_tasks_by_owner as _dispatch_tasks_by_owner,
    dispatch_tasks_by_payload_ref as _dispatch_tasks_by_payload_ref,
    list_dispatch_tasks as _list_dispatch_tasks,
    list_ingress_requests as _list_ingress_requests,
    run_is_dispatch_queued as _run_is_dispatch_queued,
)
from crxzipple.modules.operations.application.read_models.orchestration_summary_sections import (
    overview_metrics as _overview_metrics,
)
from crxzipple.shared.time import format_datetime_utc


def orchestration_operations_overview(
    *,
    run_query: OrchestrationRunQueryPort,
    executor_lease_query: OrchestrationExecutorLeaseQueryPort,
    ingress_query: OrchestrationIngressRequestQueryPort | None = None,
    dispatch_query: OrchestrationDispatchTaskQueryPort | None = None,
) -> OperationsModuleOverview:
    now = utcnow()
    runs = run_query.list_runs()
    leases = executor_lease_query.list_executor_leases(status=None)
    ingress_requests = _list_ingress_requests(ingress_query)
    dispatch_tasks = _list_dispatch_tasks(dispatch_query)
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
    failed_runs = [run for run in runs if run.status is OrchestrationRunStatus.FAILED]
    recent_failed_runs = _recent_failed_runs(failed_runs, now=now)
    online_leases = [
        lease for lease in leases if lease.counts_toward_capacity(now=now)
    ]
    capacity = sum(lease.max_inflight_assignments for lease in online_leases)
    inflight = sum(lease.inflight_assignment_count for lease in online_leases)
    available = sum(lease.available_assignment_slots(now=now) for lease in online_leases)
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
        metrics=_overview_metrics(
            health=health,
            visible_ingress_count=visible_ingress_count,
            ingress_requests=ingress_requests,
            running_runs=running_runs,
            waiting_runs=waiting_runs,
            queued_runs=queued_runs,
            available_executor_slots=available,
            online_executor_count=len(online_leases),
            inflight_executor_count=inflight,
            executor_capacity=capacity,
            failed_runs=failed_runs,
            recent_failed_runs=recent_failed_runs,
            now=now,
        ),
        queue=_queue_rows(
            queued_runs,
            dispatch_task_by_run_id=step_dispatch_by_run_id,
            now=now,
        ),
        lane_locks=_lane_lock_rows(running_runs, now=now),
        executor=_executor_rows(leases, running_runs=running_runs, now=now),
        actions=_overview_actions(),
    )
