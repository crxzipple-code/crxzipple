from __future__ import annotations

import asyncio
from dataclasses import dataclass
from threading import Event as StopEvent
from typing import TYPE_CHECKING, Callable

from crxzipple.core.logger import get_logger
from crxzipple.modules.dispatch.application import dispatch_wakeup_topic
from crxzipple.modules.events.domain import EventTopicWatch
from crxzipple.modules.orchestration.application.dispatch_owner_kinds import (
    ORCHESTRATION_CONTINUATION_DISPATCH_OWNER_KIND,
    ORCHESTRATION_INGRESS_DISPATCH_OWNER_KIND,
    ORCHESTRATION_STEP_DISPATCH_OWNER_KIND,
)
from crxzipple.modules.orchestration.application.ingress_processing import (
    fail_assignment_input_from_ingress_error,
    process_ingress_request,
)
from crxzipple.modules.orchestration.application.ports import EventBusPort
from crxzipple.modules.orchestration.application.worker import (
    orchestration_executor_assignment_requested_topic,
)
from crxzipple.modules.orchestration.domain import (
    OrchestrationExecutorLease,
    OrchestrationIngressRequest,
    OrchestrationRun,
)
from crxzipple.modules.orchestration.domain.exceptions import (
    OrchestrationValidationError,
)
from crxzipple.shared.domain.events import Event, named_event_topic

if TYPE_CHECKING:
    from crxzipple.modules.orchestration.application.commands import (
        FailAssignmentInput,
        RequestCompactionInput,
        RequestDueHeartbeatsInput,
        RequestHeartbeatInput,
        RequestMemoryFlushInput,
        ResumeOrchestrationRunInput,
        SubmitBoundOrchestrationTurnInput,
        SubmitOrchestrationTurnInput,
    )
    from crxzipple.modules.orchestration.application.ports.runtime import (
        OrchestrationSchedulerIntakePort,
    )
    from crxzipple.modules.orchestration.application.runtime_events import (
        OrchestrationRuntimeEventService,
    )
    from crxzipple.modules.orchestration.application.coordinators.ingress import (
        RunIngressCoordinator,
    )
    from crxzipple.modules.orchestration.application.coordinators.continuation_tasks import (
        RunContinuationCoordinator,
    )
from crxzipple.modules.orchestration.application.coordinators.continuation_tasks import (
    OrchestrationContinuationKind,
    OrchestrationContinuationTask,
)

logger = get_logger(__name__)

ORCHESTRATION_INGRESS_REQUESTED_EVENT = "orchestration.ingress.requested"


def orchestration_ingress_requested_topic() -> str:
    return named_event_topic(ORCHESTRATION_INGRESS_REQUESTED_EVENT)


