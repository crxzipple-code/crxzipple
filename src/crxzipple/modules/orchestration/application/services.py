from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Callable, Protocol

from crxzipple.core.logger import get_logger
from crxzipple.modules.agent.application import (
    AgentApplicationService,
)
from crxzipple.modules.orchestration.application.coordinators import (
    RunIntakeCoordinator,
    RunProgressCoordinator,
    RunRecoveryCoordinator,
    RunRequestCoordinator,
    RunWaitCoordinator,
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
from crxzipple.modules.orchestration.application.prompting import (
    PromptMode,
    estimate_text_tokens,
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
from crxzipple.shared.content_blocks import extract_text_content

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class AcceptOrchestrationRunInput:
    inbound_instruction: InboundInstruction
    delivery_target: DeliveryTarget | None = None
    run_id: str | None = None
    queue_policy: OrchestrationQueuePolicy = OrchestrationQueuePolicy.FIFO
    priority: int = 100
    max_steps: int = 99
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RouteOrchestrationRunInput:
    run_id: str
    agent_id: str
    session_key: str | None = None
    lane_key: str | None = None
    priority: int | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class BindSessionInput:
    run_id: str
    active_session_id: str


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
    requested_llm_id: str | None = None
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
        self.auto_compaction_reserve_tokens = auto_compaction_reserve_tokens
        self.auto_compaction_soft_threshold_tokens = auto_compaction_soft_threshold_tokens
        self.intake_coordinator = RunIntakeCoordinator(
            uow_factory=uow_factory,
            scheduler=self.scheduler,
            dispatch_port=self.dispatch_port,
            resolve_session_bundle=self.resolve_session_bundle,
            resolve_session_bundle_input_factory=lambda **kwargs: ResolveSessionBundleInput(
                **kwargs,
            ),
            session_start_prompt_flow_hint=self._session_start_prompt_flow_hint,
        )
        self.request_coordinator = RunRequestCoordinator(
            uow_factory=uow_factory,
            scheduler=self.scheduler,
            dispatch_port=self.dispatch_port,
            session_service=session_service,
            request_heartbeat_input_factory=lambda **kwargs: RequestHeartbeatInput(
                **kwargs,
            ),
        )
        self.lease_manager = OrchestrationLeaseManager(
            uow_factory=uow_factory,
            dispatch_port=self.dispatch_port,
            worker_lease_seconds=worker_lease_seconds,
            worker_heartbeat_seconds=worker_heartbeat_seconds,
        )
        self.progress_coordinator = RunProgressCoordinator(
            uow_factory=uow_factory,
            dispatch_port=self.dispatch_port,
            lease_manager=self.lease_manager,
            claim_next_queued_run=lambda worker_id: self.claim_next_queued_run(
                worker_id=worker_id,
            ),
            advance_once=lambda run_id, worker_id: self.advance_once(
                run_id=run_id,
                worker_id=worker_id,
            ),
            heartbeat_run=lambda run_id, worker_id: self.heartbeat_run(
                run_id,
                worker_id=worker_id,
            ),
            get_run=self.get_run,
            apply_compaction_summary=self._apply_compaction_summary,
            extract_memory_candidate=self._extract_memory_candidate,
            maybe_request_auto_compaction=self._maybe_request_auto_compaction,
            clear_pending_compaction_marker=(
                self.request_coordinator.clear_pending_compaction_marker
            ),
            clear_pending_memory_flush_marker=(
                self.request_coordinator.clear_pending_memory_flush_marker
            ),
            is_compaction_run=self._is_compaction_run,
            is_memory_flush_run=self._is_memory_flush_run,
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
            reconcile_tool_waits=(
                lambda tool_run_ids: self.recovery_coordinator.reconcile_tool_waits(
                    tool_run_ids,
                )
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
        self.recovery_coordinator = RunRecoveryCoordinator(
            uow_factory=uow_factory,
            lease_manager=self.lease_manager,
            wait_coordinator=self.wait_coordinator,
            tool_resume=self.tool_resume,
        )

    def accept(self, data: AcceptOrchestrationRunInput) -> OrchestrationRun:
        return self.intake_coordinator.accept(data)

    def route(self, data: RouteOrchestrationRunInput) -> OrchestrationRun:
        return self.intake_coordinator.route(data)

    def bind_session(self, data: BindSessionInput) -> OrchestrationRun:
        return self.intake_coordinator.bind_session(data)

    def enqueue(self, data: EnqueueOrchestrationRunInput) -> OrchestrationRun:
        return self.intake_coordinator.enqueue(data)

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
            maintenance_ran, terminal_run = self._maybe_run_preflight_maintenance(
                run=run,
                worker_id=worker_id,
            )
            if terminal_run is not None:
                return terminal_run
            if maintenance_ran:
                continue
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

            pre_invoke_stage = run.stage
            pre_invoke_step = run.current_step
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
                current_run = self.get_run(run_id)
                if self._run_has_left_worker_control(
                    current_run,
                    worker_id=worker_id,
                ):
                    return current_run
                if self._is_context_limit_error(exc):
                    self._rewind_llm_attempt(
                        run_id=run_id,
                        worker_id=worker_id,
                        previous_stage=pre_invoke_stage,
                        previous_step=pre_invoke_step,
                    )
                    refreshed_run = self.get_run(run_id)
                    maintenance_ran, terminal_run = self._maybe_run_preflight_maintenance(
                        run=refreshed_run,
                        worker_id=worker_id,
                        force=True,
                        failure_message=str(exc) or type(exc).__name__,
                    )
                    if terminal_run is not None:
                        return terminal_run
                    if maintenance_ran:
                        continue
                return self.fail_run(
                    FailOrchestrationRunInput(
                        run_id=run_id,
                        worker_id=worker_id,
                        message=str(exc) or type(exc).__name__,
                        code="engine_failed",
                        details={"stage": OrchestrationRunStage.LLM.value},
                    ),
                )
            current_run = self.get_run(run_id)
            if self._run_has_left_worker_control(
                current_run,
                worker_id=worker_id,
            ):
                return current_run
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

            if self._is_memory_flush_run(run) and not outcome.inline_tool_run_ids:
                return self.fail_run(
                    FailOrchestrationRunInput(
                        run_id=run_id,
                        worker_id=worker_id,
                        message=(
                            "Memory flush must complete by calling a maintenance tool."
                        ),
                        code="memory_flush_protocol_violation",
                        details={
                            "prompt_mode": "memory_flush",
                            "output_text": outcome.response_text,
                        },
                    ),
                )

            return self.complete_run(
                CompleteOrchestrationRunInput(
                    run_id=run_id,
                    worker_id=worker_id,
                    result_payload=self._result_payload_from_outcome(outcome),
                    metadata=self._prompt_metadata_from_outcome(outcome),
                ),
            )

    def process_next_queued_run(self, *, worker_id: str) -> OrchestrationRun | None:
        return self.progress_coordinator.process_next_queued_run(
            worker_id=worker_id,
        )

    def resolve_session_bundle(self, data: ResolveSessionBundleInput) -> SessionBundle:
        if self.session_resolver is None:
            raise RuntimeError("Orchestration session_resolver is not configured.")
        return self.session_resolver.resolve(data)

    def prepare_session_run(self, data: PrepareSessionRunInput) -> OrchestrationRun:
        return self.intake_coordinator.prepare_session_run(data)

    def advance_run(self, data: AdvanceOrchestrationRunInput) -> OrchestrationRun:
        return self.progress_coordinator.advance_run(data)

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
        return self.progress_coordinator.complete_run(data)

    def fail_run(self, data: FailOrchestrationRunInput) -> OrchestrationRun:
        current_run = self.get_run(data.run_id)
        if current_run.status in {
            OrchestrationRunStatus.COMPLETED,
            OrchestrationRunStatus.FAILED,
            OrchestrationRunStatus.CANCELLED,
        }:
            return current_run
        return self.progress_coordinator.fail_run(data)

    def cancel_run(self, run_id: str, *, reason: str | None = None) -> OrchestrationRun:
        return self.progress_coordinator.cancel_run(run_id, reason=reason)

    def resolve_approval_request(
        self,
        data: ResolveApprovalRequestInput,
    ) -> OrchestrationRun:
        return self.wait_coordinator.resolve_approval_request(data)

    def request_compaction(self, data: RequestCompactionInput) -> OrchestrationRun:
        return self.request_coordinator.request_compaction(data)

    def request_heartbeat(self, data: RequestHeartbeatInput) -> OrchestrationRun:
        return self.request_coordinator.request_heartbeat(data)

    def request_memory_flush(self, data: RequestMemoryFlushInput) -> OrchestrationRun:
        return self.request_coordinator.request_memory_flush(data)

    def request_due_heartbeats(
        self,
        data: RequestDueHeartbeatsInput,
    ) -> list[OrchestrationRun]:
        return self.request_coordinator.request_due_heartbeats(data)

    def recover_abandoned_runs(self) -> list[OrchestrationRun]:
        return self.recovery_coordinator.recover_abandoned_runs()

    def handle_recovered_dispatch_task(
        self,
        *,
        orchestration_run_id: str,
        reason: str,
    ) -> OrchestrationRun | None:
        return self.recovery_coordinator.handle_recovered_dispatch_task(
            orchestration_run_id=orchestration_run_id,
            reason=reason,
        )

    def handle_terminal_tool_run(self, tool_run_id: str) -> list[OrchestrationRun]:
        return self.recovery_coordinator.handle_terminal_tool_run(tool_run_id)

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
        if outcome.inline_tool_run_ids:
            payload["inline_tool_run_ids"] = list(outcome.inline_tool_run_ids)
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
        del run
        return

    @staticmethod
    def _get_run(uow: OrchestrationUnitOfWork, run_id: str) -> OrchestrationRun:
        run = uow.orchestration_runs.get(run_id)
        if run is None:
            raise OrchestrationRunNotFoundError(
                f"Orchestration run '{run_id}' was not found.",
            )
        return run

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
            if self._run_has_left_worker_control(
                run,
                worker_id=worker_id,
            ):
                return run
            run.sync_llm_stream(
                worker_id=worker_id,
                invocation_id=invocation_id,
                text=text,
            )
            uow.orchestration_runs.add(run)
            uow.collect(run)
            uow.commit()
            return run

    @staticmethod
    def _run_has_left_worker_control(
        run: OrchestrationRun,
        *,
        worker_id: str,
    ) -> bool:
        if run.status is not OrchestrationRunStatus.RUNNING:
            return True
        return run.worker_id != worker_id

    def _maybe_run_preflight_maintenance(
        self,
        *,
        run: OrchestrationRun,
        worker_id: str,
        force: bool = False,
        failure_message: str | None = None,
    ) -> tuple[bool, OrchestrationRun | None]:
        if not self.auto_compaction_enabled:
            return False, None
        if self.engine is None or self.session_service is None:
            return False, None
        if self._is_maintenance_mode_run(run):
            return False, None
        session_key = str(run.metadata.get("session_key", "")).strip()
        if not session_key:
            return False, None
        preview = self._safe_preview_prompt(run)
        trigger = self._preflight_compaction_trigger(
            run=run,
            preview=preview,
            force=force,
            failure_message=failure_message,
        )
        if trigger is None:
            return False, None
        if self._preflight_maintenance_attempted(run):
            return False, self.fail_run(
                FailOrchestrationRunInput(
                    run_id=run.id,
                    worker_id=worker_id,
                    message=(
                        "Prompt budget remained above the maintenance threshold "
                        "after a recovery attempt."
                    ),
                    code="context_budget_unrecoverable",
                    details=trigger,
                ),
            )
        self._record_preflight_maintenance_attempt(
            run_id=run.id,
            step=run.current_step,
            details=trigger,
        )

        flush_run = self.request_coordinator.existing_pending_memory_flush_run(session_key)
        compaction_run = self.request_coordinator.existing_pending_compaction_run(session_key)
        if flush_run is None and compaction_run is None:
            flush_run = self.request_memory_flush(
                RequestMemoryFlushInput(
                    anchor_run_id=run.id,
                    reason=str(trigger["flush_reason"]),
                    trigger_basis="pre_compaction",
                    trigger_details={
                        "compaction_trigger_basis": str(trigger["trigger_basis"]),
                        "compaction_trigger_details": dict(trigger["trigger_details"]),
                        "compaction_reason": str(trigger["compaction_reason"]),
                        "compaction_preserve": (
                            "open tasks, decisions, approvals, constraints, "
                            "and preferences"
                        ),
                    },
                ),
            )

        if flush_run is not None:
            processed_flush = self._process_requested_run_inline(
                run_id=flush_run.id,
                worker_id=worker_id,
            )
            if processed_flush.status is not OrchestrationRunStatus.COMPLETED:
                return False, self.fail_run(
                    FailOrchestrationRunInput(
                        run_id=run.id,
                        worker_id=worker_id,
                        message=(
                            "Preflight memory flush did not complete successfully."
                        ),
                        code="preflight_maintenance_failed",
                        details={
                            "maintenance_run_id": processed_flush.id,
                            "maintenance_kind": "memory_flush",
                            "maintenance_status": processed_flush.status.value,
                            **trigger,
                        },
                    ),
                )
            compaction_run = self.request_coordinator.existing_pending_compaction_run(
                session_key,
            )

        if compaction_run is None:
            return False, self.fail_run(
                FailOrchestrationRunInput(
                    run_id=run.id,
                    worker_id=worker_id,
                    message=(
                        "Preflight maintenance did not schedule a compaction run."
                    ),
                    code="preflight_maintenance_failed",
                    details=trigger,
                ),
            )
        processed_compaction = self._process_requested_run_inline(
            run_id=compaction_run.id,
            worker_id=worker_id,
        )
        if processed_compaction.status is not OrchestrationRunStatus.COMPLETED:
            return False, self.fail_run(
                FailOrchestrationRunInput(
                    run_id=run.id,
                    worker_id=worker_id,
                    message="Preflight compaction did not complete successfully.",
                    code="preflight_maintenance_failed",
                    details={
                        "maintenance_run_id": processed_compaction.id,
                        "maintenance_kind": "compaction",
                        "maintenance_status": processed_compaction.status.value,
                        **trigger,
                    },
                ),
            )
        self._mark_preflight_maintenance_applied(
            run_id=run.id,
            step=run.current_step,
            details=trigger,
        )
        return True, None

    def _process_requested_run_inline(
        self,
        *,
        run_id: str,
        worker_id: str,
    ) -> OrchestrationRun:
        claimed = self.lease_manager.claim_run(
            run_id,
            worker_id=worker_id,
            get_run=self._get_run,
        )
        with self.lease_manager.heartbeat_while_processing(
            run_id=claimed.id,
            worker_id=worker_id,
            heartbeat_run=self.heartbeat_run,
        ):
            return self.advance_once(run_id=claimed.id, worker_id=worker_id)

    def _preflight_compaction_trigger(
        self,
        *,
        run: OrchestrationRun,
        preview: PromptPreview | None,
        force: bool,
        failure_message: str | None,
    ) -> dict[str, object] | None:
        metrics = self._preflight_prompt_budget_metrics(run, preview=preview)
        trigger = self._compaction_trigger_from_metrics(
            estimated_total_tokens=metrics["estimated_total_tokens"],
            dynamic_threshold=metrics["prompt_threshold_tokens"],
        )
        if trigger is None and not force:
            return None
        flush_reason = "preflight_compaction_memory_flush"
        if force:
            flush_reason = "preflight_compaction_context_limit_recovery"
        details = dict(metrics)
        if failure_message is not None and failure_message.strip():
            details["failure_message"] = failure_message.strip()
        if trigger is None:
            trigger = {
                "trigger_basis": "context_limit_recovery",
                "compaction_reason": "context_limit_recovery_after_engine_error",
                "trigger_details": details,
            }
        trigger["flush_reason"] = flush_reason
        return trigger

    def _preflight_prompt_budget_metrics(
        self,
        run: OrchestrationRun,
        *,
        preview: PromptPreview | None,
    ) -> dict[str, int | None]:
        estimated_total_tokens = 0
        transcript_chars = 0
        transcript_estimated_tokens = 0
        prompt_threshold_tokens: int | None = None
        if preview is not None and preview.prompt_report is not None:
            report = preview.prompt_report
            estimated_total_tokens = (
                report.system_estimated_tokens + report.transcript_estimated_tokens
            )
            transcript_chars = report.transcript_chars
            transcript_estimated_tokens = report.transcript_estimated_tokens
            prompt_threshold_tokens = self._auto_compaction_prompt_threshold_tokens_for_context_window(
                report.llm_context_window_tokens,
            )

        pending_inbound_chars, pending_inbound_tokens = self._pending_inbound_prompt_metrics(
            run,
        )
        return {
            "estimated_total_tokens": estimated_total_tokens + pending_inbound_tokens,
            "transcript_chars": transcript_chars + pending_inbound_chars,
            "transcript_estimated_tokens": (
                transcript_estimated_tokens + pending_inbound_tokens
            ),
            "prompt_threshold_tokens": prompt_threshold_tokens,
            "pending_inbound_chars": pending_inbound_chars,
            "pending_inbound_estimated_tokens": pending_inbound_tokens,
        }

    def _pending_inbound_prompt_metrics(
        self,
        run: OrchestrationRun,
    ) -> tuple[int, int]:
        session_key = str(run.metadata.get("session_key", "")).strip()
        if (
            self.session_service is None
            or not session_key
            or run.active_session_id is None
            or not run.active_session_id.strip()
        ):
            return 0, 0
        existing_message = self.session_service.get_message_by_source(
            session_key=session_key,
            session_id=run.active_session_id,
            source_kind="orchestration_run",
            source_id=run.id,
        )
        if existing_message is not None and existing_message.role == "user":
            return 0, 0
        content = extract_text_content(run.inbound_instruction.content)
        if content is None or not content.strip():
            return 0, 0
        return len(content), estimate_text_tokens(content)

    def _safe_preview_prompt(self, run: OrchestrationRun) -> PromptPreview | None:
        if self.engine is None:
            return None
        try:
            return self.engine.preview_prompt(run)
        except Exception:
            logger.exception(
                "failed to build prompt preview for preflight maintenance",
                extra={"run_id": run.id},
            )
            return None

    def _record_preflight_maintenance_attempt(
        self,
        *,
        run_id: str,
        step: int,
        details: dict[str, object],
    ) -> None:
        with self.uow_factory() as uow:
            run = self._get_run(uow, run_id)
            current_payload = run.metadata.get("preflight_maintenance")
            payload = dict(current_payload) if isinstance(current_payload, dict) else {}
            payload["last_attempt_step"] = step
            payload["last_attempt_details"] = dict(details)
            run.metadata["preflight_maintenance"] = payload
            uow.orchestration_runs.add(run)
            uow.collect(run)
            uow.commit()

    def _mark_preflight_maintenance_applied(
        self,
        *,
        run_id: str,
        step: int,
        details: dict[str, object],
    ) -> None:
        with self.uow_factory() as uow:
            run = self._get_run(uow, run_id)
            current_payload = run.metadata.get("preflight_maintenance")
            payload = dict(current_payload) if isinstance(current_payload, dict) else {}
            payload["applied_for_run"] = True
            payload["applied_step"] = step
            payload["applied_details"] = dict(details)
            run.metadata["preflight_maintenance"] = payload
            uow.orchestration_runs.add(run)
            uow.collect(run)
            uow.commit()

    @staticmethod
    def _preflight_maintenance_attempted(run: OrchestrationRun) -> bool:
        payload = run.metadata.get("preflight_maintenance")
        if not isinstance(payload, dict):
            return False
        try:
            return int(payload.get("last_attempt_step")) == run.current_step
        except (TypeError, ValueError):
            return False

    def _rewind_llm_attempt(
        self,
        *,
        run_id: str,
        worker_id: str,
        previous_stage: OrchestrationRunStage,
        previous_step: int,
    ) -> OrchestrationRun:
        with self.uow_factory() as uow:
            run = self._get_run(uow, run_id)
            run.rewind_llm_attempt(
                worker_id=worker_id,
                previous_stage=previous_stage,
                previous_step=previous_step,
            )
            uow.orchestration_runs.add(run)
            uow.collect(run)
            uow.commit()
            return run

    @staticmethod
    def _is_context_limit_error(exc: Exception) -> bool:
        message = (str(exc) or type(exc).__name__).strip().lower()
        if not message:
            return False
        patterns = (
            "context length",
            "context_length",
            "maximum context",
            "max context",
            "context window",
            "too many tokens",
            "token limit",
            "prompt is too long",
            "context_limit",
        )
        return any(pattern in message for pattern in patterns)

    @staticmethod
    def _is_maintenance_mode_run(run: OrchestrationRun) -> bool:
        if OrchestrationApplicationService._is_memory_flush_run(run):
            return True
        if OrchestrationApplicationService._is_compaction_run(run):
            return True
        prompt_mode = str(run.metadata.get("prompt_mode", "")).strip().lower()
        if prompt_mode == PromptMode.HEARTBEAT.value:
            return True
        prompt_flow_hint = run.metadata.get("prompt_flow_hint")
        if isinstance(prompt_flow_hint, dict):
            raw_mode = str(prompt_flow_hint.get("mode", "")).strip().lower()
            if raw_mode == PromptMode.HEARTBEAT.value:
                return True
        return False

    def _compaction_trigger_from_metrics(
        self,
        *,
        estimated_total_tokens: int,
        dynamic_threshold: int | None,
    ) -> dict[str, object] | None:
        dynamic_threshold_exceeded = (
            dynamic_threshold is not None
            and estimated_total_tokens >= dynamic_threshold
        )
        if not dynamic_threshold_exceeded or dynamic_threshold is None:
            return None
        trigger_details: dict[str, object] = {
            "estimated_total_tokens": estimated_total_tokens,
            "prompt_threshold_tokens": dynamic_threshold,
        }
        return {
            "trigger_basis": "prompt_budget",
            "compaction_reason": (
                "auto_compaction_prompt_budget_exceeded"
                f":{estimated_total_tokens}/{dynamic_threshold}"
            ),
            "trigger_details": trigger_details,
        }

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
            updated_result_payload = dict(persisted_run.result_payload or {})
            updated_result_payload["archived_message_count"] = archived_count
            updated_result_payload["archived_through_sequence_no"] = cutoff_sequence_no
            updated_result_payload["compacted_at"] = (
                run.completed_at.isoformat()
                if run.completed_at is not None
                else run.updated_at.isoformat()
            )
            persisted_run.result_payload = updated_result_payload
            uow.orchestration_runs.add(persisted_run)
            uow.collect(persisted_run)
            uow.commit()

    def _maybe_request_auto_compaction(self, run: OrchestrationRun) -> OrchestrationRun | None:
        if not self.auto_compaction_enabled:
            return None
        if self.session_service is None:
            return None
        if self._is_memory_flush_run(run):
            flush_request = run.metadata.get("memory_flush_request")
            if not isinstance(flush_request, dict):
                return None
            if str(flush_request.get("basis", "")).strip().lower() != "pre_compaction":
                return None
            session_key = str(run.metadata.get("session_key", "")).strip()
            if not session_key:
                return None
            if (
                self.request_coordinator.existing_pending_compaction_run(session_key)
                is not None
            ):
                return None
            trigger_details = flush_request.get("details")
            if not isinstance(trigger_details, dict):
                trigger_details = {}
            compaction_trigger_details = trigger_details.get("compaction_trigger_details")
            if not isinstance(compaction_trigger_details, dict):
                compaction_trigger_details = {}
            compaction_trigger_basis = str(
                trigger_details.get("compaction_trigger_basis", ""),
            ).strip() or "pre_compaction"
            compaction_reason = (
                str(trigger_details.get("compaction_reason", "")).strip()
                or "auto_compaction_after_memory_flush"
            )
            compaction_preserve = (
                str(trigger_details.get("compaction_preserve", "")).strip()
                or "open tasks, decisions, approvals, constraints, and preferences"
            )
            logger.info(
                "auto compaction requested after pre-compaction memory flush",
                extra={"run_id": run.id, "session_key": session_key},
            )
            return self.request_compaction(
                RequestCompactionInput(
                    anchor_run_id=run.id,
                    reason=compaction_reason,
                    preserve=compaction_preserve,
                    trigger_basis=compaction_trigger_basis,
                    trigger_details=dict(compaction_trigger_details),
                ),
            )
        if self._is_compaction_run(run):
            return None
        preflight_payload = run.metadata.get("preflight_maintenance")
        if isinstance(preflight_payload, dict) and preflight_payload.get("applied_for_run"):
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
        dynamic_threshold = self._auto_compaction_prompt_threshold_tokens(run)
        trigger = self._compaction_trigger_from_metrics(
            estimated_total_tokens=estimated_total_tokens,
            dynamic_threshold=dynamic_threshold,
        )
        if trigger is None:
            return None
        if (
            self.request_coordinator.existing_pending_compaction_run(session_key)
            is not None
        ):
            return None
        if (
            self.request_coordinator.existing_pending_memory_flush_run(session_key)
            is not None
        ):
            return None
        logger.info(
            "auto pre-compaction memory flush requested after completed run",
            extra={
                "run_id": run.id,
                "session_key": session_key,
                "transcript_chars": transcript_chars,
                "transcript_estimated_tokens": transcript_estimated_tokens,
                "estimated_total_tokens": estimated_total_tokens,
                "dynamic_threshold": dynamic_threshold,
            },
        )
        return self.request_memory_flush(
            RequestMemoryFlushInput(
                anchor_run_id=run.id,
                reason="auto_pre_compaction_flush",
                trigger_basis="pre_compaction",
                trigger_details={
                    "compaction_trigger_basis": str(trigger["trigger_basis"]),
                    "compaction_trigger_details": dict(trigger["trigger_details"]),
                    "compaction_reason": str(trigger["compaction_reason"]),
                    "compaction_preserve": (
                        "open tasks, decisions, approvals, constraints, "
                        "and preferences"
                    ),
                },
            ),
        )

    def _auto_compaction_prompt_threshold_tokens(
        self,
        run: OrchestrationRun,
    ) -> int | None:
        return self._auto_compaction_prompt_threshold_tokens_for_context_window(
            self._context_window_tokens_for_run(run),
        )

    def _auto_compaction_prompt_threshold_tokens_for_context_window(
        self,
        context_window_tokens: int | None,
    ) -> int | None:
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
