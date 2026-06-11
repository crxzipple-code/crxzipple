from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
import threading
from typing import Any, Callable, Protocol

from crxzipple.core.logger import get_logger
from crxzipple.modules.dispatch.domain import (
    DispatchPolicy,
    DispatchTask,
    DispatchTaskRepository,
    DispatchTaskStatus,
)
from crxzipple.modules.orchestration.application.assignment import (
    OrchestrationAssignmentSelector,
)
from crxzipple.modules.orchestration.application.dispatch_owner_kinds import (
    ORCHESTRATION_STEP_DISPATCH_OWNER_KIND,
)
from crxzipple.modules.orchestration.application.execution_chain_lifecycle import (
    current_dispatch_task_id,
    require_current_dispatch_task_id,
)
from crxzipple.modules.orchestration.application.ports import (
    OrchestrationDispatchPort,
)
from crxzipple.modules.orchestration.application.ports.database import (
    TransientDatabaseErrorClassifier,
    is_transient_database_lock_error,
)
from crxzipple.modules.orchestration.domain import (
    ExecutionChainRepository,
    ExecutionStepRepository,
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


class LeaseUnitOfWork(Protocol):
    execution_chains: ExecutionChainRepository
    execution_steps: ExecutionStepRepository
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
    dispatch_port: OrchestrationDispatchPort
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
            active_dispatch_lane_keys = {
                task.lane_key
                for status in (DispatchTaskStatus.CLAIMED, DispatchTaskStatus.WAITING)
                for task in uow.dispatch_tasks.list(status=status)
                if task.lane_key is not None
            }
            candidate_tasks = _runnable_dispatch_tasks(
                uow.dispatch_tasks.list(
                    status=DispatchTaskStatus.QUEUED,
                    owner_kind=ORCHESTRATION_STEP_DISPATCH_OWNER_KIND,
                ),
                active_lane_keys=active_dispatch_lane_keys,
            )
            skipped_task_ids: set[str] = set()
            for lease in candidates:
                for task in candidate_tasks:
                    if task.id in skipped_task_ids:
                        continue
                    run = self._run_for_dispatch_task_id(uow, task.id)
                    if run is None:
                        skipped_task_ids.add(task.id)
                        continue
                    if run.status is not OrchestrationRunStatus.QUEUED:
                        skipped_task_ids.add(task.id)
                        continue
                    dispatch_task_id = current_dispatch_task_id(uow, run=run)
                    if dispatch_task_id != task.id:
                        skipped_task_ids.add(task.id)
                        continue
                    claim = self.dispatch_port.claim_queued(
                        uow.dispatch_tasks,
                        uow,
                        run,
                        dispatch_task_id=task.id,
                        worker_id=lease.worker_id,
                        lease_seconds=self.worker_lease_seconds,
                    )
                    if claim is None:
                        uow.rollback()
                        skipped_task_ids.add(task.id)
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
                    claimed_run = uow.orchestration_runs.claim_queued_for_assignment(
                        run_id=run.id,
                        worker_id=lease.worker_id,
                        claimed_at=claim.claimed_at,
                    )
                    if claimed_run is None:
                        uow.rollback()
                        skipped_task_ids.add(task.id)
                        continue
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
            dispatch_task_id = require_current_dispatch_task_id(uow, run=run)
            task = uow.dispatch_tasks.get(dispatch_task_id)
            if task is None:
                raise RuntimeError(
                    f"Dispatch task '{dispatch_task_id}' was not found for orchestration run.",
                )
            if task.status is not DispatchTaskStatus.QUEUED:
                raise RuntimeError(
                    f"Dispatch task '{dispatch_task_id}' is not queued for inline claim.",
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
                dispatch_task_id=require_current_dispatch_task_id(uow, run=run),
                worker_id=worker_id,
                lease_seconds=self.worker_lease_seconds,
            )
            uow.orchestration_runs.add(run)
            uow.collect(run)
            uow.commit()
            return run

    def recover_abandoned_runs(self) -> list[OrchestrationRun]:
        self.mark_expired_executor_leases_offline()
        recovered_dispatch_task_ids = self.dispatch_port.recover_abandoned_dispatch_task_ids(
            reason=DISPATCH_LEASE_EXPIRED_REASON,
        )
        if not recovered_dispatch_task_ids:
            return []
        with self.uow_factory() as uow:
            recovered_runs = []
            for dispatch_task_id in recovered_dispatch_task_ids:
                run = self._run_for_dispatch_task_id(uow, dispatch_task_id)
                if run is not None:
                    self._requeue_recovered_running_run(
                        uow,
                        run,
                        reason=DISPATCH_LEASE_EXPIRED_REASON,
                    )
                    recovered_runs.append(run)
            if recovered_runs:
                uow.commit()
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
        dispatch_task_id: str,
        reason: str,
    ) -> OrchestrationRun | None:
        with self.uow_factory() as uow:
            run = self._run_for_dispatch_task_id(uow, dispatch_task_id)
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
            self._requeue_recovered_running_run(
                uow,
                run,
                reason=reason,
            )
            uow.commit()
            return run

    @staticmethod
    def _run_for_dispatch_task_id(
        uow: LeaseUnitOfWork,
        dispatch_task_id: str,
    ) -> OrchestrationRun | None:
        step = uow.execution_steps.get(dispatch_task_id)
        if step is not None:
            return uow.orchestration_runs.get(step.turn_id)
        task = uow.dispatch_tasks.get(dispatch_task_id)
        if task is not None and isinstance(task.payload_ref, str) and task.payload_ref.strip():
            return uow.orchestration_runs.get(task.payload_ref.strip())
        return None

    @staticmethod
    def _requeue_recovered_running_run(
        uow: LeaseUnitOfWork,
        run: OrchestrationRun,
        *,
        reason: str,
    ) -> None:
        if run.status is not OrchestrationRunStatus.RUNNING:
            return
        dispatch_task_id = current_dispatch_task_id(uow, run=run)
        dispatch_task = (
            uow.dispatch_tasks.get(dispatch_task_id)
            if dispatch_task_id is not None
            else None
        )
        release_worker_id = run.worker_id
        run.recover_worker_lease(reason=reason)
        if release_worker_id is not None:
            uow.orchestration_executor_leases.release_assignment_capacity(
                worker_id=release_worker_id,
            )
        if (
            dispatch_task is not None
            and dispatch_task.status is DispatchTaskStatus.CLAIMED
        ):
            dispatch_task.recover_abandoned(reason=reason)
            uow.dispatch_tasks.add(dispatch_task)
            uow.collect(dispatch_task)
        uow.orchestration_runs.add(run)
        uow.collect(run)

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
    def _claim_token_for_worker(worker_id: str) -> str:
        return f"orchestration:{worker_id}"


