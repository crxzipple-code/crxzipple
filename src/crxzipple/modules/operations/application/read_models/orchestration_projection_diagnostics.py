from __future__ import annotations

from crxzipple.modules.dispatch.domain import DispatchTask
from crxzipple.modules.orchestration.application.coordinators.continuation_tasks import (
    OrchestrationContinuationTask,
)
from crxzipple.modules.orchestration.domain import (
    OrchestrationExecutorLease,
    OrchestrationIngressRequest,
    OrchestrationRun,
)
from crxzipple.modules.operations.application.observation_models import OperationsObservedEvent
from crxzipple.modules.operations.application.read_models.models import (
    OperationsOwnerFactSourceModel,
    OperationsProjectionDiagnosticsModel,
)


def orchestration_projection_diagnostics(
    *,
    runs: list[OrchestrationRun],
    leases: list[OrchestrationExecutorLease],
    ingress_requests: list[OrchestrationIngressRequest],
    continuation_tasks: list[OrchestrationContinuationTask],
    dispatch_tasks: list[DispatchTask],
    observed_events: tuple[OperationsObservedEvent, ...],
    owner_call_count: int,
    elapsed_ms: float,
    freshness_at: str,
) -> OperationsProjectionDiagnosticsModel:
    return OperationsProjectionDiagnosticsModel(
        module="orchestration",
        owner_sources=(
            OperationsOwnerFactSourceModel(
                module="orchestration",
                facts=(
                    "runs",
                    "execution_chains",
                    "execution_steps",
                    "execution_step_items",
                    "executor_leases",
                    "ingress_requests",
                    "continuation_tasks",
                ),
                read_path="OrchestrationRunQueryPort",
            ),
            OperationsOwnerFactSourceModel(
                module="dispatch",
                facts=("dispatch_tasks",),
                read_path="OrchestrationDispatchTaskQueryPort",
            ),
            OperationsOwnerFactSourceModel(
                module="operations",
                facts=("observed_events", "observer_state"),
                read_path="OperationsObservationReadPort",
            ),
        ),
        owner_call_count=owner_call_count,
        processed_item_count=(
            len(runs)
            + len(leases)
            + len(ingress_requests)
            + len(continuation_tasks)
            + len(dispatch_tasks)
            + len(observed_events)
        ),
        elapsed_ms=round(elapsed_ms, 3),
        freshness_at=freshness_at,
    )
