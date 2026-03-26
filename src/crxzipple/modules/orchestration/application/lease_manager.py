from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import threading
from typing import Any, Callable, Protocol

from crxzipple.core.logger import get_logger
from crxzipple.modules.dispatch.domain import DispatchTaskRepository
from crxzipple.modules.orchestration.application.ports import (
    RunDispatchPort,
)
from crxzipple.modules.orchestration.domain import (
    OrchestrationRun,
    OrchestrationRunRepository,
    OrchestrationRunStatus,
)
from crxzipple.shared.domain.aggregates import AggregateRoot


logger = get_logger(__name__)

DISPATCH_LEASE_EXPIRED_REASON = "Orchestration worker lease expired before completion."
DISPATCH_LEASE_EXHAUSTED_REASON = (
    "Orchestration worker lease expired before completion and the run was failed for safety."
)


class LeaseUnitOfWork(Protocol):
    orchestration_runs: OrchestrationRunRepository
    dispatch_tasks: DispatchTaskRepository

    def __enter__(self) -> "LeaseUnitOfWork":
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
class OrchestrationLeaseManager:
    uow_factory: Callable[[], LeaseUnitOfWork]
    dispatch_port: RunDispatchPort
    worker_lease_seconds: int
    worker_heartbeat_seconds: float

    def claim_next_queued_run(
        self,
        *,
        worker_id: str,
        get_run: Callable[[LeaseUnitOfWork, str], OrchestrationRun],
    ) -> OrchestrationRun | None:
        self.recover_abandoned_runs()
        with self.uow_factory() as uow:
            claim = self.dispatch_port.claim_next_queued(
                uow.dispatch_tasks,
                uow,
                worker_id=worker_id,
                lease_seconds=self.worker_lease_seconds,
            )
            if claim is None:
                return None
            run = get_run(uow, claim.run_id)
            run.claim(worker_id=worker_id, claimed_at=claim.claimed_at)
            uow.orchestration_runs.add(run)
            uow.collect(run)
            uow.commit()
            return run

    def heartbeat_run(
        self,
        run_id: str,
        *,
        worker_id: str,
        get_run: Callable[[LeaseUnitOfWork, str], OrchestrationRun],
    ) -> OrchestrationRun:
        with self.uow_factory() as uow:
            run = get_run(uow, run_id)
            if run.status is not OrchestrationRunStatus.RUNNING:
                return run
            if run.worker_id != worker_id:
                logger.warning(
                    "skipping heartbeat for orchestration run owned by another worker",
                    extra={
                        "run_id": run.id,
                        "expected_worker_id": worker_id,
                        "actual_worker_id": run.worker_id,
                    },
                )
                return run
            run.heartbeat(worker_id=worker_id)
            self.dispatch_port.heartbeat(
                uow.dispatch_tasks,
                uow,
                run,
                worker_id=worker_id,
                lease_seconds=self.worker_lease_seconds,
            )
            uow.orchestration_runs.add(run)
            uow.collect(run)
            uow.commit()
            return run

    def recover_abandoned_runs(self) -> list[OrchestrationRun]:
        recovered_ids = self.dispatch_port.recover_abandoned_run_ids(
            reason=DISPATCH_LEASE_EXPIRED_REASON,
        )
        if not recovered_ids:
            return []
        with self.uow_factory() as uow:
            recovered_runs = []
            for run_id in recovered_ids:
                run = uow.orchestration_runs.get(run_id)
                if run is not None:
                    recovered_runs.append(run)
            return recovered_runs

    def handle_recovered_dispatch_task(
        self,
        *,
        orchestration_run_id: str,
        reason: str,
    ) -> OrchestrationRun | None:
        with self.uow_factory() as uow:
            run = uow.orchestration_runs.get(orchestration_run_id)
            if run is None:
                return None
            if run.status in {
                OrchestrationRunStatus.COMPLETED,
                OrchestrationRunStatus.FAILED,
                OrchestrationRunStatus.CANCELLED,
                OrchestrationRunStatus.QUEUED,
                OrchestrationRunStatus.WAITING,
                OrchestrationRunStatus.ACCEPTED,
            }:
                return run
            run.fail(
                worker_id=None,
                message=self.lease_exhausted_reason(reason),
                code="worker_lease_expired",
                details={"reason": reason},
            )
            self.dispatch_port.fail(uow.dispatch_tasks, uow, run)
            uow.orchestration_runs.add(run)
            uow.collect(run)
            uow.commit()
            return run

    @contextmanager
    def heartbeat_while_processing(
        self,
        *,
        run_id: str,
        worker_id: str,
        heartbeat_run: Callable[[str, str], OrchestrationRun],
    ) -> Any:
        if self.worker_heartbeat_seconds <= 0:
            yield
            return
        stop_event = threading.Event()

        def _run_heartbeat_loop() -> None:
            while not stop_event.wait(self.worker_heartbeat_seconds):
                try:
                    run = heartbeat_run(run_id, worker_id)
                except Exception:
                    logger.exception(
                        "failed to heartbeat orchestration run while processing",
                        extra={"run_id": run_id, "worker_id": worker_id},
                    )
                    return
                if run.status is not OrchestrationRunStatus.RUNNING:
                    return

        heartbeat_thread = threading.Thread(
            target=_run_heartbeat_loop,
            name=f"orchestration-heartbeat-{run_id[:8]}",
            daemon=True,
        )
        heartbeat_thread.start()
        try:
            yield
        finally:
            stop_event.set()
            heartbeat_thread.join(timeout=max(self.worker_heartbeat_seconds * 2, 0.2))

    @staticmethod
    def lease_exhausted_reason(reason: str) -> str:
        normalized = reason.strip()
        if normalized == DISPATCH_LEASE_EXPIRED_REASON:
            return DISPATCH_LEASE_EXHAUSTED_REASON
        return f"{normalized} (run failed after dispatch recovery)"
