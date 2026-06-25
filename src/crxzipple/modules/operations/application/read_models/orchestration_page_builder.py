from __future__ import annotations

from time import perf_counter
from typing import Any

from crxzipple.modules.orchestration.application.ports import (
    OrchestrationExecutorLeaseQueryPort,
    OrchestrationRunQueryPort,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsModuleRoleModel,
)
from crxzipple.modules.operations.application.read_models.orchestration_actions import (
    page_actions as _page_actions,
)
from crxzipple.modules.operations.application.read_models.orchestration_models import (
    OrchestrationOperationsPage,
)
from crxzipple.modules.operations.application.read_models.orchestration_page_facts import (
    collect_orchestration_page_facts,
)
from crxzipple.modules.operations.application.read_models.orchestration_page_sections import (
    build_orchestration_page_sections,
)
from crxzipple.modules.operations.application.read_models.orchestration_ports import (
    OrchestrationContinuationQueryPort,
    OrchestrationDispatchTaskQueryPort,
    OrchestrationIngressRequestQueryPort,
)
from crxzipple.modules.operations.application.read_models.orchestration_projection_diagnostics import (
    orchestration_projection_diagnostics,
)
from crxzipple.modules.operations.application.read_models.ports_runtime import (
    OperationsObservationReadPort,
)
from crxzipple.shared.time import format_datetime_utc


def orchestration_operations_page(
    *,
    run_query: OrchestrationRunQueryPort,
    executor_lease_query: OrchestrationExecutorLeaseQueryPort,
    ingress_query: OrchestrationIngressRequestQueryPort | None = None,
    continuation_query: OrchestrationContinuationQueryPort | None = None,
    dispatch_query: OrchestrationDispatchTaskQueryPort | None = None,
    operations_observation: OperationsObservationReadPort | None = None,
    runtime_bootstrap_config: Any | None = None,
    worker_lease_seconds: int | None = None,
    worker_heartbeat_seconds: float | None = None,
) -> OrchestrationOperationsPage:
    projection_started_at = perf_counter()
    facts = collect_orchestration_page_facts(
        run_query=run_query,
        executor_lease_query=executor_lease_query,
        ingress_query=ingress_query,
        continuation_query=continuation_query,
        dispatch_query=dispatch_query,
        operations_observation=operations_observation,
    )
    actions = _page_actions()
    sections = build_orchestration_page_sections(
        facts=facts,
        run_query=run_query,
        runtime_bootstrap_config=runtime_bootstrap_config,
        worker_lease_seconds=worker_lease_seconds,
        worker_heartbeat_seconds=worker_heartbeat_seconds,
    )

    return OrchestrationOperationsPage(
        module="orchestration",
        title="Orchestration",
        subtitle="调度器、运行队列、Lane Lock、Executor、故障与操作事件的统一控制台。",
        health=facts.health,
        updated_at=format_datetime_utc(facts.now),
        auto_refresh=True,
        role=OperationsModuleRoleModel(
            label="Admin",
            can_operate=True,
            scope="orchestration",
        ),
        metrics=sections.metrics,
        tabs=sections.tabs,
        active_tab="overview",
        actions=actions,
        scheduler_status=sections.scheduler_status,
        backpressure=sections.backpressure,
        stuck_runs=sections.stuck_runs,
        policy_limits=sections.policy_limits,
        run_queue=sections.run_queue,
        execution_chains=sections.execution_chains,
        repeated_probes=sections.repeated_probes,
        lane_locks=sections.lane_locks,
        executor_overview=sections.executor_overview,
        ingress_queue=sections.ingress_queue,
        recent_failures=sections.recent_failures,
        ops_event_log=sections.ops_event_log,
        projection_diagnostics=orchestration_projection_diagnostics(
            runs=facts.runs,
            leases=facts.leases,
            ingress_requests=facts.ingress_requests,
            continuation_tasks=facts.continuation_tasks,
            dispatch_tasks=facts.dispatch_tasks,
            observed_events=facts.observed_events,
            owner_call_count=facts.owner_call_count,
            elapsed_ms=(perf_counter() - projection_started_at) * 1000,
            freshness_at=format_datetime_utc(facts.now),
        ),
    )
