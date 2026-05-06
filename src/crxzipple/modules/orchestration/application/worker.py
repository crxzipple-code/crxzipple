from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from threading import Event as StopEvent
from typing import TYPE_CHECKING, Awaitable, Callable

from crxzipple.core.logger import get_logger
from crxzipple.modules.events import EventsApplicationService
from crxzipple.modules.events.domain import EventTopicWatch
from crxzipple.modules.orchestration.application.lease_manager import (
    OrchestrationLeaseManager,
)
from crxzipple.modules.orchestration.domain.entities import (
    OrchestrationExecutorLease,
    OrchestrationRun,
)
from crxzipple.modules.orchestration.application.commands import (
    AdvanceAssignmentInput,
    CompleteAssignmentInput,
    FailAssignmentInput,
    WaitAssignmentOnToolInput,
)
from crxzipple.modules.orchestration.domain.value_objects import (
    OrchestrationExecutorLeaseStatus,
    OrchestrationRunStage,
)
from crxzipple.modules.orchestration.domain.exceptions import (
    OrchestrationValidationError,
)
from crxzipple.shared.domain.events import named_event_topic
from crxzipple.shared.infrastructure.database_errors import (
    is_transient_database_lock_error,
)
from crxzipple.shared.runtime_metrics import (
    RuntimeMetricsRegistry,
    get_runtime_metrics_registry,
)

logger = get_logger(__name__)

if TYPE_CHECKING:
    from crxzipple.modules.orchestration.application.unit_of_work import (
        OrchestrationUnitOfWork,
    )

ORCHESTRATION_EXECUTOR_ASSIGNMENT_REQUESTED_EVENT = (
    "orchestration.executor.assignment.requested"
)


def orchestration_executor_assignment_requested_topic() -> str:
    return named_event_topic(ORCHESTRATION_EXECUTOR_ASSIGNMENT_REQUESTED_EVENT)


