from __future__ import annotations

import asyncio
from dataclasses import dataclass
from threading import Event as StopEvent
from typing import TYPE_CHECKING, Callable

from crxzipple.core.logger import get_logger
from crxzipple.modules.dispatch.application import dispatch_wakeup_topic
from crxzipple.modules.events import Event, EventsApplicationService
from crxzipple.modules.events.domain import EventTopicWatch
from crxzipple.modules.orchestration.application.lane import session_lane_key
from crxzipple.modules.orchestration.application.worker import (
    orchestration_executor_assignment_requested_topic,
)
from crxzipple.modules.orchestration.domain import (
    OrchestrationBoundSessionTarget,
    OrchestrationExecutorLease,
    OrchestrationIngressRequest,
    OrchestrationIngressRequestKind,
    OrchestrationRun,
    OrchestrationSchedulerSignal,
    OrchestrationSchedulerSignalKind,
)
from crxzipple.modules.orchestration.domain.exceptions import (
    OrchestrationValidationError,
)
from crxzipple.modules.session.domain import (
    DirectSessionScope,
    SessionResetPolicy,
    SessionRouteContext,
)
from crxzipple.shared.domain.events import named_event_topic

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
    from crxzipple.modules.orchestration.application.coordinators.scheduler_signals import (
        RunSchedulerSignalCoordinator,
    )

logger = get_logger(__name__)

ORCHESTRATION_INGRESS_REQUESTED_EVENT = "orchestration.ingress.requested"
ORCHESTRATION_SCHEDULER_SIGNAL_REQUESTED_EVENT = (
    "orchestration.scheduler.signal.requested"
)


def orchestration_ingress_requested_topic() -> str:
    return named_event_topic(ORCHESTRATION_INGRESS_REQUESTED_EVENT)


def orchestration_scheduler_signal_requested_topic() -> str:
    return named_event_topic(ORCHESTRATION_SCHEDULER_SIGNAL_REQUESTED_EVENT)


