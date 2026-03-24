from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Protocol
from uuid import uuid4

from crxzipple.modules.dispatch.application import (
    DispatchApplicationService,
)
from crxzipple.modules.orchestration.application.engine import (
    EngineAdvanceOutcome,
    OrchestrationEngine,
)
from crxzipple.modules.orchestration.application.dispatch_bridge import (
    OrchestrationDispatchBridge,
)
from crxzipple.modules.orchestration.application.lease_manager import (
    OrchestrationLeaseManager,
)
from crxzipple.modules.orchestration.application.router import OrchestrationRouter
from crxzipple.modules.orchestration.application.scheduler import (
    OrchestrationScheduler,
)
from crxzipple.modules.orchestration.application.session_resolver import (
    ResolveSessionBundleInput,
    SessionBundle,
    SessionResolver,
)
from crxzipple.modules.orchestration.application.tool_resume import (
    OrchestrationToolResumeCoordinator,
)
from crxzipple.modules.orchestration.domain.entities import OrchestrationRun
from crxzipple.modules.orchestration.domain.exceptions import (
    OrchestrationRunNotFoundError,
    OrchestrationValidationError,
)
from crxzipple.modules.orchestration.domain.repositories import (
    OrchestrationRunRepository,
    OrchestrationRunWaitRepository,
)
from crxzipple.modules.orchestration.domain.value_objects import (
    DeliveryTarget,
    InboundInstruction,
    OrchestrationQueuePolicy,
    OrchestrationRunStage,
    OrchestrationRunStatus,
)
from crxzipple.modules.session.domain import SessionResetPolicy, SessionRouteContext
from crxzipple.shared.domain.aggregates import AggregateRoot
from crxzipple.modules.dispatch.domain import DispatchTaskRepository


@dataclass(frozen=True, slots=True)
class AcceptOrchestrationRunInput:
    inbound_instruction: InboundInstruction
    delivery_target: DeliveryTarget | None = None
    run_id: str | None = None
    queue_policy: OrchestrationQueuePolicy = OrchestrationQueuePolicy.FIFO
    priority: int = 100
    max_steps: int = 12
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RouteOrchestrationRunInput:
    run_id: str
    agent_id: str
    bulk_key: str
    lane_key: str | None = None
    priority: int | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class BindSessionInput:
    run_id: str
    active_session_id: str
    bulk_key: str | None = None


@dataclass(frozen=True, slots=True)
class EnqueueOrchestrationRunInput:
    run_id: str
    lane_key: str | None = None
    queue_policy: OrchestrationQueuePolicy | None = None
    priority: int | None = None


@dataclass(frozen=True, slots=True)
class AdvanceOrchestrationRunInput:
    run_id: str
    worker_id: str
    stage: OrchestrationRunStage
    step_increment: int = 0
    metadata: dict[str, object] = field(default_factory=dict)
    now: datetime | None = None


@dataclass(frozen=True, slots=True)
class WaitOnToolInput:
    run_id: str
    worker_id: str
    pending_tool_run_ids: tuple[str, ...]
    reason: str | None = None
    now: datetime | None = None


@dataclass(frozen=True, slots=True)
class ResumeOrchestrationRunInput:
    run_id: str
    lane_key: str | None = None
    queue_policy: OrchestrationQueuePolicy | None = None
    priority: int | None = None
    reason: str | None = None
    clear_pending_tool_run_ids: bool = True
    now: datetime | None = None


@dataclass(frozen=True, slots=True)
class CompleteOrchestrationRunInput:
    run_id: str
    worker_id: str
    result_payload: dict[str, object] = field(default_factory=dict)
    now: datetime | None = None


@dataclass(frozen=True, slots=True)
class FailOrchestrationRunInput:
    run_id: str
    message: str
    code: str = "orchestration_failed"
    details: dict[str, object] = field(default_factory=dict)
    worker_id: str | None = None
    now: datetime | None = None


@dataclass(frozen=True, slots=True)
class PrepareSessionRunInput:
    run_id: str
    context: SessionRouteContext
    ensure: bool = True
    touch_activity: bool = True
    reset_policy: SessionResetPolicy | None = None
    priority: int | None = None
    metadata: dict[str, object] = field(default_factory=dict)
    now: datetime | None = None


class OrchestrationUnitOfWork(Protocol):
    orchestration_runs: OrchestrationRunRepository
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


