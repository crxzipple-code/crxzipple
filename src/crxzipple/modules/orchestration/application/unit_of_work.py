from __future__ import annotations

from typing import Any, Protocol

from crxzipple.modules.dispatch.domain import DispatchTaskRepository
from crxzipple.modules.orchestration.domain.repositories import (
    ExecutionChainRepository,
    ExecutionStepItemRepository,
    ExecutionStepRepository,
    OrchestrationExecutorLeaseRepository,
    OrchestrationIngressRequestRepository,
    OrchestrationRunRepository,
    OrchestrationRunWaitRepository,
)
from crxzipple.shared.domain.aggregates import AggregateRoot


class OrchestrationUnitOfWork(Protocol):
    execution_chains: ExecutionChainRepository
    execution_steps: ExecutionStepRepository
    execution_step_items: ExecutionStepItemRepository
    orchestration_runs: OrchestrationRunRepository
    orchestration_ingress_requests: OrchestrationIngressRequestRepository
    orchestration_executor_leases: OrchestrationExecutorLeaseRepository
    orchestration_waits: OrchestrationRunWaitRepository
    dispatch_tasks: DispatchTaskRepository

    def __enter__(self) -> "OrchestrationUnitOfWork":
        ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> None:
        ...

    def collect(self, aggregate: AggregateRoot[Any]) -> None:
        ...

    def commit(self) -> None:
        ...

    def rollback(self) -> None:
        ...