@dataclass(slots=True)
class OrchestrationExecutorService:
    """Execution-side helpers for orchestration executor workers."""

    uow_factory: Callable[[], "OrchestrationUnitOfWork"]
    events_service: EventsApplicationService | None
    worker_lease_seconds: int
    lease_manager: OrchestrationLeaseManager
    admit_assignment_fn: Callable[..., OrchestrationRun]
    advance_once_fn: Callable[..., OrchestrationRun]
    next_assigned_assignment_fn: Callable[..., OrchestrationRun | None]
    process_assigned_assignment_fn: Callable[..., OrchestrationRun]
    process_assigned_assignment_async_fn: Callable[..., Awaitable[OrchestrationRun]]
    process_next_assigned_assignment_fn: Callable[..., OrchestrationRun | None]
    heartbeat_assignment_fn: Callable[..., OrchestrationRun]
    advance_assignment_fn: Callable[[AdvanceAssignmentInput], OrchestrationRun]
    wait_assignment_on_tool_fn: Callable[[WaitAssignmentOnToolInput], OrchestrationRun]
    complete_assignment_fn: Callable[[CompleteAssignmentInput], OrchestrationRun]
    fail_assignment_fn: Callable[[FailAssignmentInput], OrchestrationRun]
    metrics: RuntimeMetricsRegistry = field(
        default_factory=get_runtime_metrics_registry,
    )

    def process_next_available(
        self,
        *,
        worker_id: str,
        exclude_run_ids: tuple[str, ...] = (),
    ) -> OrchestrationRun | None:
        return self.process_next_assigned_assignment(
            worker_id=worker_id,
            exclude_run_ids=exclude_run_ids,
        )

    def heartbeat_executor(
        self,
        *,
        worker_id: str,
        max_inflight_assignments: int | None = None,
        inflight_assignment_count: int | None = None,
        draining: bool | None = None,
        metadata: dict[str, object] | None = None,
    ) -> OrchestrationExecutorLease:
        with self.uow_factory() as uow:
            lease = uow.orchestration_executor_leases.get(worker_id)
            if lease is None:
                lease = OrchestrationExecutorLease.register(
                    worker_id=worker_id,
                    max_inflight_assignments=max_inflight_assignments or 1,
                    inflight_assignment_count=inflight_assignment_count or 0,
                    draining=bool(draining),
                    metadata=metadata,
                    lease_seconds=self.worker_lease_seconds,
                )
                uow.orchestration_executor_leases.add(lease)
                uow.collect(lease)
            else:
                lease = uow.orchestration_executor_leases.heartbeat(
                    worker_id=worker_id,
                    max_inflight_assignments=max_inflight_assignments,
                    inflight_assignment_count=inflight_assignment_count,
                    draining=draining,
                    metadata=metadata,
                    lease_seconds=self.worker_lease_seconds,
                )
                if lease is None:
                    lease = OrchestrationExecutorLease.register(
                        worker_id=worker_id,
                        max_inflight_assignments=max_inflight_assignments or 1,
                        inflight_assignment_count=inflight_assignment_count or 0,
                        draining=bool(draining),
                        metadata=metadata,
                        lease_seconds=self.worker_lease_seconds,
                    )
                    uow.orchestration_executor_leases.add(lease)
                    uow.collect(lease)
                else:
                    lease.heartbeat(
                        max_inflight_assignments=max_inflight_assignments,
                        inflight_assignment_count=inflight_assignment_count,
                        draining=draining,
                        metadata=metadata,
                        lease_seconds=self.worker_lease_seconds,
                        happened_at=lease.last_heartbeat_at,
                    )
                    uow.collect(lease)
            uow.commit()
            return lease

    def list_executor_leases(
        self,
        *,
        status: OrchestrationExecutorLeaseStatus | None = None,
    ) -> list[OrchestrationExecutorLease]:
        with self.uow_factory() as uow:
            return uow.orchestration_executor_leases.list(status=status)

    def runtime_metrics_snapshot(self) -> dict[str, object]:
        return self.metrics.snapshot(
            prefixes=(
                "llm.profile_limiter.",
                "orchestration.",
                "tool.remote_provider_limiter.",
                "tool.service.",
            ),
        )

    def build_wait_watches(self) -> tuple[EventTopicWatch, ...]:
        if self.events_service is None:
            return ()
        wakeup_topic = orchestration_executor_assignment_requested_topic()
        return (
            EventTopicWatch(
                topic=wakeup_topic,
                after_cursor=self.events_service.snapshot_event_topic(
                    wakeup_topic,
                ),
            ),
        )

    def admit_assignment(
        self,
        *,
        run_id: str,
        worker_id: str,
        acquire_lane_lock: bool = True,
    ) -> OrchestrationRun:
        return self.admit_assignment_fn(
            run_id=run_id,
            worker_id=worker_id,
            acquire_lane_lock=acquire_lane_lock,
        )

    def process_assignment_inline(
        self,
        *,
        run_id: str,
        worker_id: str,
        acquire_lane_lock: bool = True,
    ) -> OrchestrationRun:
        claimed = self.admit_assignment(
            run_id=run_id,
            worker_id=worker_id,
            acquire_lane_lock=acquire_lane_lock,
        )
        with self.lease_manager.heartbeat_while_processing(
            run_id=claimed.id,
            worker_id=worker_id,
            heartbeat_assignment=self.heartbeat_assignment,
        ):
            return self.advance_once(
                run_id=claimed.id,
                worker_id=worker_id,
            )

    def next_assigned_assignment(
        self,
        *,
        worker_id: str,
        exclude_run_ids: tuple[str, ...] = (),
    ) -> OrchestrationRun | None:
        return self.next_assigned_assignment_fn(
            worker_id=worker_id,
            exclude_run_ids=exclude_run_ids,
        )

    def process_assigned_assignment(
        self,
        *,
        run_id: str,
        worker_id: str,
    ) -> OrchestrationRun:
        return self.process_assigned_assignment_fn(
            run_id=run_id,
            worker_id=worker_id,
        )

    async def process_assigned_assignment_async(
        self,
        *,
        run_id: str,
        worker_id: str,
    ) -> OrchestrationRun:
        return await self.process_assigned_assignment_async_fn(
            run_id=run_id,
            worker_id=worker_id,
        )

    def process_next_assigned_assignment(
        self,
        *,
        worker_id: str,
        exclude_run_ids: tuple[str, ...] = (),
    ) -> OrchestrationRun | None:
        return self.process_next_assigned_assignment_fn(
            worker_id=worker_id,
            exclude_run_ids=exclude_run_ids,
        )

    def wait_for_work(
        self,
        *,
        timeout_seconds: float,
        stop_event: StopEvent,
    ) -> None:
        watches = self.build_wait_watches()
        if self.events_service is None or not watches:
            stop_event.wait(timeout_seconds)
            return
        self.events_service.wait_for_event_topics(
            watches,
            timeout_seconds=timeout_seconds,
            stop_event=stop_event,
        )

    def run_until_stopped(
        self,
        *,
        worker_id: str,
        poll_interval_seconds: float,
        max_runs: int | None = None,
        max_idle_cycles: int | None = None,
        stop_event: StopEvent | None = None,
        max_concurrent_assignments: int = 1,
    ) -> int:
        if max_concurrent_assignments <= 0:
            raise OrchestrationValidationError(
                "Orchestration executor max_concurrent_assignments must be positive.",
            )
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(
                self.run_until_stopped_async(
                    worker_id=worker_id,
                    poll_interval_seconds=poll_interval_seconds,
                    max_runs=max_runs,
                    max_idle_cycles=max_idle_cycles,
                    stop_event=stop_event,
                    max_concurrent_assignments=max_concurrent_assignments,
                ),
            )
        raise OrchestrationValidationError(
            "run_until_stopped cannot be called from an active asyncio loop; "
            "use run_until_stopped_async instead.",
        )

    async def run_until_stopped_async(
        self,
        *,
        worker_id: str,
        poll_interval_seconds: float,
        max_runs: int | None = None,
        max_idle_cycles: int | None = None,
        stop_event: StopEvent | None = None,
        max_concurrent_assignments: int = 1,
    ) -> int:
        if max_concurrent_assignments <= 0:
            raise OrchestrationValidationError(
                "Orchestration executor max_concurrent_assignments must be positive.",
            )
        return await self._run_async_until_stopped(
            worker_id=worker_id,
            poll_interval_seconds=poll_interval_seconds,
            max_runs=max_runs,
            max_idle_cycles=max_idle_cycles,
            stop_event=stop_event,
            max_concurrent_assignments=max_concurrent_assignments,
        )

    async def _run_async_until_stopped(
        self,
        *,
        worker_id: str,
        poll_interval_seconds: float,
        max_runs: int | None,
        max_idle_cycles: int | None,
        stop_event: StopEvent | None,
        max_concurrent_assignments: int,
    ) -> int:
        processed_runs = 0
        idle_cycles = 0
        stopper = stop_event or StopEvent()
        active: dict[asyncio.Task[OrchestrationRun], str] = {}

        async def _heartbeat() -> None:
            self._set_executor_runtime_gauges(
                worker_id=worker_id,
                active_assignment_count=len(active),
                max_concurrent_assignments=max_concurrent_assignments,
            )
            try:
                await asyncio.to_thread(
                    self.heartbeat_executor,
                    worker_id=worker_id,
                    max_inflight_assignments=max_concurrent_assignments,
                    # Lease inflight capacity is owned by scheduler assignment claims and
                    # released when a run completes/waits/fails; active tasks are reported
                    # in metadata and metrics without overwriting that capacity counter.
                    inflight_assignment_count=None,
                    draining=False,
                    metadata=self._runtime_heartbeat_metadata(
                        worker_id=worker_id,
                        active_run_ids=tuple(active.values()),
                        max_concurrent_assignments=max_concurrent_assignments,
                    ),
                )
            except Exception as exc:
                if not is_transient_database_lock_error(exc):
                    raise
                logger.warning(
                    "transient database lock while heartbeating orchestration executor; will retry",
                    extra={"worker_id": worker_id, "active_run_ids": tuple(active.values())},
                )

        async def _next_assigned(
            exclude_run_ids: tuple[str, ...],
        ) -> OrchestrationRun | None:
            return await asyncio.to_thread(
                self.next_assigned_assignment,
                worker_id=worker_id,
                exclude_run_ids=exclude_run_ids,
            )

        async def _process_assigned(run_id: str) -> OrchestrationRun:
            labels = {"worker_id": worker_id}
            with self.metrics.active(
                "orchestration.executor.assignment_tasks",
                labels=labels,
            ):
                with self.metrics.timed(
                    "orchestration.executor.assignment_seconds",
                    labels=labels,
                ):
                    try:
                        run = await self.process_assigned_assignment_async(
                            run_id=run_id,
                            worker_id=worker_id,
                        )
                    except Exception:
                        self.metrics.increment_counter(
                            "orchestration.executor.assignment_failures",
                            labels=labels,
                        )
                        raise
                    self.metrics.increment_counter(
                        "orchestration.executor.assignment_completions",
                        labels=labels,
                    )
                    return run

        async def _wait_for_work() -> None:
            await asyncio.to_thread(
                self.wait_for_work,
                timeout_seconds=poll_interval_seconds,
                stop_event=stopper,
            )

        async def _collect_finished(
            *,
            timeout_seconds: float | None = None,
        ) -> int:
            nonlocal processed_runs
            if not active:
                return 0
            if timeout_seconds is None or timeout_seconds <= 0:
                finished = {task for task in active if task.done()}
            else:
                finished, _ = await asyncio.wait(
                    tuple(active),
                    timeout=timeout_seconds,
                    return_when=asyncio.FIRST_COMPLETED,
                )
            completed = 0
            for task in finished:
                run_id = active.pop(task)
                run = task.result()
                completed += 1
                logger.info(
                    "orchestration executor processed assignment",
                    extra={
                        "run_id": run.id if run is not None else run_id,
                        "processed_runs": processed_runs + completed,
                        "worker_id": worker_id,
                    },
                )
            return completed

        logger.info(
            "orchestration executor async runtime started",
            extra={
                "poll_interval_seconds": poll_interval_seconds,
                "max_runs": max_runs,
                "max_idle_cycles": max_idle_cycles,
                "worker_id": worker_id,
                "max_concurrent_assignments": max_concurrent_assignments,
            },
        )
        await _heartbeat()

        try:
            while not stopper.is_set():
                self._set_executor_runtime_gauges(
                    worker_id=worker_id,
                    active_assignment_count=len(active),
                    max_concurrent_assignments=max_concurrent_assignments,
                )
                processed_runs += await _collect_finished()
                if max_runs is not None and processed_runs >= max_runs:
                    logger.info(
                        "orchestration executor exiting after processed run limit",
                        extra={
                            "processed_runs": processed_runs,
                            "worker_id": worker_id,
                        },
                    )
                    break

                started = False
                while len(active) < max_concurrent_assignments:
                    if max_runs is not None and (
                        processed_runs + len(active) >= max_runs
                    ):
                        break
                    run = await _next_assigned(tuple(active.values()))
                    if run is None:
                        break
                    active[
                        asyncio.create_task(
                            _process_assigned(run.id),
                            name=f"orchestration-assignment:{run.id}",
                        )
                    ] = run.id
                    started = True
                    self._set_executor_runtime_gauges(
                        worker_id=worker_id,
                        active_assignment_count=len(active),
                        max_concurrent_assignments=max_concurrent_assignments,
                    )

                if started:
                    idle_cycles = 0
                    continue

                await _heartbeat()

                if active:
                    processed_runs += await _collect_finished(
                        timeout_seconds=poll_interval_seconds,
                    )
                    continue

                idle_cycles += 1
                if max_idle_cycles is not None and idle_cycles >= max_idle_cycles:
                    logger.info(
                        "orchestration executor exiting after idle limit",
                        extra={
                            "idle_cycles": idle_cycles,
                            "worker_id": worker_id,
                        },
                    )
                    break
                await _wait_for_work()
        finally:
            if active:
                finished, _ = await asyncio.wait(tuple(active))
                for task in finished:
                    run_id = active.pop(task)
                    if task.cancelled():
                        continue
                    run = task.result()
                    processed_runs += 1
                    logger.info(
                        "orchestration executor processed assignment during shutdown",
                        extra={
                            "run_id": run.id if run is not None else run_id,
                            "processed_runs": processed_runs,
                            "worker_id": worker_id,
                        },
                    )
            self._set_executor_runtime_gauges(
                worker_id=worker_id,
                active_assignment_count=0,
                max_concurrent_assignments=max_concurrent_assignments,
            )
            await _heartbeat()

        return processed_runs

    def _set_executor_runtime_gauges(
        self,
        *,
        worker_id: str,
        active_assignment_count: int,
        max_concurrent_assignments: int,
    ) -> None:
        labels = {"worker_id": worker_id}
        self.metrics.set_gauge(
            "orchestration.executor.active_assignments",
            active_assignment_count,
            labels=labels,
        )
        self.metrics.set_gauge(
            "orchestration.executor.available_assignment_slots",
            max(max_concurrent_assignments - active_assignment_count, 0),
            labels=labels,
        )

    def _runtime_heartbeat_metadata(
        self,
        *,
        worker_id: str,
        active_run_ids: tuple[str, ...],
        max_concurrent_assignments: int,
    ) -> dict[str, object]:
        return {
            "runtime_metrics": self.runtime_metrics_snapshot(),
            "runtime_state": {
                "worker_id": worker_id,
                "active_run_ids": list(active_run_ids),
                "active_assignment_count": len(active_run_ids),
                "max_concurrent_assignments": max_concurrent_assignments,
            },
        }

    def heartbeat_assignment(
        self,
        *,
        run_id: str,
        worker_id: str,
    ) -> OrchestrationRun:
        return self.heartbeat_assignment_fn(run_id, worker_id=worker_id)

    def advance_once(
        self,
        *,
        run_id: str,
        worker_id: str,
    ) -> OrchestrationRun:
        return self.advance_once_fn(
            run_id=run_id,
            worker_id=worker_id,
        )

    def advance_assignment(
        self,
        *,
        run_id: str,
        worker_id: str,
        stage: OrchestrationRunStage,
        step_increment: int = 0,
        metadata: dict[str, object] | None = None,
    ) -> OrchestrationRun:
        return self.advance_assignment_fn(
            AdvanceAssignmentInput(
                run_id=run_id,
                worker_id=worker_id,
                stage=stage,
                step_increment=step_increment,
                metadata=metadata or {},
            ),
        )

    def wait_assignment_on_tool(
        self,
        *,
        run_id: str,
        worker_id: str,
        pending_tool_run_ids: tuple[str, ...],
        reason: str | None = None,
    ) -> OrchestrationRun:
        return self.wait_assignment_on_tool_fn(
            WaitAssignmentOnToolInput(
                run_id=run_id,
                worker_id=worker_id,
                pending_tool_run_ids=pending_tool_run_ids,
                reason=reason,
            ),
        )

    def complete_assignment(
        self,
        *,
        run_id: str,
        worker_id: str,
        result_payload: dict[str, object] | None = None,
    ) -> OrchestrationRun:
        return self.complete_assignment_fn(
            CompleteAssignmentInput(
                run_id=run_id,
                worker_id=worker_id,
                result_payload=result_payload or {},
            ),
        )

    def fail_assignment(
        self,
        *,
        run_id: str,
        message: str,
        code: str = "orchestration_failed",
        details: dict[str, object] | None = None,
        worker_id: str | None = None,
    ) -> OrchestrationRun:
        return self.fail_assignment_fn(
            FailAssignmentInput(
                run_id=run_id,
                message=message,
                code=code,
                details=details or {},
                worker_id=worker_id,
            ),
        )