class OrchestrationApplicationService:
    def __init__(
        self,
        uow_factory: Callable[[], OrchestrationUnitOfWork],
        scheduler: OrchestrationScheduler | None = None,
        dispatch_bridge: OrchestrationDispatchBridge | None = None,
        dispatch_service: DispatchApplicationService | None = None,
        router: OrchestrationRouter | None = None,
        session_resolver: SessionResolver | None = None,
        engine: OrchestrationEngine | None = None,
        worker_lease_seconds: int = 30,
        worker_heartbeat_seconds: float = 5.0,
    ) -> None:
        self.uow_factory = uow_factory
        self.scheduler = scheduler or OrchestrationScheduler()
        self.dispatch_bridge = dispatch_bridge or OrchestrationDispatchBridge()
        self.dispatch_service = dispatch_service
        self.router = router or OrchestrationRouter()
        self.session_resolver = session_resolver
        self.engine = engine
        self.worker_lease_seconds = worker_lease_seconds
        self.worker_heartbeat_seconds = worker_heartbeat_seconds
        self.lease_manager = OrchestrationLeaseManager(
            uow_factory=uow_factory,
            dispatch_bridge=self.dispatch_bridge,
            dispatch_service=self.dispatch_service,
            worker_lease_seconds=worker_lease_seconds,
            worker_heartbeat_seconds=worker_heartbeat_seconds,
        )
        self.tool_resume = (
            OrchestrationToolResumeCoordinator(
                uow_factory=uow_factory,
                engine=engine,
                get_run=self.get_run,
                resume_run=self._resume_after_tool_completion,
            )
            if engine is not None
            else None
        )

    def accept(self, data: AcceptOrchestrationRunInput) -> OrchestrationRun:
        run = OrchestrationRun.accept(
            run_id=data.run_id or uuid4().hex,
            inbound_instruction=data.inbound_instruction,
            delivery_target=data.delivery_target,
            queue_policy=data.queue_policy,
            priority=data.priority,
            max_steps=data.max_steps,
            metadata=data.metadata,
        )
        with self.uow_factory() as uow:
            uow.orchestration_runs.add(run)
            uow.collect(run)
            uow.commit()
            return run

    def route(self, data: RouteOrchestrationRunInput) -> OrchestrationRun:
        with self.uow_factory() as uow:
            run = self._get_run(uow, data.run_id)
            run.route(
                agent_id=data.agent_id,
                bulk_key=data.bulk_key,
                lane_key=data.lane_key,
                priority=data.priority,
                metadata=data.metadata,
            )
            uow.orchestration_runs.add(run)
            uow.collect(run)
            uow.commit()
            return run

    def bind_session(self, data: BindSessionInput) -> OrchestrationRun:
        with self.uow_factory() as uow:
            run = self._get_run(uow, data.run_id)
            run.bind_session(
                active_session_id=data.active_session_id,
                bulk_key=data.bulk_key,
            )
            uow.orchestration_runs.add(run)
            uow.collect(run)
            uow.commit()
            return run

    def enqueue(self, data: EnqueueOrchestrationRunInput) -> OrchestrationRun:
        with self.uow_factory() as uow:
            run = self._get_run(uow, data.run_id)
            self.scheduler.enqueue(
                run,
                lane_key=data.lane_key,
                queue_policy=data.queue_policy,
                priority=data.priority,
            )
            self.dispatch_bridge.enqueue(uow.dispatch_tasks, uow, run)
            uow.orchestration_runs.add(run)
            uow.collect(run)
            uow.commit()
            return run

    def get_run(self, run_id: str) -> OrchestrationRun:
        with self.uow_factory() as uow:
            return self._get_run(uow, run_id)

    def list_runs(
        self,
        *,
        status: OrchestrationRunStatus | None = None,
    ) -> list[OrchestrationRun]:
        with self.uow_factory() as uow:
            return uow.orchestration_runs.list(status=status)

    def claim_next_queued_run(self, *, worker_id: str) -> OrchestrationRun | None:
        return self.lease_manager.claim_next_queued_run(
            worker_id=worker_id,
            get_run=self._get_run,
        )

    def advance_once(self, *, run_id: str, worker_id: str) -> OrchestrationRun:
        if self.engine is None:
            raise RuntimeError("Orchestration engine is not configured.")
        while True:
            run = self.get_run(run_id)
            if run.current_step >= run.max_steps:
                return self.fail_run(
                    FailOrchestrationRunInput(
                        run_id=run_id,
                        worker_id=worker_id,
                        message="Orchestration run exceeded its maximum step budget.",
                        code="max_steps_exceeded",
                        details={"max_steps": run.max_steps},
                    ),
                )

            self.advance_run(
                AdvanceOrchestrationRunInput(
                    run_id=run_id,
                    worker_id=worker_id,
                    stage=OrchestrationRunStage.LLM,
                    step_increment=1,
                ),
            )
            run = self.get_run(run_id)
            try:
                outcome = self.engine.advance_once(
                    run,
                    on_llm_stream_update=lambda invocation_id, text: self._sync_llm_stream(
                        run_id=run_id,
                        worker_id=worker_id,
                        invocation_id=invocation_id,
                        text=text,
                    ),
                )
            except Exception as exc:
                return self.fail_run(
                    FailOrchestrationRunInput(
                        run_id=run_id,
                        worker_id=worker_id,
                        message=str(exc) or type(exc).__name__,
                        code="engine_failed",
                        details={"stage": OrchestrationRunStage.LLM.value},
                    ),
                )

            if outcome.pending_tool_run_ids:
                self.advance_run(
                    AdvanceOrchestrationRunInput(
                        run_id=run_id,
                        worker_id=worker_id,
                        stage=OrchestrationRunStage.TOOL,
                        metadata={
                            "llm_invocation_id": outcome.llm_invocation_id,
                            "tool_call_names": list(outcome.tool_call_names),
                            "pending_background_tools": [
                                dict(item) for item in outcome.pending_background_tools
                            ],
                        },
                    ),
                )
                return self.wait_on_tool(
                    WaitOnToolInput(
                        run_id=run_id,
                        worker_id=worker_id,
                        pending_tool_run_ids=outcome.pending_tool_run_ids,
                        reason="tool_background_wait",
                    ),
                )

            if outcome.continue_loop:
                self.advance_run(
                    AdvanceOrchestrationRunInput(
                        run_id=run_id,
                        worker_id=worker_id,
                        stage=OrchestrationRunStage.TOOL,
                        metadata={
                            "llm_invocation_id": outcome.llm_invocation_id,
                            "tool_call_names": list(outcome.tool_call_names),
                        },
                    ),
                )
                continue

            return self.complete_run(
                CompleteOrchestrationRunInput(
                    run_id=run_id,
                    worker_id=worker_id,
                    result_payload=self._result_payload_from_outcome(outcome),
                ),
            )

    def process_next_queued_run(self, *, worker_id: str) -> OrchestrationRun | None:
        run = self.claim_next_queued_run(worker_id=worker_id)
        if run is None:
            return None
        with self.lease_manager.heartbeat_while_processing(
            run_id=run.id,
            worker_id=worker_id,
            heartbeat_run=self._heartbeat_run_for_manager,
        ):
            return self.advance_once(run_id=run.id, worker_id=worker_id)

    def resolve_session_bundle(self, data: ResolveSessionBundleInput) -> SessionBundle:
        if self.session_resolver is None:
            raise RuntimeError("Orchestration session_resolver is not configured.")
        return self.session_resolver.resolve(data)

    def prepare_session_run(self, data: PrepareSessionRunInput) -> OrchestrationRun:
        bundle = self.resolve_session_bundle(
            ResolveSessionBundleInput(
                context=data.context,
                ensure=data.ensure,
                touch_activity=data.touch_activity,
                reset_policy=data.reset_policy,
                now=data.now,
            ),
        )
        if bundle.session is None or bundle.active_instance is None:
            raise OrchestrationValidationError(
                "Session resolution did not produce an active session to bind.",
            )

        route_metadata = {
            "session_key": bundle.routing.key_resolution.key,
            "session_kind": bundle.routing.key_resolution.kind.value,
        }
        route_metadata.update(data.metadata)

        with self.uow_factory() as uow:
            run = self._get_run(uow, data.run_id)
            run.route(
                agent_id=data.context.agent_id,
                bulk_key=bundle.routing.bulk_key,
                lane_key=bundle.routing.lane_key,
                priority=data.priority,
                metadata=route_metadata,
            )
            run.bind_session(
                active_session_id=bundle.active_instance.id,
                bulk_key=bundle.routing.bulk_key,
            )
            uow.orchestration_runs.add(run)
            uow.collect(run)
            uow.commit()
            return run

    def advance_run(self, data: AdvanceOrchestrationRunInput) -> OrchestrationRun:
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

    def wait_on_tool(self, data: WaitOnToolInput) -> OrchestrationRun:
        with self.uow_factory() as uow:
            run = self._get_run(uow, data.run_id)
            run.wait_on_tool(
                worker_id=data.worker_id,
                pending_tool_run_ids=data.pending_tool_run_ids,
                reason=data.reason,
                happened_at=data.now,
            )
            self.dispatch_bridge.wait(uow.dispatch_tasks, uow, run)
            uow.orchestration_waits.replace_tool_waits(
                run.id,
                run.pending_tool_run_ids,
            )
            uow.orchestration_runs.add(run)
            uow.collect(run)
            uow.commit()
        self._reconcile_tool_waits(data.pending_tool_run_ids)
        return self.get_run(data.run_id)

    def heartbeat_run(self, run_id: str, *, worker_id: str) -> OrchestrationRun:
        return self.lease_manager.heartbeat_run(
            run_id,
            worker_id=worker_id,
            get_run=self._get_run,
        )

    def resume_run(self, data: ResumeOrchestrationRunInput) -> OrchestrationRun:
        with self.uow_factory() as uow:
            run = self._get_run(uow, data.run_id)
            run.resume(
                lane_key=data.lane_key,
                queue_policy=data.queue_policy,
                priority=data.priority,
                reason=data.reason,
                clear_pending_tool_run_ids=data.clear_pending_tool_run_ids,
                happened_at=data.now,
            )
            self.dispatch_bridge.enqueue(uow.dispatch_tasks, uow, run)
            uow.orchestration_waits.delete_for_run(run.id)
            uow.orchestration_runs.add(run)
            uow.collect(run)
            uow.commit()
            return run

    def complete_run(self, data: CompleteOrchestrationRunInput) -> OrchestrationRun:
        with self.uow_factory() as uow:
            run = self._get_run(uow, data.run_id)
            run.complete(
                worker_id=data.worker_id,
                result_payload=data.result_payload,
                happened_at=data.now,
            )
            self.dispatch_bridge.complete(uow.dispatch_tasks, uow, run)
            uow.orchestration_waits.delete_for_run(run.id)
            uow.orchestration_runs.add(run)
            uow.collect(run)
            uow.commit()
            return run

    def fail_run(self, data: FailOrchestrationRunInput) -> OrchestrationRun:
        with self.uow_factory() as uow:
            run = self._get_run(uow, data.run_id)
            run.fail(
                worker_id=data.worker_id,
                message=data.message,
                code=data.code,
                details=data.details,
                happened_at=data.now,
            )
            self.dispatch_bridge.fail(uow.dispatch_tasks, uow, run)
            uow.orchestration_waits.delete_for_run(run.id)
            uow.orchestration_runs.add(run)
            uow.collect(run)
            uow.commit()
            return run

    def cancel_run(self, run_id: str, *, reason: str | None = None) -> OrchestrationRun:
        with self.uow_factory() as uow:
            run = self._get_run(uow, run_id)
            run.cancel(reason=reason)
            self.dispatch_bridge.cancel(uow.dispatch_tasks, uow, run)
            uow.orchestration_waits.delete_for_run(run.id)
            uow.orchestration_runs.add(run)
            uow.collect(run)
            uow.commit()
            return run

    def recover_abandoned_runs(self) -> list[OrchestrationRun]:
        return self.lease_manager.recover_abandoned_runs()

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
        if self.tool_resume is None:
            raise RuntimeError("Orchestration engine is not configured.")
        return self.tool_resume.handle_terminal_tool_run(tool_run_id)

    def _reconcile_tool_waits(self, tool_run_ids: tuple[str, ...]) -> None:
        if self.tool_resume is None:
            raise RuntimeError("Orchestration engine is not configured.")
        self.tool_resume.reconcile_tool_waits(tool_run_ids)

    @staticmethod
    def _result_payload_from_outcome(outcome: EngineAdvanceOutcome) -> dict[str, object]:
        payload: dict[str, object] = {
            "llm_id": outcome.llm_id,
            "llm_invocation_id": outcome.llm_invocation_id,
        }
        if outcome.response_text is not None:
            payload["output_text"] = outcome.response_text
        if outcome.user_message_id is not None:
            payload["user_message_id"] = outcome.user_message_id
        if outcome.assistant_message_ids:
            payload["assistant_message_ids"] = list(outcome.assistant_message_ids)
            payload["assistant_message_id"] = outcome.assistant_message_ids[-1]
        if outcome.tool_result_message_ids:
            payload["tool_result_message_ids"] = list(outcome.tool_result_message_ids)
        return payload

    @staticmethod
    def _get_run(uow: OrchestrationUnitOfWork, run_id: str) -> OrchestrationRun:
        run = uow.orchestration_runs.get(run_id)
        if run is None:
            raise OrchestrationRunNotFoundError(
                f"Orchestration run '{run_id}' was not found.",
            )
        return run

    def _heartbeat_run_for_manager(self, run_id: str, worker_id: str) -> OrchestrationRun:
        return self.heartbeat_run(run_id, worker_id=worker_id)

    def _sync_llm_stream(
        self,
        *,
        run_id: str,
        worker_id: str,
        invocation_id: str,
        text: str,
    ) -> OrchestrationRun:
        with self.uow_factory() as uow:
            run = self._get_run(uow, run_id)
            run.sync_llm_stream(
                worker_id=worker_id,
                invocation_id=invocation_id,
                text=text,
            )
            uow.orchestration_runs.add(run)
            uow.collect(run)
            uow.commit()
            return run

    def _resume_after_tool_completion(
        self,
        run_id: str,
        queue_policy: OrchestrationQueuePolicy,
        reason: str,
    ) -> OrchestrationRun:
        return self.resume_run(
            ResumeOrchestrationRunInput(
                run_id=run_id,
                queue_policy=queue_policy,
                reason=reason,
            ),
        )
