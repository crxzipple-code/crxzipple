from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Protocol

from crxzipple.modules.dispatch.domain import DispatchTaskRepository
from crxzipple.modules.orchestration.application.lease_manager import (
    OrchestrationLeaseManager,
)
from crxzipple.modules.orchestration.application.ports import RunDispatchPort
from crxzipple.modules.orchestration.domain import (
    OrchestrationRun,
    OrchestrationRunRepository,
    OrchestrationRunWaitRepository,
)
from crxzipple.modules.orchestration.domain.exceptions import (
    OrchestrationRunNotFoundError,
)
from crxzipple.shared.domain.aggregates import AggregateRoot

if TYPE_CHECKING:
    from crxzipple.modules.orchestration.application.services import (
        AdvanceOrchestrationRunInput,
        CompleteOrchestrationRunInput,
        FailOrchestrationRunInput,
    )


class ProgressCoordinatorUnitOfWork(Protocol):
    orchestration_runs: OrchestrationRunRepository
    orchestration_waits: OrchestrationRunWaitRepository
    dispatch_tasks: DispatchTaskRepository

    def __enter__(self) -> "ProgressCoordinatorUnitOfWork":
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


@dataclass(slots=True)
class RunProgressCoordinator:
    uow_factory: Callable[[], ProgressCoordinatorUnitOfWork]
    dispatch_port: RunDispatchPort
    lease_manager: OrchestrationLeaseManager
    claim_next_queued_run: Callable[[str], OrchestrationRun | None]
    advance_once: Callable[[str, str], OrchestrationRun]
    heartbeat_run: Callable[[str, str], OrchestrationRun]
    get_run: Callable[[str], OrchestrationRun]
    apply_compaction_summary: Callable[[OrchestrationRun], None]
    apply_memory_flush: Callable[[OrchestrationRun], None]
    extract_memory_candidate: Callable[[OrchestrationRun], None]
    maybe_request_auto_compaction: Callable[[OrchestrationRun], OrchestrationRun | None]
    clear_pending_compaction_marker: Callable[[OrchestrationRun], None]
    is_compaction_run: Callable[[OrchestrationRun], bool]

    def process_next_queued_run(self, *, worker_id: str) -> OrchestrationRun | None:
        run = self.claim_next_queued_run(worker_id)
        if run is None:
            return None
        with self.lease_manager.heartbeat_while_processing(
            run_id=run.id,
            worker_id=worker_id,
            heartbeat_run=self.heartbeat_run,
        ):
            return self.advance_once(run_id=run.id, worker_id=worker_id)

    def advance_run(self, data: "AdvanceOrchestrationRunInput") -> OrchestrationRun:
        with self.uow_factory() as uow:
            run = self._get_run(uow, data.run_id)
            run.advance(
                worker_id=data.worker_id,
                stage=data.stage,
                step_increment=data.step_increment,
                metadata=data.metadata,
                happened_at=data.now,
            )
            uow.orchestration_runs.add(run)
            uow.collect(run)
            uow.commit()
            return run

    def complete_run(self, data: "CompleteOrchestrationRunInput") -> OrchestrationRun:
        with self.uow_factory() as uow:
            run = self._get_run(uow, data.run_id)
            if data.metadata:
                run.metadata.update(data.metadata)
            run.complete(
                worker_id=data.worker_id,
                result_payload=data.result_payload,
                happened_at=data.now,
            )
            self.dispatch_port.complete(uow.dispatch_tasks, uow, run)
            uow.orchestration_waits.delete_for_run(run.id)
            uow.orchestration_runs.add(run)
            uow.collect(run)
            uow.commit()
        self.apply_compaction_summary(run)
        self.apply_memory_flush(run)
        self.extract_memory_candidate(run)
        self.maybe_request_auto_compaction(run)
        return self.get_run(data.run_id)

    def fail_run(self, data: "FailOrchestrationRunInput") -> OrchestrationRun:
        with self.uow_factory() as uow:
            run = self._get_run(uow, data.run_id)
            run.fail(
                worker_id=data.worker_id,
                message=data.message,
                code=data.code,
                details=data.details,
                happened_at=data.now,
            )
            self.dispatch_port.fail(uow.dispatch_tasks, uow, run)
            uow.orchestration_waits.delete_for_run(run.id)
            uow.orchestration_runs.add(run)
            uow.collect(run)
            uow.commit()
        if self.is_compaction_run(run):
            self.clear_pending_compaction_marker(run)
        return run

    def cancel_run(
        self,
        run_id: str,
        *,
        reason: str | None = None,
    ) -> OrchestrationRun:
        with self.uow_factory() as uow:
            run = self._get_run(uow, run_id)
            run.cancel(reason=reason)
            self.dispatch_port.cancel(uow.dispatch_tasks, uow, run)
            uow.orchestration_waits.delete_for_run(run.id)
            uow.orchestration_runs.add(run)
            uow.collect(run)
            uow.commit()
        if self.is_compaction_run(run):
            self.clear_pending_compaction_marker(run)
        return run

    @staticmethod
    def _get_run(
        uow: ProgressCoordinatorUnitOfWork,
        run_id: str,
    ) -> OrchestrationRun:
        run = uow.orchestration_runs.get(run_id)
        if run is None:
            raise OrchestrationRunNotFoundError(
                f"Orchestration run '{run_id}' was not found.",
            )
        return run