@dataclass(slots=True)
class OrchestrationSchedulerService:
    ingress_coordinator: "RunIngressCoordinator"
    intake_port: "OrchestrationSchedulerIntakePort"
    scheduler_signal_coordinator: "RunSchedulerSignalCoordinator"
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
    events_service: EventsApplicationService | None = None
    on_run_enqueued: Callable[[OrchestrationRun], None] | None = None
    runtime_event_service: "OrchestrationRuntimeEventService | None" = None

    def submit_turn(
        self,
        data: "SubmitOrchestrationTurnInput",
        *,
        inline_worker_id: str | None = None,
    ) -> OrchestrationRun:
        run = self.ingress_coordinator.submit_turn(
            data,
            claimed_worker_id=inline_worker_id,
        )
        if inline_worker_id is None:
            return run
        request = self.ingress_coordinator.get_request_for_run(run.id)
        if request is None:
            return self.get_run_fn(run.id)
        processed = self._process_request(
            request,
            worker_id=inline_worker_id,
        )
        return processed or self.get_run_fn(run.id)

    def submit_bound_turn(
        self,
        data: "SubmitBoundOrchestrationTurnInput",
        *,
        inline_worker_id: str | None = None,
    ) -> OrchestrationRun:
        run = self.ingress_coordinator.submit_bound_turn(
            data,
            claimed_worker_id=inline_worker_id,
        )
        if inline_worker_id is None:
            return run
        request = self.ingress_coordinator.get_request_for_run(run.id)
        if request is None:
            return self.get_run_fn(run.id)
        processed = self._process_request(
            request,
            worker_id=inline_worker_id,
        )
        return processed or self.get_run_fn(run.id)

    def process_next_request(
        self,
        *,
        worker_id: str,
    ) -> OrchestrationRun | None:
        return self._process_request(
            self.ingress_coordinator.claim_next_request(worker_id=worker_id),
            worker_id=worker_id,
        )

    def process_next_available(
        self,
        *,
        worker_id: str,
    ) -> tuple[OrchestrationRun | None, OrchestrationSchedulerSignal | None]:
        run = self.process_next_request(worker_id=worker_id)
        if run is not None:
            return run, None
        self.process_runtime_events()
        signal = self.process_next_signal(worker_id=worker_id)
        if signal is not None:
            return None, signal
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
        wakeup_topic = dispatch_wakeup_topic("orchestration_run")
        watches = [
            EventTopicWatch(
                topic=orchestration_ingress_requested_topic(),
                after_cursor=self.events_service.snapshot_event_topic(
                    orchestration_ingress_requested_topic(),
                ),
            ),
            EventTopicWatch(
                topic=orchestration_scheduler_signal_requested_topic(),
                after_cursor=self.events_service.snapshot_event_topic(
                    orchestration_scheduler_signal_requested_topic(),
                ),
            ),
            EventTopicWatch(
                topic=wakeup_topic,
                after_cursor=self.events_service.snapshot_event_topic(
                    wakeup_topic,
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
            run, signal = await asyncio.to_thread(
                self.process_next_available,
                worker_id=worker_id,
            )
            if run is None and signal is None:
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
            if signal is not None:
                extra["signal_id"] = signal.id
                extra["signal_kind"] = signal.signal_kind.value
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
            self.ingress_coordinator.claim_request_for_run(
                run_id=run_id,
                worker_id=worker_id,
            ),
            worker_id=worker_id,
        )

    def queue_tool_terminal_signal(
        self,
        *,
        tool_run_id: str,
    ) -> OrchestrationSchedulerSignal:
        return self.scheduler_signal_coordinator.queue_tool_terminal_signal(
            tool_run_id=tool_run_id,
        )

    def queue_sessions_spawn_followup_signal(
        self,
        *,
        child_run_id: str,
    ) -> OrchestrationSchedulerSignal:
        return self.scheduler_signal_coordinator.queue_sessions_spawn_followup_signal(
            child_run_id=child_run_id,
        )

    def process_next_signal(
        self,
        *,
        worker_id: str,
    ) -> OrchestrationSchedulerSignal | None:
        return self._process_signal(
            self.scheduler_signal_coordinator.claim_next_signal(
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
        orchestration_run_id: str,
        reason: str,
    ) -> OrchestrationRun | None:
        return self.handle_recovered_dispatch_task_fn(
            orchestration_run_id=orchestration_run_id,
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
        if request is None:
            return None
        try:
            run = self._prepare_and_enqueue_request(request)
            self.ingress_coordinator.complete_request(request.id)
            if self.on_run_enqueued is not None:
                try:
                    self.on_run_enqueued(run)
                except Exception:
                    logger.exception(
                        "orchestration scheduler run-enqueued callback failed",
                        extra={
                            "request_kind": request.kind.value,
                            "request_id": request.id,
                            "run_id": run.id,
                        },
                    )
            return run
        except Exception as exc:
            self.ingress_coordinator.fail_request(
                request.id,
                message=str(exc) or type(exc).__name__,
                code=_exception_code(exc, default="ingress_prepare_failed"),
                details={
                    "run_id": request.run_id,
                    "request_kind": request.kind.value,
                    **_exception_details(exc),
                },
            )
            try:
                failure = self._fail_input(
                    request,
                    worker_id=worker_id,
                    exc=exc,
                )
                self.fail_assignment_fn(failure)
            except Exception:
                logger.exception(
                    "failed to mark ingress-backed run as failed",
                    extra={
                        "request_kind": request.kind.value,
                        "request_id": request.id,
                        "run_id": request.run_id,
                    },
                )
            raise

    def _prepare_and_enqueue_request(
        self,
        request: OrchestrationIngressRequest,
    ) -> OrchestrationRun:
        if request.kind is OrchestrationIngressRequestKind.ROUTED_TURN:
            prepared = self.intake_port.prepare_session_run(
                self._prepare_input(request),
            )
            return self.intake_port.enqueue(
                self._enqueue_input(request, run_id=prepared.id),
            )
        if request.kind is OrchestrationIngressRequestKind.BOUND_TURN:
            bound_target = self._ingress_bound_target(request)
            routed = self.intake_port.route(
                self._route_bound_request_input(
                    request=request,
                    bound_target=bound_target,
                ),
            )
            bound = self.intake_port.bind_session(
                self._bind_bound_request_input(
                    run_id=routed.id,
                    active_session_id=bound_target.active_session_id,
                ),
            )
            return self.intake_port.enqueue(
                self._enqueue_bound_request_input(
                    request=request,
                    bound_target=bound_target,
                    run_id=bound.id,
                ),
            )
        raise OrchestrationValidationError(
            f"Unsupported orchestration ingress request kind '{request.kind.value}'.",
        )

    def _process_signal(
        self,
        signal: OrchestrationSchedulerSignal | None,
    ) -> OrchestrationSchedulerSignal | None:
        if signal is None:
            return None
        try:
            if signal.signal_kind is OrchestrationSchedulerSignalKind.TOOL_TERMINAL:
                tool_run_id = str(signal.signal_payload.get("tool_run_id", "")).strip()
                if tool_run_id:
                    self.handle_terminal_tool_run(tool_run_id)
            elif signal.signal_kind is OrchestrationSchedulerSignalKind.SESSIONS_SPAWN_FOLLOWUP:
                child_run_id = str(signal.signal_payload.get("child_run_id", "")).strip()
                if child_run_id:
                    self.process_sessions_spawn_followup(child_run_id)
            return self.scheduler_signal_coordinator.complete_signal(signal.id)
        except Exception as exc:
            logger.exception(
                "orchestration scheduler signal processing failed",
                extra={
                    "signal_id": signal.id,
                    "signal_kind": signal.signal_kind.value,
                },
            )
            return self.scheduler_signal_coordinator.fail_signal(
                signal.id,
                message=str(exc) or type(exc).__name__,
                code="scheduler_signal_failed",
                details={
                    "signal_kind": signal.signal_kind.value,
                },
            )
        finally:
            if signal is not None and signal.status is not None:
                logger.debug(
                    "orchestration scheduler finished signal processing attempt",
                    extra={
                        "signal_id": signal.id,
                        "signal_kind": signal.signal_kind.value,
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

    @staticmethod
    def _prepare_input(
        request: OrchestrationIngressRequest,
    ) -> "PrepareSessionRunInput":
        from crxzipple.modules.orchestration.application.intake_commands import (
            PrepareSessionRunInput,
        )

        if request.kind is not OrchestrationIngressRequestKind.ROUTED_TURN:
            raise OrchestrationValidationError(
                f"Request '{request.id}' is not a routed-turn ingress request.",
            )
        return PrepareSessionRunInput(
            run_id=request.run_id,
            context=OrchestrationSchedulerService._ingress_route_context(request),
            requested_llm_id=request.requested_llm_id,
            ensure=request.ensure_session,
            touch_activity=request.touch_activity,
            reset_policy=OrchestrationSchedulerService._ingress_reset_policy(request),
            priority=request.priority,
            metadata=dict(request.prepare_metadata),
        )

    @staticmethod
    def _enqueue_input(
        request: OrchestrationIngressRequest,
        *,
        run_id: str,
    ) -> "EnqueueOrchestrationRunInput":
        from crxzipple.modules.orchestration.application.intake_commands import (
            EnqueueOrchestrationRunInput,
        )

        return EnqueueOrchestrationRunInput(
            run_id=run_id,
            queue_policy=request.queue_policy,
            priority=request.priority,
        )

    @staticmethod
    def _route_bound_request_input(
        *,
        request: OrchestrationIngressRequest,
        bound_target: OrchestrationBoundSessionTarget,
    ) -> "RouteOrchestrationRunInput":
        from crxzipple.modules.orchestration.application.intake_commands import (
            RouteOrchestrationRunInput,
        )

        return RouteOrchestrationRunInput(
            run_id=request.run_id,
            agent_id=bound_target.agent_id,
            session_key=bound_target.session_key,
            lane_key=OrchestrationSchedulerService._bound_lane_key(
                session_key=bound_target.session_key,
                lane_key=bound_target.lane_key,
            ),
            priority=request.priority,
            metadata=OrchestrationSchedulerService._bound_request_metadata(
                request=request,
                session_key=bound_target.session_key,
            ),
        )

    @staticmethod
    def _bind_bound_request_input(
        *,
        run_id: str,
        active_session_id: str,
    ) -> "BindSessionInput":
        from crxzipple.modules.orchestration.application.intake_commands import (
            BindSessionInput,
        )

        return BindSessionInput(
            run_id=run_id,
            active_session_id=active_session_id,
        )

    @staticmethod
    def _enqueue_bound_request_input(
        *,
        request: OrchestrationIngressRequest,
        bound_target: OrchestrationBoundSessionTarget,
        run_id: str,
    ) -> "EnqueueOrchestrationRunInput":
        from crxzipple.modules.orchestration.application.intake_commands import (
            EnqueueOrchestrationRunInput,
        )

        return EnqueueOrchestrationRunInput(
            run_id=run_id,
            lane_key=OrchestrationSchedulerService._bound_lane_key(
                session_key=bound_target.session_key,
                lane_key=bound_target.lane_key,
            ),
            queue_policy=request.queue_policy,
            priority=request.priority,
        )

    @staticmethod
    def _bound_request_metadata(
        *,
        request: OrchestrationIngressRequest,
        session_key: str,
    ) -> dict[str, object]:
        metadata = {
            "session_key": session_key,
            **dict(request.prepare_metadata),
        }
        requested_llm_id = (
            request.requested_llm_id.strip()
            if isinstance(request.requested_llm_id, str)
            and request.requested_llm_id.strip()
            else None
        )
        if requested_llm_id is not None:
            metadata.setdefault("requested_llm_id", requested_llm_id)
        return metadata

    @staticmethod
    def _bound_lane_key(*, session_key: str, lane_key: str | None) -> str:
        if isinstance(lane_key, str) and lane_key.strip():
            return lane_key.strip()
        return session_lane_key(session_key)

    @staticmethod
    def _ingress_bound_target(
        request: OrchestrationIngressRequest,
    ) -> OrchestrationBoundSessionTarget:
        bound_target = request.bound_session_target
        if bound_target is None:
            raise OrchestrationValidationError(
                f"Missing bound session target for ingress request '{request.id}'.",
            )
        return bound_target

    @staticmethod
    def _fail_input(
        request: OrchestrationIngressRequest,
        *,
        worker_id: str,
        exc: Exception,
    ) -> "FailAssignmentInput":
        from crxzipple.modules.orchestration.application.commands import (
            FailAssignmentInput,
        )

        message = str(exc) or type(exc).__name__
        return FailAssignmentInput(
            run_id=request.run_id,
            worker_id=worker_id,
            message=message,
            code=_exception_code(exc, default="ingress_prepare_failed"),
            details={
                "request_id": request.id,
                **_exception_details(exc),
            },
        )

    @staticmethod
    def _ingress_route_context(request: OrchestrationIngressRequest) -> SessionRouteContext:
        if request.kind is not OrchestrationIngressRequestKind.ROUTED_TURN:
            raise OrchestrationValidationError(
                f"Request '{request.id}' does not carry a route context.",
            )
        payload = dict(request.route_context_payload)
        direct_scope = payload.get("direct_scope")
        if direct_scope is not None:
            payload["direct_scope"] = (
                direct_scope
                if isinstance(direct_scope, DirectSessionScope)
                else DirectSessionScope(str(direct_scope))
            )
        metadata = payload.get("metadata")
        if not isinstance(metadata, dict):
            payload["metadata"] = {}
        try:
            return SessionRouteContext(**payload)
        except Exception as exc:
            raise OrchestrationValidationError(
                f"Invalid orchestration ingress route context for request '{request.id}'.",
            ) from exc

    @staticmethod
    def _ingress_reset_policy(
        request: OrchestrationIngressRequest,
    ) -> SessionResetPolicy | None:
        payload = request.reset_policy_payload
        if not payload:
            return None
        return SessionResetPolicy(
            idle_minutes=(
                int(payload["idle_minutes"])
                if payload.get("idle_minutes") is not None
                else None
            ),
            daily_reset_hour_utc=(
                int(payload["daily_reset_hour_utc"])
                if payload.get("daily_reset_hour_utc") is not None
                else None
            ),
        )


def _exception_code(exc: Exception, *, default: str) -> str:
    code = getattr(exc, "code", None)
    if isinstance(code, str) and code.strip():
        return code.strip()
    return default


def _exception_details(exc: Exception) -> dict[str, object]:
    details = getattr(exc, "details", None)
    if isinstance(details, dict):
        return dict(details)
    return {}
