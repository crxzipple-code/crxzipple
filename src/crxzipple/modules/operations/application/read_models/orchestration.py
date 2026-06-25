from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from crxzipple.modules.orchestration.application.ports import (
    OrchestrationExecutorLeaseQueryPort,
    OrchestrationRunQueryPort,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsModuleOverview,
)
from crxzipple.modules.operations.application.read_models.orchestration_models import (
    OrchestrationOperationsPage,
)
from crxzipple.modules.operations.application.read_models.orchestration_overview_builder import (
    orchestration_operations_overview,
)
from crxzipple.modules.operations.application.read_models.orchestration_page_builder import (
    orchestration_operations_page,
)
from crxzipple.modules.operations.application.read_models.orchestration_ports import (
    OrchestrationContinuationQueryPort,
    OrchestrationDispatchTaskQueryPort,
    OrchestrationIngressRequestQueryPort,
)
from crxzipple.modules.operations.application.read_models.ports_runtime import (
    OperationsObservationReadPort,
)


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
        return orchestration_operations_overview(
            run_query=self.run_query,
            executor_lease_query=self.executor_lease_query,
            ingress_query=self.ingress_query,
            dispatch_query=self.dispatch_query,
        )

    def page(self) -> OrchestrationOperationsPage:
        return orchestration_operations_page(
            run_query=self.run_query,
            executor_lease_query=self.executor_lease_query,
            ingress_query=self.ingress_query,
            continuation_query=self.continuation_query,
            dispatch_query=self.dispatch_query,
            operations_observation=self.operations_observation,
            runtime_bootstrap_config=self.runtime_bootstrap_config,
            worker_lease_seconds=self.worker_lease_seconds,
            worker_heartbeat_seconds=self.worker_heartbeat_seconds,
        )
