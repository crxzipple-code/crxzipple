from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Protocol
from uuid import uuid4

from crxzipple.core.logger import get_logger
from crxzipple.modules.agent.application import (
    AgentApplicationService,
)
from crxzipple.modules.memory.application import RecordMemoryFlushInput
from crxzipple.modules.orchestration.application.coordinators import (
    RunWaitCoordinator,
)
from crxzipple.modules.orchestration.application.memory_flush import (
    is_memory_flush_skip_reply,
)
from crxzipple.modules.orchestration.application.engine import (
    EngineAdvanceOutcome,
    OrchestrationEngine,
    PromptPreview,
)
from crxzipple.modules.orchestration.application.lease_manager import (
    OrchestrationLeaseManager,
)
from crxzipple.modules.orchestration.application.ports import (
    AuthorizationPort,
    LlmPort,
    MemoryPort,
    RunDispatchPort,
)
from crxzipple.modules.orchestration.application.router import OrchestrationRouter
from crxzipple.modules.orchestration.application.scheduler import (
    OrchestrationScheduler,
)
from crxzipple.modules.orchestration.application.memory_candidates import (
    extract_memory_candidate,
)
from crxzipple.modules.orchestration.application.prompting import PromptMode
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
    ApprovalDecision,
    ApprovalResolution,
    CapabilityRequestScopeHint,
    DeliveryTarget,
    InboundInstruction,
    OrchestrationQueuePolicy,
    OrchestrationRunStage,
    OrchestrationRunStatus,
    PendingApprovalRequest,
)
from crxzipple.modules.session.application import (
    ArchiveSessionMessagesInput,
    AppendSessionMessageInput,
    SessionApplicationService,
)
from crxzipple.modules.session.domain import (
    SessionMessageKind,
    SessionMessageNotFoundError,
    SessionResetPolicy,
    SessionRouteContext,
)
from crxzipple.shared.domain.aggregates import AggregateRoot
from crxzipple.modules.dispatch.domain import DispatchTaskRepository

logger = get_logger(__name__)


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
class WaitForConfirmationInput:
    run_id: str
    worker_id: str
    request: PendingApprovalRequest
    llm_invocation_id: str
    metadata: dict[str, object] = field(default_factory=dict)
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
    metadata: dict[str, object] = field(default_factory=dict)
    now: datetime | None = None


@dataclass(frozen=True, slots=True)
class CompleteOrchestrationRunInput:
    run_id: str
    worker_id: str
    result_payload: dict[str, object] = field(default_factory=dict)
    metadata: dict[str, object] = field(default_factory=dict)
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


@dataclass(frozen=True, slots=True)
class ResolveApprovalRequestInput:
    run_id: str
    request_id: str
    decision: ApprovalDecision
    now: datetime | None = None


@dataclass(frozen=True, slots=True)
class RequestCompactionInput:
    anchor_run_id: str
    reason: str | None = None
    preserve: str | None = None
    trigger_basis: str = "manual"
    trigger_details: dict[str, object] = field(default_factory=dict)
    queue_policy: OrchestrationQueuePolicy = OrchestrationQueuePolicy.JUMP_QUEUE
    priority: int | None = None
    max_steps: int = 1


@dataclass(frozen=True, slots=True)
class RequestHeartbeatInput:
    anchor_run_id: str
    reason: str | None = None
    idle_reply: str | None = "HEARTBEAT_OK"
    trigger_basis: str = "manual"
    trigger_details: dict[str, object] = field(default_factory=dict)
    queue_policy: OrchestrationQueuePolicy = OrchestrationQueuePolicy.JUMP_QUEUE
    priority: int | None = None
    max_steps: int = 1


@dataclass(frozen=True, slots=True)
class RequestMemoryFlushInput:
    anchor_run_id: str
    reason: str | None = None
    trigger_basis: str = "manual"
    trigger_details: dict[str, object] = field(default_factory=dict)
    queue_policy: OrchestrationQueuePolicy = OrchestrationQueuePolicy.JUMP_QUEUE
    priority: int | None = None
    max_steps: int = 1


