from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Protocol

from crxzipple.core.logger import get_logger
from crxzipple.modules.orchestration.application.lease_manager import (
    OrchestrationLeaseManager,
)
from crxzipple.modules.orchestration.application.tool_resume import (
    OrchestrationToolResumeCoordinator,
)
from crxzipple.modules.orchestration.domain import (
    OrchestrationExecutorLease,
    OrchestrationRun,
    OrchestrationRunRepository,
    OrchestrationRunStatus,
)


logger = get_logger(__name__)


class RecoveryCoordinatorUnitOfWork(Protocol):
    orchestration_runs: OrchestrationRunRepository

    def __enter__(self) -> "RecoveryCoordinatorUnitOfWork":
        ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> None:
        ...


@dataclass(slots=True)
class RunRecoveryCoordinator:
    uow_factory: Callable[[], RecoveryCoordinatorUnitOfWork]
    lease_manager: OrchestrationLeaseManager
    continue_recovery_contract: Callable[[str], OrchestrationRun]
    tool_resume: OrchestrationToolResumeCoordinator | None

    def expire_executor_leases(self) -> list[OrchestrationExecutorLease]:
        return self.lease_manager.mark_expired_executor_leases_offline()

    def recover_abandoned_runs(self) -> list[OrchestrationRun]:
        recovered: dict[str, OrchestrationRun] = {
            run.id: run for run in self.lease_manager.recover_abandoned_runs()
        }
        with self.uow_factory() as uow:
            waiting_runs = uow.orchestration_runs.list(
                status=OrchestrationRunStatus.WAITING,
            )
        for run in waiting_runs:
            try:
                continued = self.continue_recovery_contract(run.id)
            except Exception:
                logger.exception(
                    "failed to continue stalled recovery contract",
                    extra={"run_id": run.id},
                )
                continue
            if continued.status is not run.status or continued.stage is not run.stage:
                recovered[continued.id] = continued
        return list(recovered.values())

    def handle_recovered_dispatch_task(
        self,
        *,
        orchestration_run_id: str,
        reason: str,
    ) -> OrchestrationRun | None:
        return self.lease_manager.handle_recovered_dispatch_task(
            orchestration_run_id=orchestration_run_id,
            reason=reason,
        )

    def handle_terminal_tool_run(self, tool_run_id: str) -> list[OrchestrationRun]:
        tool_resume = self._require_tool_resume()
        return tool_resume.handle_terminal_tool_run(tool_run_id)

    def reconcile_tool_waits(self, tool_run_ids: tuple[str, ...]) -> None:
        tool_resume = self._require_tool_resume()
        tool_resume.reconcile_tool_waits(tool_run_ids)

    def _require_tool_resume(self) -> OrchestrationToolResumeCoordinator:
        if self.tool_resume is None:
            raise RuntimeError("Orchestration engine is not configured.")
        return self.tool_resume