@dataclass(slots=True)
class OrchestrationSchedulerService:
    ingress_coordinator: "RunIngressCoordinator"
    intake_port: "OrchestrationSchedulerIntakePort"
    continuation_coordinator: "RunContinuationCoordinator"
    get_run_fn: Callable[[str], OrchestrationRun]
    assign_next_assignment_fn: Callable[[], OrchestrationRun | None]
    recover_abandoned_runs_fn: Callable[[], list[OrchestrationRun]]
    expire_executor_leases_fn: Callable[[], list[OrchestrationExecutorLease]]
    handle_recovered_dispatch_task_fn: Callable[..., OrchestrationRun | None]
    handle_terminal_tool_run_fn: Callable[[str], list[OrchestrationRun]]
    process_sessions_spawn_followup_fn: Callable[[str], OrchestrationRun | None]
    request_compaction_fn: Callable[["RequestCompactionInput"], OrchestrationRun]
    request_heartbeat_fn: Callable[["RequestHeartbeatInput"], OrchestrationRun]
    request_memory_flush_fn: Callable[["RequestMemoryFlushInput"], OrchestrationRun]
    request_due_heartbeats_fn: Callable[
        ["RequestDueHeartbeatsInput"],
        list[OrchestrationRun],
    ]
    resume_run_fn: Callable[["ResumeOrchestrationRunInput"], OrchestrationRun]
    fail_assignment_fn: Callable[["FailAssignmentInput"], OrchestrationRun]
    events_service: EventBusPort | None = None
    on_run_enqueued: Callable[[OrchestrationRun], None] | None = None
    runtime_event_service: "OrchestrationRuntimeEventService | None" = None

    def submit_turn(
        self,
        data: "SubmitOrchestrationTurnInput",
        *,
        inline_worker_id: str | None = None,
    ) -> OrchestrationRun:
        run = self.ingress_coordinator.submit_turn(data)
        if inline_worker_id is None:
            return run
        processed = self.process_run_request(
            run_id=run.id,
            worker_id=inline_worker_id,
        )
        return processed or self.get_run_fn(run.id)

    def submit_bound_turn(
        self,
        data: "SubmitBoundOrchestrationTurnInput",
        *,
        inline_worker_id: str | None = None,
    ) -> OrchestrationRun:
        run = self.ingress_coordinator.submit_bound_turn(data)
        if inline_worker_id is None:
            return run
        processed = self.process_run_request(
            run_id=run.id,
            worker_id=inline_worker_id,
        )
        return processed or self.get_run_fn(run.id)

    def process_next_request(
        self,
        *,
        worker_id: str,
    ) -> OrchestrationRun | None:
        return self._process_request(
            self.ingress_coordinator.claim_next_dispatch_request(worker_id=worker_id),
            worker_id=worker_id,
        )

    def process_next_available(
        self,
        *,
        worker_id: str,
    ) -> tuple[OrchestrationRun | None, OrchestrationContinuationTask | None]:
        run = self.process_next_request(worker_id=worker_id)
        if run is not None:
            return run, None
        self.process_runtime_events()
        continuation = self.process_next_continuation(worker_id=worker_id)
        if continuation is not None:
            return None, continuation
        return self.assign_next_assignment(), None

    def process_runtime_events(self, *, limit_per_subscription: int = 100) -> int:
        if self.runtime_event_service is None:
            return 0
        return self.runtime_event_service.process_available_events(
            limit_per_subscription=limit_per_subscription,
        )

    def build_wait_watches(self) -> tuple[EventTopicWatch, ...]:
        if self.events_service is None:
            return ()
        run_wakeup_topic = dispatch_wakeup_topic(ORCHESTRATION_STEP_DISPATCH_OWNER_KIND)
        ingress_wakeup_topic = dispatch_wakeup_topic(
            ORCHESTRATION_INGRESS_DISPATCH_OWNER_KIND,
        )
        continuation_wakeup_topic = dispatch_wakeup_topic(
            ORCHESTRATION_CONTINUATION_DISPATCH_OWNER_KIND,
        )
        watches = [
            EventTopicWatch(
                topic=orchestration_ingress_requested_topic(),
                after_cursor=self.events_service.snapshot_event_topic(
                    orchestration_ingress_requested_topic(),
                ),
            ),
            EventTopicWatch(
                topic=ingress_wakeup_topic,
                after_cursor=self.events_service.snapshot_event_topic(
                    ingress_wakeup_topic,
                ),
            ),
            EventTopicWatch(
                topic=run_wakeup_topic,
                after_cursor=self.events_service.snapshot_event_topic(
                    run_wakeup_topic,
                ),
            ),
            EventTopicWatch(
                topic=continuation_wakeup_topic,
                after_cursor=self.events_service.snapshot_event_topic(
                    continuation_wakeup_topic,
                ),
            ),
        ]
        if self.runtime_event_service is not None:
            watches.extend(self.runtime_event_service.build_wait_watches())
        return tuple(watches)

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
    ) -> int:
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
    ) -> int:
        processed_runs = 0
        idle_cycles = 0
        stopper = stop_event or StopEvent()

        logger.info(
            "orchestration scheduler started",
            extra={
                "poll_interval_seconds": poll_interval_seconds,
                "max_runs": max_runs,
                "max_idle_cycles": max_idle_cycles,
                "worker_id": worker_id,
            },
        )

        while not stopper.is_set():
            run, continuation = await asyncio.to_thread(
                self.process_next_available,
                worker_id=worker_id,
            )
            if run is None and continuation is None:
                idle_cycles += 1
                if max_idle_cycles is not None and idle_cycles >= max_idle_cycles:
                    logger.info(
                        "orchestration scheduler exiting after idle limit",
                        extra={
                            "idle_cycles": idle_cycles,
                            "worker_id": worker_id,
                        },
                    )
                    break
                await asyncio.to_thread(
                    self.wait_for_work,
                    timeout_seconds=poll_interval_seconds,
                    stop_event=stopper,
                )
                continue

            idle_cycles = 0
            processed_runs += 1
            extra = {
                "processed_runs": processed_runs,
                "worker_id": worker_id,
            }
            if run is not None:
                extra["run_id"] = run.id
            if continuation is not None:
                extra["continuation_id"] = continuation.id
                extra["continuation_kind"] = continuation.continuation_kind.value
            logger.info(
                "orchestration scheduler processed work item",
                extra=extra,
            )
            if max_runs is not None and processed_runs >= max_runs:
                logger.info(
                    "orchestration scheduler exiting after processed run limit",
                    extra={
                        "processed_runs": processed_runs,
                        "worker_id": worker_id,
                    },
                )
                break

        return processed_runs

    def process_run_request(
        self,
        *,
        run_id: str,
        worker_id: str,
    ) -> OrchestrationRun | None:
        return self._process_request(
            self.ingress_coordinator.claim_dispatch_request_for_run(
                run_id=run_id,
                worker_id=worker_id,
            ),
            worker_id=worker_id,
        )

    def queue_tool_terminal_continuation(
        self,
        *,
        tool_run_id: str,
    ) -> OrchestrationContinuationTask:
        return self.continuation_coordinator.queue_tool_terminal_continuation(
            tool_run_id=tool_run_id,
        )

    def queue_sessions_spawn_followup_continuation(
        self,
        *,
        child_run_id: str,
    ) -> OrchestrationContinuationTask:
        return self.continuation_coordinator.queue_sessions_spawn_followup_continuation(
            child_run_id=child_run_id,
        )

    def process_next_continuation(
        self,
        *,
        worker_id: str,
    ) -> OrchestrationContinuationTask | None:
        return self._process_continuation(
            self.continuation_coordinator.claim_next_continuation(
                worker_id=worker_id,
            ),
        )

    def recover_abandoned_runs(self) -> list[OrchestrationRun]:
        return self.recover_abandoned_runs_fn()

    def expire_executor_leases(self) -> list[OrchestrationExecutorLease]:
        return self.expire_executor_leases_fn()

    def assign_next_assignment(self) -> OrchestrationRun | None:
        run = self.assign_next_assignment_fn()
        if run is not None:
            self._publish_executor_assignment(run)
        return run

    def handle_recovered_dispatch_task(
        self,
        *,
        dispatch_task_id: str,
        reason: str,
    ) -> OrchestrationRun | None:
        return self.handle_recovered_dispatch_task_fn(
            dispatch_task_id=dispatch_task_id,
            reason=reason,
        )

    def handle_terminal_tool_run(self, tool_run_id: str) -> list[OrchestrationRun]:
        return self.handle_terminal_tool_run_fn(tool_run_id)

    def process_sessions_spawn_followup(
        self,
        child_run_id: str,
    ) -> OrchestrationRun | None:
        return self.process_sessions_spawn_followup_fn(child_run_id)

    def request_compaction(
        self,
        data: "RequestCompactionInput",
    ) -> OrchestrationRun:
        return self.request_compaction_fn(data)

    def request_heartbeat(
        self,
        data: "RequestHeartbeatInput",
    ) -> OrchestrationRun:
        return self.request_heartbeat_fn(data)

    def request_memory_flush(
        self,
        data: "RequestMemoryFlushInput",
    ) -> OrchestrationRun:
        return self.request_memory_flush_fn(data)

    def request_due_heartbeats(
        self,
        data: "RequestDueHeartbeatsInput",
    ) -> list[OrchestrationRun]:
        return self.request_due_heartbeats_fn(data)

    def resume_run(self, data: "ResumeOrchestrationRunInput") -> OrchestrationRun:
        return self.resume_run_fn(data)

    def _process_request(
        self,
        request: OrchestrationIngressRequest | None,
        *,
        worker_id: str,
    ) -> OrchestrationRun | None:
        return process_ingress_request(
            request,
            worker_id=worker_id,
            ingress_coordinator=self.ingress_coordinator,
            intake_port=self.intake_port,
            fail_run=self._fail_ingress_backed_run,
            on_run_enqueued=self.on_run_enqueued,
        )

    def _fail_ingress_backed_run(
        self,
        request: OrchestrationIngressRequest,
        worker_id: str,
        exc: Exception,
    ) -> None:
        self.fail_assignment_fn(
            fail_assignment_input_from_ingress_error(
                request,
                worker_id=worker_id,
                exc=exc,
            ),
        )

    def _process_continuation(
        self,
        continuation: OrchestrationContinuationTask | None,
    ) -> OrchestrationContinuationTask | None:
        if continuation is None:
            return None
        try:
            if continuation.continuation_kind is OrchestrationContinuationKind.TOOL_TERMINAL:
                tool_run_id = str(continuation.payload.get("tool_run_id", "")).strip()
                if tool_run_id:
                    self.handle_terminal_tool_run(tool_run_id)
            elif continuation.continuation_kind is OrchestrationContinuationKind.SESSIONS_SPAWN_FOLLOWUP:
                child_run_id = str(continuation.payload.get("child_run_id", "")).strip()
                if child_run_id:
                    self.process_sessions_spawn_followup(child_run_id)
            return self.continuation_coordinator.complete_continuation(continuation.id)
        except Exception as exc:
            logger.exception(
                "orchestration continuation processing failed",
                extra={
                    "continuation_id": continuation.id,
                    "continuation_kind": continuation.continuation_kind.value,
                },
            )
            return self.continuation_coordinator.fail_continuation(
                continuation.id,
                message=str(exc) or type(exc).__name__,
                code="orchestration_continuation_failed",
                details={
                    "continuation_kind": continuation.continuation_kind.value,
                },
            )
        finally:
            if continuation is not None and continuation.status is not None:
                logger.debug(
                    "orchestration scheduler finished continuation processing attempt",
                    extra={
                        "continuation_id": continuation.id,
                        "continuation_kind": continuation.continuation_kind.value,
                    },
                )

    def _publish_executor_assignment(self, run: OrchestrationRun) -> None:
        if self.events_service is None:
            return
        self.events_service.publish(
            Event(
                topic=orchestration_executor_assignment_requested_topic(),
                kind="command",
                ordering_key=run.worker_id,
                payload={
                    "run_id": run.id,
                    "worker_id": run.worker_id,
                    "lane_key": run.lane_key,
                },
            ),
        )