def _runnable_dispatch_tasks(
    queued_tasks: list[DispatchTask],
    *,
    active_lane_keys: set[str],
) -> list[DispatchTask]:
    eligible_tasks = [
        task
        for task in queued_tasks
        if task.status is DispatchTaskStatus.QUEUED
        and (task.lane_key is None or task.lane_key not in active_lane_keys)
    ]
    lane_heads: dict[str, DispatchTask] = {}
    for task in sorted(eligible_tasks, key=_dispatch_lane_sort_key):
        lane_group = task.lane_key or task.id
        lane_heads.setdefault(lane_group, task)
    return sorted(lane_heads.values(), key=_dispatch_global_sort_key)


def _dispatch_lane_sort_key(task: DispatchTask) -> tuple[object, ...]:
    return (
        task.priority,
        _dispatch_lane_policy_rank(task.policy),
        task.queued_at or task.created_at,
        task.created_at,
        task.id,
    )


def _dispatch_global_sort_key(task: DispatchTask) -> tuple[object, ...]:
    return (
        task.priority,
        _dispatch_global_policy_rank(task.policy),
        task.queued_at or task.created_at,
        task.created_at,
        task.id,
    )


def _dispatch_lane_policy_rank(policy: DispatchPolicy) -> int:
    if policy is DispatchPolicy.RESUME_FIRST:
        return 0
    if policy in {DispatchPolicy.JUMP_QUEUE, DispatchPolicy.LANE_JUMP_QUEUE}:
        return 1
    return 2


def _dispatch_global_policy_rank(policy: DispatchPolicy) -> int:
    if policy is DispatchPolicy.RESUME_FIRST:
        return 0
    if policy is DispatchPolicy.JUMP_QUEUE:
        return 1
    return 2
