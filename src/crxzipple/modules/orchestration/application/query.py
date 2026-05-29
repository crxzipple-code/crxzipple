"""Read-side queries for orchestration runs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from crxzipple.modules.orchestration.application.unit_of_work import (
    OrchestrationUnitOfWork,
)
from crxzipple.modules.orchestration.domain.entities import OrchestrationRun
from crxzipple.modules.orchestration.domain.entities import (
    OrchestrationExecutorLease,
    OrchestrationIngressRequest,
    OrchestrationSchedulerSignal,
)
from crxzipple.modules.orchestration.domain.exceptions import (
    OrchestrationRunNotFoundError,
)
from crxzipple.modules.orchestration.domain.value_objects import (
    OrchestrationExecutorLeaseStatus,
    OrchestrationIngressStatus,
    OrchestrationRunStatus,
    OrchestrationSchedulerSignalStatus,
)


@dataclass(slots=True)
class OrchestrationRunQueryService:
    uow_factory: Callable[[], OrchestrationUnitOfWork]

    def get_run(self, run_id: str) -> OrchestrationRun:
        with self.uow_factory() as uow:
            run = uow.orchestration_runs.get(run_id)
            if run is None:
                raise OrchestrationRunNotFoundError(
                    f"Orchestration run '{run_id}' was not found.",
                )
            return run

    def list_runs(
        self,
        *,
        status: OrchestrationRunStatus | None = None,
    ) -> list[OrchestrationRun]:
        with self.uow_factory() as uow:
            return uow.orchestration_runs.list(status=status)

    def list_ingress_requests(
        self,
        *,
        status: OrchestrationIngressStatus | None = None,
    ) -> list[OrchestrationIngressRequest]:
        with self.uow_factory() as uow:
            return uow.orchestration_ingress_requests.list(status=status)

    def list_scheduler_signals(
        self,
        *,
        status: OrchestrationSchedulerSignalStatus | None = None,
    ) -> list[OrchestrationSchedulerSignal]:
        with self.uow_factory() as uow:
            return uow.orchestration_scheduler_signals.list(status=status)

    def list_executor_leases(
        self,
        *,
        status: OrchestrationExecutorLeaseStatus | None = None,
    ) -> list[OrchestrationExecutorLease]:
        with self.uow_factory() as uow:
            return uow.orchestration_executor_leases.list(status=status)
