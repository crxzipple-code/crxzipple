from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Any, Callable, Protocol

from crxzipple.core.logger import get_logger
from crxzipple.modules.agent.application import (
    AgentApplicationService,
)
from crxzipple.modules.memory.application import RecordMemoryFlushInput
from crxzipple.modules.orchestration.application.coordinators import (
    RunIntakeCoordinator,
    RunProgressCoordinator,
    RunRecoveryCoordinator,
    RunRequestCoordinator,
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
            apply_memory_flush=self._apply_memory_flush,
            extract_memory_candidate=self._extract_memory_candidate,
            maybe_request_auto_compaction=self._maybe_request_auto_compaction,
            clear_pending_compaction_marker=(
                self.request_coordinator.clear_pending_compaction_marker
            ),
            is_compaction_run=self._is_compaction_run,
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
        if (
            self.request_coordinator.existing_pending_compaction_run(session_key)
            is not None
        ):
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
