from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
import threading
from typing import Any, Callable, Protocol

from crxzipple.core.logger import get_logger
from crxzipple.modules.dispatch.domain import DispatchTaskRepository, DispatchTaskStatus
from crxzipple.modules.orchestration.application.assignment import (
    OrchestrationAssignmentSelector,
)
from crxzipple.modules.orchestration.application.ports import (
    RunDispatchPort,
)
from crxzipple.modules.orchestration.application.ports.database import (
    TransientDatabaseErrorClassifier,
    is_transient_database_lock_error,
)
from crxzipple.modules.orchestration.domain import (
    OrchestrationExecutorLease,
    OrchestrationExecutorLeaseStatus,
    OrchestrationExecutorLeaseRepository,
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
    orchestration_executor_leases: OrchestrationExecutorLeaseRepository
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

    def rollback(self) -> None:
        ...


@dataclass(slots=True)
class OrchestrationLeaseManager:
    uow_factory: Callable[[], LeaseUnitOfWork]
    dispatch_port: RunDispatchPort
    worker_lease_seconds: int
    worker_heartbeat_seconds: float
    assignment_selector: OrchestrationAssignmentSelector = field(
        default_factory=OrchestrationAssignmentSelector,
    )
    transient_database_error_classifier: TransientDatabaseErrorClassifier = (
        is_transient_database_lock_error
    )

    def assign_next_assignment(
        self,
    ) -> OrchestrationRun | None:
        self.recover_abandoned_runs()
        with self.uow_factory() as uow:
            candidates = self.assignment_selector.available_executors(
                uow.orchestration_executor_leases.list(status=None),
            )
            if not candidates:
                return None
            queued_runs = uow.orchestration_runs.list(
                status=OrchestrationRunStatus.QUEUED,
            )
            active_runs = [
                *uow.orchestration_runs.list(status=OrchestrationRunStatus.RUNNING),
                *uow.orchestration_runs.list(status=OrchestrationRunStatus.WAITING),
            ]
            skipped_run_ids: set[str] = set()
            for lease in candidates:
                while True:
                    run = self.assignment_selector.select_runnable_run(
                        queued_runs=[
                            item
                            for item in queued_runs
                            if item.id not in skipped_run_ids
                        ],
                        active_runs=active_runs,
                    )
                    if run is None:
                        return None
                    task = uow.dispatch_tasks.get(run.id)
                    if task is None or task.status is not DispatchTaskStatus.QUEUED:
                        skipped_run_ids.add(run.id)
                        continue
                    claimed_run = uow.orchestration_runs.claim_queued_for_assignment(
                        run_id=run.id,
                        worker_id=lease.worker_id,
                    )
                    if claimed_run is None:
                        skipped_run_ids.add(run.id)
                        continue
                    claim = self.dispatch_port.claim_queued(
                        uow.dispatch_tasks,
                        uow,
                        run,
                        worker_id=lease.worker_id,
                        lease_seconds=self.worker_lease_seconds,
                    )
                    if claim is None:
                        uow.rollback()
                        skipped_run_ids.add(run.id)
                        continue
                    capacity_lease = (
                        uow.orchestration_executor_leases.claim_assignment_capacity(
                            worker_id=lease.worker_id,
                            lease_seconds=self.worker_lease_seconds,
                        )
                    )
                    if capacity_lease is None:
                        uow.rollback()
                        break
                    claimed_run.claim(
                        worker_id=lease.worker_id,
                        claimed_at=claim.claimed_at,
                    )
                    uow.collect(capacity_lease)
                    uow.orchestration_runs.add(claimed_run)
                    uow.collect(claimed_run)
                    uow.commit()
                    return claimed_run
        return None

    def release_executor_assignment(self, *, worker_id: str) -> None:
        with self.uow_factory() as uow:
            uow.orchestration_executor_leases.release_assignment_capacity(
                worker_id=worker_id,
            )
            uow.commit()

    def admit_assignment(
        self,
        run_id: str,
        *,
        worker_id: str,
        get_run: Callable[[LeaseUnitOfWork, str], OrchestrationRun],
        acquire_lane_lock: bool = True,
    ) -> OrchestrationRun:
        with self.uow_factory() as uow:
            run = get_run(uow, run_id)
            if (
                run.status is OrchestrationRunStatus.RUNNING
                and run.worker_id == worker_id
            ):
                return run
            if run.status is not OrchestrationRunStatus.QUEUED:
                raise RuntimeError(
                    f"Orchestration run '{run_id}' is not queued for inline claim.",
                )
            task = uow.dispatch_tasks.get(run_id)
            if task is None:
                raise RuntimeError(
                    f"Dispatch task '{run_id}' was not found for orchestration run.",
                )
            if task.status is not DispatchTaskStatus.QUEUED:
                raise RuntimeError(
                    f"Dispatch task '{run_id}' is not queued for inline claim.",
                )
            task.claim(
                worker_id=worker_id,
                claim_token=self._claim_token_for_worker(worker_id),
                lease_seconds=self.worker_lease_seconds,
            )
            run.claim(
                worker_id=worker_id,
                claimed_at=task.claimed_at,
                acquire_lane_lock=acquire_lane_lock,
            )
            uow.dispatch_tasks.add(task)
            uow.collect(task)
            uow.orchestration_runs.add(run)
            uow.collect(run)
            uow.commit()
            return run

    def heartbeat_assignment(
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
        self.mark_expired_executor_leases_offline()
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

    def mark_expired_executor_leases_offline(self) -> list[OrchestrationExecutorLease]:
        with self.uow_factory() as uow:
            expired_leases = [
                lease
                for lease in uow.orchestration_executor_leases.list(
                    status=OrchestrationExecutorLeaseStatus.ONLINE,
                )
                if lease.is_expired()
            ]
            for lease in expired_leases:
                lease.mark_offline()
                uow.orchestration_executor_leases.add(lease)
                uow.collect(lease)
            if expired_leases:
                uow.commit()
            return expired_leases

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
            release_worker_id = (
                run.worker_id
                if run.status is OrchestrationRunStatus.RUNNING
                else None
            )
            run.fail(
                worker_id=None,
                message=self.lease_exhausted_reason(reason),
                code="worker_lease_expired",
                details={"reason": reason},
            )
            self.dispatch_port.fail(uow.dispatch_tasks, uow, run)
            if release_worker_id is not None:
                uow.orchestration_executor_leases.release_assignment_capacity(
                    worker_id=release_worker_id,
                )
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
        heartbeat_assignment: Callable[..., OrchestrationRun],
    ) -> Any:
        if self.worker_heartbeat_seconds <= 0:
            yield
            return
        stop_event = threading.Event()

        def _run_heartbeat_loop() -> None:
            while not stop_event.wait(self.worker_heartbeat_seconds):
                try:
                    run = heartbeat_assignment(
                        run_id=run_id,
                        worker_id=worker_id,
                    )
                except Exception as exc:
                    if self.transient_database_error_classifier(exc):
                        logger.warning(
                            "transient database lock while heartbeating orchestration run; will retry",
                            extra={"run_id": run_id, "worker_id": worker_id},
                        )
                        continue
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

    @staticmethod
    def _claim_token_for_worker(worker_id: str) -> str:
        return f"orchestration:{worker_id}"