@dataclass(frozen=True, slots=True)
class RequestDueHeartbeatsInput:
    idle_seconds: int
    agent_id: str | None = None
    limit: int | None = None
    reason: str | None = None
    idle_reply: str | None = "HEARTBEAT_OK"
    queue_policy: OrchestrationQueuePolicy = OrchestrationQueuePolicy.JUMP_QUEUE
    priority: int | None = None
    max_steps: int = 1
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
        dispatch_port: RunDispatchPort | None = None,
        agent_service: AgentApplicationService | None = None,
        authorization_port: AuthorizationPort | None = None,
        llm_port: LlmPort | None = None,
        memory_port: MemoryPort | None = None,
        session_service: SessionApplicationService | None = None,
        router: OrchestrationRouter | None = None,
        session_resolver: SessionResolver | None = None,
        engine: OrchestrationEngine | None = None,
        worker_lease_seconds: int = 30,
        worker_heartbeat_seconds: float = 5.0,
        auto_compaction_enabled: bool = True,
        auto_compaction_transcript_chars: int = 48_000,
        auto_compaction_transcript_tokens: int = 12_000,
        auto_compaction_reserve_tokens: int = 20_000,
        auto_compaction_soft_threshold_tokens: int = 4_000,
    ) -> None:
        self.uow_factory = uow_factory
        self.scheduler = scheduler or OrchestrationScheduler()
        if dispatch_port is None:
            raise RuntimeError("Orchestration dispatch port is not configured.")
        self.dispatch_port = dispatch_port
        self.agent_service = agent_service
        self.authorization_port = authorization_port
        self.llm_port = llm_port
        self.memory_port = memory_port
        self.session_service = session_service
        self.router = router or OrchestrationRouter()
        self.session_resolver = session_resolver
        self.engine = engine
        self.worker_lease_seconds = worker_lease_seconds
        self.worker_heartbeat_seconds = worker_heartbeat_seconds
        self.auto_compaction_enabled = auto_compaction_enabled
        self.auto_compaction_transcript_chars = auto_compaction_transcript_chars
        self.auto_compaction_transcript_tokens = auto_compaction_transcript_tokens
        self.auto_compaction_reserve_tokens = auto_compaction_reserve_tokens
        self.auto_compaction_soft_threshold_tokens = auto_compaction_soft_threshold_tokens
        self.lease_manager = OrchestrationLeaseManager(
            uow_factory=uow_factory,
            dispatch_port=self.dispatch_port,
            worker_lease_seconds=worker_lease_seconds,
            worker_heartbeat_seconds=worker_heartbeat_seconds,
        )
        self.wait_coordinator = RunWaitCoordinator(
            uow_factory=uow_factory,
            dispatch_port=self.dispatch_port,
            engine=engine,
            session_service=session_service,
            agent_service=agent_service,
            get_run=self.get_run,
            resume_input_factory=lambda **kwargs: ResumeOrchestrationRunInput(
                **kwargs,
            ),
            grant_run_tool_access=self._grant_run_tool_access,
            grant_session_tool_access=self._grant_session_tool_access,
            grant_agent_effect_access=self._grant_agent_effect_access,
            append_approval_resolution_message=self._append_approval_resolution_message,
            reconcile_tool_waits=self._reconcile_tool_waits,
            continue_recovery_contract_callback=(
                lambda run_id: self._continue_recovery_contract(run_id)
            ),
        )
        self.tool_resume = (
            OrchestrationToolResumeCoordinator(
                uow_factory=uow_factory,
                engine=engine,
                get_run=self.get_run,
                resume_run=self.wait_coordinator.resume_after_tool_completion,
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
            self.dispatch_port.enqueue(uow.dispatch_tasks, uow, run)
            uow.orchestration_runs.add(run)
            uow.collect(run)
            uow.commit()
            return run

    def get_run(self, run_id: str) -> OrchestrationRun:
        with self.uow_factory() as uow:
            return self._get_run(uow, run_id)

    def preview_prompt(self, run_id: str) -> PromptPreview:
        if self.engine is None:
            raise OrchestrationValidationError(
                "Prompt preview requires an orchestration engine.",
            )
        run = self.get_run(run_id)
        return self.engine.preview_prompt(run)

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
            self._clear_prompt_flow_hint(run_id)

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
                            **self._prompt_metadata_from_outcome(outcome),
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

            if outcome.pending_approval_request is not None:
                return self.wait_for_confirmation(
                    WaitForConfirmationInput(
                        run_id=run_id,
                        worker_id=worker_id,
                        request=outcome.pending_approval_request,
                        llm_invocation_id=outcome.llm_invocation_id,
                        metadata=self._prompt_metadata_from_outcome(outcome),
                        reason="approval_requested",
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
                            **self._prompt_metadata_from_outcome(outcome),
                        },
                    ),
                )
                continue

            return self.complete_run(
                CompleteOrchestrationRunInput(
                    run_id=run_id,
                    worker_id=worker_id,
                    result_payload=self._result_payload_from_outcome(outcome),
                    metadata=self._prompt_metadata_from_outcome(outcome),
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
            prompt_flow_hint = self._session_start_prompt_flow_hint(bundle)
            if prompt_flow_hint is not None:
                run.metadata["prompt_flow_hint"] = prompt_flow_hint
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
        return self.wait_coordinator.wait_on_tool(data)

    def wait_for_confirmation(
        self,
        data: WaitForConfirmationInput,
    ) -> OrchestrationRun:
        return self.wait_coordinator.wait_for_confirmation(data)

    def heartbeat_run(self, run_id: str, *, worker_id: str) -> OrchestrationRun:
        return self.lease_manager.heartbeat_run(
            run_id,
            worker_id=worker_id,
            get_run=self._get_run,
        )

    def resume_run(self, data: ResumeOrchestrationRunInput) -> OrchestrationRun:
        return self.wait_coordinator.resume_run(data)

    def complete_run(self, data: CompleteOrchestrationRunInput) -> OrchestrationRun:
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
        self._apply_compaction_summary(run)
        self._apply_memory_flush(run)
        self._extract_memory_candidate(run)
        self._maybe_request_auto_compaction(run)
        return self.get_run(data.run_id)

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
            self.dispatch_port.fail(uow.dispatch_tasks, uow, run)
            uow.orchestration_waits.delete_for_run(run.id)
            uow.orchestration_runs.add(run)
            uow.collect(run)
            uow.commit()
        if self._is_compaction_run(run):
            self._clear_pending_compaction_marker(run)
        return run

    def cancel_run(self, run_id: str, *, reason: str | None = None) -> OrchestrationRun:
        with self.uow_factory() as uow:
            run = self._get_run(uow, run_id)
            run.cancel(reason=reason)
            self.dispatch_port.cancel(uow.dispatch_tasks, uow, run)
            uow.orchestration_waits.delete_for_run(run.id)
            uow.orchestration_runs.add(run)
            uow.collect(run)
            uow.commit()
        if self._is_compaction_run(run):
            self._clear_pending_compaction_marker(run)
        return run

    def resolve_approval_request(
        self,
        data: ResolveApprovalRequestInput,
    ) -> OrchestrationRun:
        return self.wait_coordinator.resolve_approval_request(data)

    def request_compaction(self, data: RequestCompactionInput) -> OrchestrationRun:
        with self.uow_factory() as uow:
            anchor = self._get_run(uow, data.anchor_run_id)
            if anchor.agent_id is None or not anchor.agent_id.strip():
                raise OrchestrationValidationError(
                    "Compaction anchor run agent_id is required.",
                )
            if anchor.bulk_key is None or not anchor.bulk_key.strip():
                raise OrchestrationValidationError(
                    "Compaction anchor run bulk_key is required.",
                )
            if anchor.active_session_id is None or not anchor.active_session_id.strip():
                raise OrchestrationValidationError(
                    "Compaction anchor run active_session_id is required.",
                )
            session_key = str(anchor.metadata.get("session_key", "")).strip()
            if not session_key:
                raise OrchestrationValidationError(
                    "Compaction anchor run metadata.session_key is required.",
                )
            trigger_basis = data.trigger_basis.strip() or "manual"
            trigger_details = dict(data.trigger_details)
            metadata = {
                "session_key": session_key,
                "session_kind": str(anchor.metadata.get("session_kind", "")).strip(),
                "prompt_flow_hint": self._compaction_prompt_flow_hint(
                    reason=data.reason,
                    preserve=data.preserve,
                ),
                "compaction_anchor_run_id": anchor.id,
                "compaction_request": {
                    "basis": trigger_basis,
                    "details": trigger_details,
                    "reason": (data.reason or "").strip() or "manual",
                },
            }
            run = OrchestrationRun.accept(
                run_id=uuid4().hex,
                inbound_instruction=InboundInstruction(source="compaction"),
                queue_policy=data.queue_policy,
                priority=anchor.priority if data.priority is None else data.priority,
                max_steps=data.max_steps,
                metadata=metadata,
            )
            run.route(
                agent_id=anchor.agent_id,
                bulk_key=anchor.bulk_key,
                lane_key=anchor.lane_key,
                priority=run.priority,
                metadata=metadata,
            )
            run.bind_session(
                active_session_id=anchor.active_session_id,
                bulk_key=anchor.bulk_key,
            )
            self.scheduler.enqueue(
                run,
                lane_key=anchor.lane_key,
                queue_policy=data.queue_policy,
                priority=run.priority,
            )
            self.dispatch_port.enqueue(uow.dispatch_tasks, uow, run)
            uow.orchestration_runs.add(run)
            uow.collect(run)
            uow.commit()
        if self.session_service is not None:
            self._merge_session_compaction_metadata(
                session_key=session_key,
                metadata={
                    "pending_run_id": run.id,
                    "requested_at": run.created_at.isoformat(),
                    "request_reason": (data.reason or "").strip() or "manual",
                    "trigger_basis": trigger_basis,
                    "trigger_details": trigger_details,
                    "anchor_run_id": anchor.id,
                },
            )
        return run

    def request_heartbeat(self, data: RequestHeartbeatInput) -> OrchestrationRun:
        with self.uow_factory() as uow:
            anchor = self._get_run(uow, data.anchor_run_id)
            if anchor.agent_id is None or not anchor.agent_id.strip():
                raise OrchestrationValidationError(
                    "Heartbeat anchor run agent_id is required.",
                )
            if anchor.bulk_key is None or not anchor.bulk_key.strip():
                raise OrchestrationValidationError(
                    "Heartbeat anchor run bulk_key is required.",
                )
            if anchor.active_session_id is None or not anchor.active_session_id.strip():
                raise OrchestrationValidationError(
                    "Heartbeat anchor run active_session_id is required.",
                )
            session_key = str(anchor.metadata.get("session_key", "")).strip()
            if not session_key:
                raise OrchestrationValidationError(
                    "Heartbeat anchor run metadata.session_key is required.",
                )
            metadata = {
                "session_key": session_key,
                "session_kind": str(anchor.metadata.get("session_kind", "")).strip(),
                "prompt_flow_hint": self._heartbeat_prompt_flow_hint(
                    reason=data.reason,
                    idle_reply=data.idle_reply,
                ),
                "heartbeat_anchor_run_id": anchor.id,
                "heartbeat_request": {
                    "basis": data.trigger_basis.strip() or "manual",
                    "details": dict(data.trigger_details),
                    "reason": (data.reason or "").strip() or "manual",
                    "idle_reply": (data.idle_reply or "").strip() or "HEARTBEAT_OK",
                },
            }
            run = OrchestrationRun.accept(
                run_id=uuid4().hex,
                inbound_instruction=InboundInstruction(source="heartbeat"),
                queue_policy=data.queue_policy,
                priority=anchor.priority if data.priority is None else data.priority,
                max_steps=data.max_steps,
                metadata=metadata,
            )
            run.route(
                agent_id=anchor.agent_id,
                bulk_key=anchor.bulk_key,
                lane_key=anchor.lane_key,
                priority=run.priority,
                metadata=metadata,
            )
            run.bind_session(
                active_session_id=anchor.active_session_id,
                bulk_key=anchor.bulk_key,
            )
            self.scheduler.enqueue(
                run,
                lane_key=anchor.lane_key,
                queue_policy=data.queue_policy,
                priority=run.priority,
            )
            self.dispatch_port.enqueue(uow.dispatch_tasks, uow, run)
            uow.orchestration_runs.add(run)
            uow.collect(run)
            uow.commit()
            return run

    def request_memory_flush(self, data: RequestMemoryFlushInput) -> OrchestrationRun:
        with self.uow_factory() as uow:
            anchor = self._get_run(uow, data.anchor_run_id)
            if anchor.agent_id is None or not anchor.agent_id.strip():
                raise OrchestrationValidationError(
                    "Memory flush anchor run agent_id is required.",
                )
            if anchor.bulk_key is None or not anchor.bulk_key.strip():
                raise OrchestrationValidationError(
                    "Memory flush anchor run bulk_key is required.",
                )
            if anchor.active_session_id is None or not anchor.active_session_id.strip():
                raise OrchestrationValidationError(
                    "Memory flush anchor run active_session_id is required.",
                )
            session_key = str(anchor.metadata.get("session_key", "")).strip()
            if not session_key:
                raise OrchestrationValidationError(
                    "Memory flush anchor run metadata.session_key is required.",
                )
            trigger_basis = data.trigger_basis.strip() or "manual"
            trigger_details = dict(data.trigger_details)
            metadata = {
                "session_key": session_key,
                "session_kind": str(anchor.metadata.get("session_kind", "")).strip(),
                "prompt_flow_hint": self._memory_flush_prompt_flow_hint(
                    reason=data.reason,
                ),
                "memory_flush_anchor_run_id": anchor.id,
                "memory_flush_request": {
                    "basis": trigger_basis,
                    "details": trigger_details,
                    "reason": (data.reason or "").strip() or "manual",
                },
            }
            run = OrchestrationRun.accept(
                run_id=uuid4().hex,
                inbound_instruction=InboundInstruction(source="memory_flush"),
                queue_policy=data.queue_policy,
                priority=anchor.priority if data.priority is None else data.priority,
                max_steps=data.max_steps,
                metadata=metadata,
            )
            run.route(
                agent_id=anchor.agent_id,
                bulk_key=anchor.bulk_key,
                lane_key=anchor.lane_key,
                priority=run.priority,
                metadata=metadata,
            )
            run.bind_session(
                active_session_id=anchor.active_session_id,
                bulk_key=anchor.bulk_key,
            )
            self.scheduler.enqueue(
                run,
                lane_key=anchor.lane_key,
                queue_policy=data.queue_policy,
                priority=run.priority,
            )
            self.dispatch_port.enqueue(uow.dispatch_tasks, uow, run)
            uow.orchestration_runs.add(run)
            uow.collect(run)
            uow.commit()
            return run

    def request_due_heartbeats(
        self,
        data: RequestDueHeartbeatsInput,
    ) -> list[OrchestrationRun]:
        if self.session_service is None:
            raise RuntimeError("Orchestration session service is not configured.")
        if data.idle_seconds <= 0:
            raise OrchestrationValidationError(
                "Heartbeat idle_seconds must be greater than zero.",
            )
        if data.limit is not None and data.limit <= 0:
            raise OrchestrationValidationError(
                "Heartbeat limit must be greater than zero when provided.",
            )

        now = data.now or datetime.now(timezone.utc)
        idle_before = now - timedelta(seconds=data.idle_seconds)
        latest_runs = self._latest_anchor_runs_by_session_key()
        requested: list[OrchestrationRun] = []
        sessions = sorted(
            self.session_service.list_sessions(agent_id=data.agent_id),
            key=lambda item: item.updated_at,
        )
        for session in sessions:
            if data.limit is not None and len(requested) >= data.limit:
                break
            if session.status.strip().lower() != "active":
                continue
            updated_at = session.updated_at
            if updated_at.tzinfo is None:
                updated_at = updated_at.replace(tzinfo=timezone.utc)
            if updated_at > idle_before:
                continue
            if self._existing_inflight_run(session.id) is not None:
                continue
            anchor = latest_runs.get(session.id)
            if anchor is None:
                continue
            requested.append(
                self.request_heartbeat(
                    RequestHeartbeatInput(
                        anchor_run_id=anchor.id,
                        reason=data.reason or "idle_session_heartbeat",
                        idle_reply=data.idle_reply,
                        trigger_basis="idle_session",
                        trigger_details={
                            "idle_seconds": data.idle_seconds,
                            "session_updated_at": updated_at.isoformat(),
                        },
                        queue_policy=data.queue_policy,
                        priority=data.priority,
                        max_steps=data.max_steps,
                    ),
                ),
            )
        return requested

    def recover_abandoned_runs(self) -> list[OrchestrationRun]:
        recovered: dict[str, OrchestrationRun] = {
            run.id: run for run in self.lease_manager.recover_abandoned_runs()
        }
        for run in self.list_runs(status=OrchestrationRunStatus.WAITING):
            try:
                continued = self.wait_coordinator.continue_recovery_contract(run.id)
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
    def _prompt_metadata_from_outcome(
        outcome: EngineAdvanceOutcome,
    ) -> dict[str, object]:
        metadata: dict[str, object] = {}
        if outcome.prompt_report is not None:
            metadata["prompt_mode"] = outcome.prompt_report.mode.value
            metadata["prompt_report"] = outcome.prompt_report.to_payload()
        metadata["workspace_context_files"] = [
            {"path": item.path, "chars": item.chars}
            for item in outcome.workspace_context_files
        ]
        if (
            outcome.workspace_context_workspace is not None
            and outcome.workspace_context_workspace.strip()
        ):
            metadata["workspace_context_workspace"] = (
                outcome.workspace_context_workspace.strip()
            )
        return metadata

    def _extract_memory_candidate(self, run: OrchestrationRun) -> None:
        if self.memory_port is None:
            return
        prompt_mode = str(run.metadata.get("prompt_mode", "")).strip().lower()
        if prompt_mode in {
            PromptMode.COMPACTION.value,
            PromptMode.HEARTBEAT.value,
            PromptMode.MEMORY_FLUSH.value,
        }:
            return
        try:
            extracted = extract_memory_candidate(
                run,
                result_payload=run.result_payload,
            )
            if extracted is None:
                return
            candidate = self.memory_port.create_candidate(extracted.create_input)
            with self.uow_factory() as uow:
                current = self._get_run(uow, run.id)
                candidate_ids = current.metadata.get("memory_candidate_ids")
                if isinstance(candidate_ids, list):
                    updated_candidate_ids = [
                        str(item)
                        for item in candidate_ids
                        if isinstance(item, str) and item.strip()
                    ]
                else:
                    updated_candidate_ids = []
                if candidate.id not in updated_candidate_ids:
                    updated_candidate_ids.append(candidate.id)
                current.metadata["memory_candidate_ids"] = updated_candidate_ids
                current.metadata["memory_candidate_count"] = len(updated_candidate_ids)
                current.metadata.pop("memory_candidate_error", None)
                uow.orchestration_runs.add(current)
                uow.commit()
        except Exception as exc:
            logger.exception(
                "failed to extract memory candidate for completed run",
                extra={"run_id": run.id},
            )
            with self.uow_factory() as uow:
                current = self._get_run(uow, run.id)
                current.metadata["memory_candidate_error"] = (
                    str(exc) or type(exc).__name__
                )
                uow.orchestration_runs.add(current)
                uow.commit()

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

    def _clear_prompt_flow_hint(self, run_id: str) -> None:
        with self.uow_factory() as uow:
            run = self._get_run(uow, run_id)
            if "prompt_flow_hint" not in run.metadata:
                return
            run.metadata.pop("prompt_flow_hint", None)
            uow.orchestration_runs.add(run)
            uow.collect(run)
            uow.commit()

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
        return self.wait_coordinator.resume_after_tool_completion(
            run_id,
            queue_policy,
            reason,
        )

    def _continue_recovery_contract(self, run_id: str) -> OrchestrationRun:
        return self.wait_coordinator.continue_recovery_contract(run_id)

    @staticmethod
    def _session_start_prompt_flow_hint(
        bundle: SessionBundle,
    ) -> dict[str, object] | None:
        resolution = bundle.resolution.resolution
        if resolution.created:
            return {
                "mode": "session_start",
                "event": "created",
                "session_kind": resolution.kind.value,
            }
        if resolution.reset:
            payload: dict[str, object] = {
                "mode": "session_start",
                "event": "reset",
                "session_kind": resolution.kind.value,
            }
            if (
                resolution.reset_reason is not None
                and resolution.reset_reason.strip()
            ):
                payload["reason"] = resolution.reset_reason.strip()
            return payload
        return None

    @staticmethod
    def _compaction_prompt_flow_hint(
        *,
        reason: str | None,
        preserve: str | None,
    ) -> dict[str, object]:
        payload: dict[str, object] = {"mode": "compaction"}
        if reason is not None and reason.strip():
            payload["reason"] = reason.strip()
        if preserve is not None and preserve.strip():
            payload["preserve"] = preserve.strip()
        return payload

    @staticmethod
    def _heartbeat_prompt_flow_hint(
        *,
        reason: str | None,
        idle_reply: str | None,
    ) -> dict[str, object]:
        payload: dict[str, object] = {"mode": "heartbeat"}
        if reason is not None and reason.strip():
            payload["reason"] = reason.strip()
        if idle_reply is not None and idle_reply.strip():
            payload["idle_reply"] = idle_reply.strip()
        return payload

    @staticmethod
    def _memory_flush_prompt_flow_hint(
        *,
        reason: str | None,
    ) -> dict[str, object]:
        payload: dict[str, object] = {"mode": "memory_flush"}
        if reason is not None and reason.strip():
            payload["reason"] = reason.strip()
        return payload

    def _apply_compaction_summary(self, run: OrchestrationRun) -> None:
        prompt_mode = str(run.metadata.get("prompt_mode", "")).strip().lower()
        if prompt_mode != "compaction":
            return
        session_key = str(run.metadata.get("session_key", "")).strip()
        if not session_key:
            return
        if run.active_session_id is None or not run.active_session_id.strip():
            return
        result_payload = run.result_payload or {}
        summary_message_id = result_payload.get("assistant_message_id")
        summary_text = result_payload.get("output_text")
        if not isinstance(summary_message_id, str) or not summary_message_id.strip():
            return
        if not isinstance(summary_text, str) or not summary_text.strip():
            return
        try:
            summary_message = self.session_service.get_message(summary_message_id.strip())
        except SessionMessageNotFoundError:
            return
        summary_metadata = dict(summary_message.metadata)
        summary_metadata["maintenance_kind"] = "compaction_summary"
        summary_metadata["maintenance_run_id"] = run.id
        with self.session_service.uow_factory() as session_uow:
            session_uow.session_messages.add(
                replace(summary_message, metadata=summary_metadata),
            )
            session_uow.commit()
        cutoff_sequence_no = summary_message.sequence_no - 1
        if cutoff_sequence_no <= 0:
            return
        archived_count = self.session_service.archive_messages(
            ArchiveSessionMessagesInput(
                session_key=session_key,
                session_id=run.active_session_id,
                max_sequence_no=cutoff_sequence_no,
                reason="compaction",
            ),
        )
        self.session_service.merge_session_metadata(
            session_key=session_key,
            metadata={
                "compaction": {
                    "run_id": run.id,
                    "assistant_message_id": summary_message_id.strip(),
                    "archived_message_count": archived_count,
                    "archived_through_sequence_no": cutoff_sequence_no,
                    "summary": summary_text.strip(),
                    "compacted_at": (
                        run.completed_at.isoformat()
                        if run.completed_at is not None
                        else run.updated_at.isoformat()
                    ),
                },
            },
            touch_activity=False,
        )
        with self.uow_factory() as uow:
            persisted_run = self._get_run(uow, run.id)
            persisted_run.metadata["compaction_result"] = {
                "archived_message_count": archived_count,
                "archived_through_sequence_no": cutoff_sequence_no,
                "assistant_message_id": summary_message_id.strip(),
                "summary": summary_text.strip(),
                "compacted_at": (
                    run.completed_at.isoformat()
                    if run.completed_at is not None
                    else run.updated_at.isoformat()
                ),
            }
            uow.orchestration_runs.add(persisted_run)
            uow.collect(persisted_run)
            uow.commit()

    def _apply_memory_flush(self, run: OrchestrationRun) -> None:
        if not self._is_memory_flush_run(run):
            return
        if self.memory_port is None:
            return
        result_payload = run.result_payload or {}
        output_text = result_payload.get("output_text")
        if not isinstance(output_text, str) or not output_text.strip():
            self._store_memory_flush_result(
                run=run,
                payload={"skipped": True, "reason": "empty_output"},
            )
            return
        normalized_output = output_text.strip()
        if is_memory_flush_skip_reply(normalized_output):
            self._store_memory_flush_result(
                run=run,
                payload={"skipped": True, "reason": "no_memory_flush"},
            )
            return
        try:
            entry = self.memory_port.record_flush_entry(
                RecordMemoryFlushInput(
                    agent_id=run.agent_id or "workspace",
                    content=normalized_output,
                    session_key=_normalized_metadata_text(run.metadata, "session_key"),
                    run_id=run.id,
                    metadata={
                        "source": "memory_flush",
                        "memory_flush_anchor_run_id": run.metadata.get(
                            "memory_flush_anchor_run_id",
                        ),
                        "request": dict(
                            run.metadata.get("memory_flush_request", {})
                            if isinstance(run.metadata.get("memory_flush_request"), dict)
                            else {}
                        ),
                    },
                ),
            )
        except Exception as exc:
            logger.exception(
                "failed to persist memory flush result",
                extra={"run_id": run.id},
            )
            self._store_memory_flush_result(
                run=run,
                payload={"skipped": False, "error": str(exc) or type(exc).__name__},
            )
            return
        self._store_memory_flush_result(
            run=run,
            payload={
                "skipped": False,
                "entry_id": entry.id,
                "title": entry.title,
                "summary": entry.summary,
                "memory_file_path": entry.metadata.get("memory_file_path"),
                "storage_kind": entry.metadata.get("storage_kind"),
            },
        )

    def _maybe_request_auto_compaction(self, run: OrchestrationRun) -> OrchestrationRun | None:
        if not self.auto_compaction_enabled:
            return None
        if self.session_service is None:
            return None
        if self._is_compaction_run(run):
            return None
        prompt_mode = str(run.metadata.get("prompt_mode", "")).strip().lower()
        if prompt_mode not in {
            PromptMode.NORMAL_TURN.value,
            PromptMode.RECOVERY_RESUME.value,
        }:
            return None
        session_key = str(run.metadata.get("session_key", "")).strip()
        if not session_key:
            return None
        prompt_report = run.metadata.get("prompt_report")
        if not isinstance(prompt_report, dict):
            return None
        transcript_payload = prompt_report.get("transcript")
        if not isinstance(transcript_payload, dict):
            return None
        estimated_total_tokens = _coerce_non_negative_int(
            prompt_report.get("estimated_total_tokens"),
        )
        transcript_chars = _coerce_non_negative_int(transcript_payload.get("chars"))
        transcript_estimated_tokens = _coerce_non_negative_int(
            transcript_payload.get("estimated_tokens"),
        )
        absolute_threshold_exceeded = (
            transcript_chars >= self.auto_compaction_transcript_chars
            or transcript_estimated_tokens >= self.auto_compaction_transcript_tokens
        )
        dynamic_threshold = self._auto_compaction_prompt_threshold_tokens(run)
        dynamic_threshold_exceeded = (
            dynamic_threshold is not None
            and estimated_total_tokens >= dynamic_threshold
        )
        if not absolute_threshold_exceeded and not dynamic_threshold_exceeded:
            return None
        if self._existing_pending_compaction_run(session_key) is not None:
            return None
        logger.info(
            "auto compaction requested after completed run",
            extra={
                "run_id": run.id,
                "session_key": session_key,
                "transcript_chars": transcript_chars,
                "transcript_estimated_tokens": transcript_estimated_tokens,
                "estimated_total_tokens": estimated_total_tokens,
                "dynamic_threshold": dynamic_threshold,
            },
        )
        trigger_details = {
            "transcript_chars": transcript_chars,
            "transcript_estimated_tokens": transcript_estimated_tokens,
            "transcript_char_threshold": self.auto_compaction_transcript_chars,
            "transcript_token_threshold": self.auto_compaction_transcript_tokens,
            "estimated_total_tokens": estimated_total_tokens,
        }
        if dynamic_threshold is not None:
            trigger_details["prompt_threshold_tokens"] = dynamic_threshold
        if dynamic_threshold_exceeded and dynamic_threshold is not None:
            trigger_basis = "prompt_budget"
            reason = (
                "auto_compaction_prompt_budget_exceeded"
                f":{estimated_total_tokens}/{dynamic_threshold}"
            )
        else:
            trigger_basis = "transcript_budget"
            reason = (
                "auto_compaction_transcript_budget_exceeded"
                f":{transcript_estimated_tokens}"
            )
        return self.request_compaction(
            RequestCompactionInput(
                anchor_run_id=run.id,
                reason=reason,
                preserve="open tasks, decisions, approvals, constraints, and preferences",
                trigger_basis=trigger_basis,
                trigger_details=trigger_details,
            ),
        )

    def _auto_compaction_prompt_threshold_tokens(
        self,
        run: OrchestrationRun,
    ) -> int | None:
        context_window_tokens = self._context_window_tokens_for_run(run)
        if context_window_tokens is None:
            return None
        threshold = (
            context_window_tokens
            - self.auto_compaction_reserve_tokens
            - self.auto_compaction_soft_threshold_tokens
        )
        return threshold if threshold > 0 else None

    def _context_window_tokens_for_run(
        self,
        run: OrchestrationRun,
    ) -> int | None:
        if self.llm_port is None:
            return None
        result_payload = run.result_payload or {}
        llm_id = result_payload.get("llm_id")
        if not isinstance(llm_id, str) or not llm_id.strip():
            return None
        try:
            return self.llm_port.get_profile(llm_id.strip()).context_window_tokens
        except Exception:
            return None

    def _existing_pending_compaction_run(self, session_key: str) -> OrchestrationRun | None:
        if self.session_service is None:
            return None
        session = self.session_service.get_session(session_key)
        compaction_payload = session.metadata.get("compaction")
        if not isinstance(compaction_payload, dict):
            return None
        pending_run_id = compaction_payload.get("pending_run_id")
        if not isinstance(pending_run_id, str) or not pending_run_id.strip():
            return None
        try:
            pending_run = self.get_run(pending_run_id.strip())
        except OrchestrationRunNotFoundError:
            return None
        if pending_run.status in {
            OrchestrationRunStatus.COMPLETED,
            OrchestrationRunStatus.FAILED,
            OrchestrationRunStatus.CANCELLED,
        }:
            return None
        return pending_run

    def _latest_anchor_runs_by_session_key(self) -> dict[str, OrchestrationRun]:
        with self.uow_factory() as uow:
            runs = sorted(
                uow.orchestration_runs.list(),
                key=lambda item: item.updated_at,
                reverse=True,
            )
        latest: dict[str, OrchestrationRun] = {}
        for run in runs:
            session_key = str(run.metadata.get("session_key", "")).strip()
            if not session_key or session_key in latest:
                continue
            if run.agent_id is None or not run.agent_id.strip():
                continue
            if run.bulk_key is None or not run.bulk_key.strip():
                continue
            if run.active_session_id is None or not run.active_session_id.strip():
                continue
            latest[session_key] = run
        return latest

    def _existing_inflight_run(self, session_key: str) -> OrchestrationRun | None:
        terminal_statuses = {
            OrchestrationRunStatus.COMPLETED,
            OrchestrationRunStatus.FAILED,
            OrchestrationRunStatus.CANCELLED,
        }
        with self.uow_factory() as uow:
            runs = uow.orchestration_runs.list()
        for run in sorted(runs, key=lambda item: item.updated_at, reverse=True):
            current_session_key = str(run.metadata.get("session_key", "")).strip()
            if current_session_key != session_key:
                continue
            if run.status in terminal_statuses:
                continue
            return run
        return None

    def _merge_session_compaction_metadata(
        self,
        *,
        session_key: str,
        metadata: dict[str, object],
        remove_keys: tuple[str, ...] = (),
    ) -> None:
        if self.session_service is None:
            return
        session = self.session_service.get_session(session_key)
        current = session.metadata.get("compaction")
        payload = dict(current) if isinstance(current, dict) else {}
        payload.update(metadata)
        for key in remove_keys:
            payload.pop(key, None)
        self.session_service.merge_session_metadata(
            session_key=session_key,
            metadata={"compaction": payload},
            touch_activity=False,
        )

    def _clear_pending_compaction_marker(self, run: OrchestrationRun) -> None:
        session_key = str(run.metadata.get("session_key", "")).strip()
        if not session_key:
            return
        self._merge_session_compaction_metadata(
            session_key=session_key,
            metadata={},
            remove_keys=(
                "pending_run_id",
                "requested_at",
                "request_reason",
                "anchor_run_id",
            ),
        )

    def _store_memory_flush_result(
        self,
        *,
        run: OrchestrationRun,
        payload: dict[str, object],
    ) -> None:
        with self.uow_factory() as uow:
            persisted_run = self._get_run(uow, run.id)
            persisted_run.metadata["memory_flush_result"] = dict(payload)
            uow.orchestration_runs.add(persisted_run)
            uow.collect(persisted_run)
            uow.commit()

    @staticmethod
    def _is_memory_flush_run(run: OrchestrationRun) -> bool:
        prompt_mode = str(run.metadata.get("prompt_mode", "")).strip().lower()
        if prompt_mode == PromptMode.MEMORY_FLUSH.value:
            return True
        if run.inbound_instruction.source == "memory_flush":
            return True
        prompt_flow_hint = run.metadata.get("prompt_flow_hint")
        if isinstance(prompt_flow_hint, dict):
            raw_mode = str(prompt_flow_hint.get("mode", "")).strip().lower()
            if raw_mode == PromptMode.MEMORY_FLUSH.value:
                return True
        return False

    @staticmethod
    def _is_compaction_run(run: OrchestrationRun) -> bool:
        prompt_mode = str(run.metadata.get("prompt_mode", "")).strip().lower()
        if prompt_mode == PromptMode.COMPACTION.value:
            return True
        if run.inbound_instruction.source == "compaction":
            return True
        prompt_flow_hint = run.metadata.get("prompt_flow_hint")
        if isinstance(prompt_flow_hint, dict):
            raw_mode = str(prompt_flow_hint.get("mode", "")).strip().lower()
            if raw_mode == PromptMode.COMPACTION.value:
                return True
        return False

    def _grant_run_tool_access(
        self,
        *,
        run_id: str,
        approval_request_id: str | None,
        effect_ids: tuple[str, ...],
        tool_ids: tuple[str, ...],
    ) -> None:
        if self.authorization_port is None:
            raise RuntimeError("Authorization service is not configured.")
        run = self.get_run(run_id)
        self.authorization_port.grant_run_access(
            run_id=run.id,
            agent_id=run.agent_id,
            approval_request_id=approval_request_id,
            effect_ids=effect_ids,
            tool_ids=tool_ids,
        )

    def _grant_session_tool_access(
        self,
        *,
        run_id: str,
        approval_request_id: str | None,
        effect_ids: tuple[str, ...],
        tool_ids: tuple[str, ...],
    ) -> None:
        if self.authorization_port is None:
            raise RuntimeError("Authorization service is not configured.")
        run = self.get_run(run_id)
        session_key = str(run.metadata.get("session_key", "")).strip()
        if not session_key:
            raise OrchestrationValidationError(
                "Orchestration run metadata.session_key is required for session grants.",
            )
        self.authorization_port.grant_session_access(
            session_key=session_key,
            agent_id=run.agent_id,
            approval_request_id=approval_request_id,
            effect_ids=effect_ids,
            tool_ids=tool_ids,
        )

    def _grant_agent_effect_access(
        self,
        *,
        run_id: str,
        effect_ids: tuple[str, ...],
    ) -> None:
        if self.authorization_port is None:
            raise RuntimeError("Authorization service is not configured.")
        run = self.get_run(run_id)
        if run.agent_id is None or not run.agent_id.strip():
            raise OrchestrationValidationError(
                "Orchestration run agent_id is required for agent grants.",
            )
        for effect_id in effect_ids:
            self.authorization_port.grant_agent_effect_access(
                agent_id=run.agent_id,
                effect_id=effect_id,
            )

    def _append_approval_resolution_message(
        self,
        *,
        run_id: str,
        request: PendingApprovalRequest,
        decision: ApprovalDecision,
    ) -> None:
        run = self.get_run(run_id)
        session_key = str(run.metadata.get("session_key", "")).strip()
        if not session_key:
            raise OrchestrationValidationError(
                "Orchestration run metadata.session_key is required for approval messages.",
            )
        if run.active_session_id is None or not run.active_session_id.strip():
            raise OrchestrationValidationError(
                "Orchestration run active_session_id is required for approval messages.",
            )
        status = "approved" if decision is not ApprovalDecision.DENY else "denied"
        tool_name = request.tool_name or request.effect_id
        target_phrase = (
            f"running {tool_name}"
            if request.tool_name is not None
            else f"{request.label} ({request.effect_id})"
        )
        detail = {
            ApprovalDecision.ALLOW_ONCE: (
                f"Approved once for this turn only for {target_phrase}. "
                "This access expires after the current turn and must be requested again later if it is still needed."
            ),
            ApprovalDecision.ALLOW_FOR_SESSION: (
                f"Approved for this session for {target_phrase}. "
                "This access remains available for later turns in the current session unless visibility changes."
            ),
            ApprovalDecision.ALWAYS_FOR_AGENT: (
                f"Approved for future turns with this agent for {target_phrase}. "
                "This access should remain available in later turns unless visibility changes."
            ),
            ApprovalDecision.DENY: "Denied by the user.",
        }[decision]
        self.session_service.append_message(
            AppendSessionMessageInput(
                session_key=session_key,
                session_id=run.active_session_id,
                role="tool",
                kind=SessionMessageKind.TOOL_RESULT,
                content=detail,
                content_payload={
                    "tool_name": tool_name,
                    "tool_call_id": request.request_id,
                    "status": status,
                    "effect_id": request.effect_id,
                    "label": request.label,
                    "decision": decision.value,
                    "tool_ids": list(request.tool_ids),
                    "output": detail,
                },
                source_kind="approval_request",
                source_id=request.request_id,
                metadata={
                    "tool_call_id": request.request_id,
                    "tool_name": tool_name,
                },
            ),
        )

def _coerce_non_negative_int(value: object) -> int:
    try:
        resolved = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, resolved)


def _normalized_metadata_text(metadata: dict[str, object], key: str) -> str | None:
    value = metadata.get(key)
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None
