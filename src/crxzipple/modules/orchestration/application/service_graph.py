"""Composition graph for orchestration application services."""

from __future__ import annotations

from typing import Callable

from crxzipple.core.logger import get_logger
from crxzipple.modules.agent.application import AgentApplicationService
from crxzipple.modules.events import EventsApplicationService
from crxzipple.modules.orchestration.application.approval import (
    ApprovalControlService,
    ApprovalResolutionService,
)
from crxzipple.modules.orchestration.application.cancellation import (
    RunCancellationService,
)
from crxzipple.modules.orchestration.application.commands import (
    AdvanceAssignmentInput,
    CompleteAssignmentInput,
    FailAssignmentInput,
    RequestCompactionInput,
    RequestDueHeartbeatsInput,
    RequestHeartbeatInput,
    RequestMemoryFlushInput,
    ResolveApprovalRequestInput,
    ResumeOrchestrationRunInput,
    WaitAssignmentOnToolInput,
    WaitForConfirmationInput,
)
from crxzipple.modules.orchestration.application.coordinators import (
    RunIngressCoordinator,
    RunIntakeCoordinator,
    RunProgressCoordinator,
    RunRecoveryCoordinator,
    RunRequestCoordinator,
    RunSchedulerSignalCoordinator,
    RunWaitCoordinator,
)
from crxzipple.modules.orchestration.application.engine import (
    OrchestrationEngine,
    PromptPreview,
)
from crxzipple.modules.orchestration.application.execution import RunExecutionService
from crxzipple.modules.orchestration.application.followups import (
    SessionsSpawnFollowupService,
)
from crxzipple.modules.orchestration.application.inspection import (
    OrchestrationInspectionService,
)
from crxzipple.modules.orchestration.application.intake_service import (
    OrchestrationIntakeService,
)
from crxzipple.modules.orchestration.application.intake_workflows import (
    SessionRunPreparationWorkflow,
)
from crxzipple.modules.orchestration.application.lease_manager import (
    OrchestrationLeaseManager,
)
from crxzipple.modules.orchestration.application.maintenance import (
    OrchestrationMaintenanceService,
)
from crxzipple.modules.orchestration.application.ports import (
    AuthorizationPort,
    LlmPort,
    MemoryPort,
    RunDispatchPort,
)
from crxzipple.modules.orchestration.application.query import (
    OrchestrationRunQueryService,
)
from crxzipple.modules.orchestration.application.scheduler import OrchestrationScheduler
from crxzipple.modules.orchestration.application.scheduler_service import (
    OrchestrationSchedulerService,
)
from crxzipple.modules.orchestration.application.tool_resolver import (
    ResolvedToolSet,
    ToolExecutionDecision,
)
from crxzipple.modules.orchestration.application.tool_resume import (
    OrchestrationToolResumeCoordinator,
)
from crxzipple.modules.orchestration.application.unit_of_work import (
    OrchestrationUnitOfWork,
)
from crxzipple.modules.orchestration.application.worker import (
    OrchestrationExecutorService,
)
from crxzipple.modules.orchestration.domain.entities import (
    OrchestrationExecutorLease,
    OrchestrationRun,
)
from crxzipple.modules.orchestration.domain.exceptions import (
    OrchestrationRunNotFoundError,
)
from crxzipple.modules.orchestration.domain.value_objects import (
    OrchestrationRunStatus,
)
from crxzipple.modules.session.application import (
    ResolveSessionInput,
    ResolvedSessionBundle,
    SessionApplicationService,
    SessionResolutionService,
)
from crxzipple.modules.tool.domain import Tool, ToolExecutionTarget
from crxzipple.shared.runtime_metrics import (
    RuntimeMetricsRegistry,
    get_runtime_metrics_registry,
)

logger = get_logger(__name__)


class OrchestrationServiceGraph:
    """Owns the wiring between orchestration scheduler, executor, and side services."""

    def __init__(
        self,
        uow_factory: Callable[[], OrchestrationUnitOfWork],
        *,
        scheduler: OrchestrationScheduler | None = None,
        dispatch_port: RunDispatchPort | None = None,
        agent_service: AgentApplicationService | None = None,
        authorization_port: AuthorizationPort | None = None,
        llm_port: LlmPort | None = None,
        memory_port: MemoryPort | None = None,
        session_service: SessionApplicationService | None = None,
        session_resolution_service: SessionResolutionService | None = None,
        engine: OrchestrationEngine | None = None,
        worker_lease_seconds: int = 30,
        worker_heartbeat_seconds: float = 5.0,
        auto_compaction_enabled: bool = True,
        auto_compaction_reserve_tokens: int = 20_000,
        auto_compaction_soft_threshold_tokens: int = 4_000,
        events_service: EventsApplicationService | None = None,
        runtime_metrics: RuntimeMetricsRegistry | None = None,
        run_query_service: OrchestrationRunQueryService | None = None,
    ) -> None:
        if dispatch_port is None:
            raise RuntimeError("Orchestration dispatch port is not configured.")
        self.uow_factory = uow_factory
        self.run_query_service = run_query_service or OrchestrationRunQueryService(
            uow_factory,
        )
        self.scheduler = scheduler or OrchestrationScheduler()
        self.dispatch_port = dispatch_port
        self.agent_service = agent_service
        self.authorization_port = authorization_port
        self.llm_port = llm_port
        self.memory_port = memory_port
        self.session_service = session_service
        if session_resolution_service is None:
            if session_service is None:
                raise RuntimeError(
                    "Session resolution service is not configured.",
                )
            session_resolution_service = SessionResolutionService(session_service)
        self.session_resolution_service = session_resolution_service
        self.engine = engine
        self.inspection_service = OrchestrationInspectionService(
            engine=engine,
            get_run=self.run_query_service.get_run,
        )
        self.worker_lease_seconds = worker_lease_seconds
        self.worker_heartbeat_seconds = worker_heartbeat_seconds
        self.auto_compaction_enabled = auto_compaction_enabled
        self.auto_compaction_reserve_tokens = auto_compaction_reserve_tokens
        self.auto_compaction_soft_threshold_tokens = auto_compaction_soft_threshold_tokens
        self.events_service = events_service
        self.metrics = runtime_metrics or get_runtime_metrics_registry()

        self.ingress_coordinator = RunIngressCoordinator(uow_factory=uow_factory)
        self.scheduler_signal_coordinator = RunSchedulerSignalCoordinator(
            uow_factory=uow_factory,
        )
        self.session_run_preparation_workflow = SessionRunPreparationWorkflow(
            resolve_session_bundle=self.session_resolution_service.resolve,
            resolve_session_input_factory=lambda **kwargs: ResolveSessionInput(
                **kwargs,
            ),
            session_start_prompt_flow_hint=self._session_start_prompt_flow_hint,
        )
        self.intake_coordinator = RunIntakeCoordinator(
            uow_factory=uow_factory,
            scheduler=self.scheduler,
            dispatch_port=self.dispatch_port,
            plan_prepared_session_run=self.session_run_preparation_workflow.plan,
        )
        self.intake_service = OrchestrationIntakeService(
            coordinator=self.intake_coordinator,
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
        self.maintenance_service = OrchestrationMaintenanceService(
            uow_factory=uow_factory,
            engine=engine,
            session_service=session_service,
            llm_port=llm_port,
            request_coordinator=self.request_coordinator,
            request_memory_flush=self._request_memory_flush,
            request_compaction=self._request_compaction,
            fail_assignment=self._fail_assignment,
            process_requested_run_inline=(
                lambda *, run_id, worker_id: self.executor_service.process_assignment_inline(
                    run_id=run_id,
                    worker_id=worker_id,
                    acquire_lane_lock=False,
                )
            ),
            auto_compaction_enabled=auto_compaction_enabled,
            auto_compaction_reserve_tokens=auto_compaction_reserve_tokens,
            auto_compaction_soft_threshold_tokens=auto_compaction_soft_threshold_tokens,
        )
        self.execution_service = RunExecutionService(
            engine=engine,
            maintenance_service=self.maintenance_service,
            get_run=self.run_query_service.get_run,
            advance_assignment=self._advance_assignment,
            wait_assignment_on_tool=self._wait_assignment_on_tool,
            wait_for_confirmation=self._wait_for_confirmation,
            complete_assignment=self._complete_assignment,
            fail_assignment=self._fail_assignment,
            clear_prompt_flow_hint=self._clear_prompt_flow_hint,
            events_service=events_service,
            metrics=self.metrics,
        )
        self.executor_service = OrchestrationExecutorService(
            uow_factory=uow_factory,
            events_service=events_service,
            worker_lease_seconds=worker_lease_seconds,
            lease_manager=self.lease_manager,
            admit_assignment_fn=self._admit_assignment,
            advance_once_fn=self.execution_service.advance_once,
            next_assigned_assignment_fn=self._next_assigned_assignment,
            process_assigned_assignment_fn=self._process_assigned_assignment,
            process_assigned_assignment_async_fn=self._process_assigned_assignment_async,
            process_next_assigned_assignment_fn=self._process_next_assigned_assignment,
            heartbeat_assignment_fn=self._heartbeat_assignment,
            advance_assignment_fn=self._advance_assignment,
            wait_assignment_on_tool_fn=self._wait_assignment_on_tool,
            complete_assignment_fn=self._complete_assignment,
            fail_assignment_fn=self._fail_assignment,
        )
        self.progress_coordinator = RunProgressCoordinator(
            uow_factory=uow_factory,
            dispatch_port=self.dispatch_port,
            lease_manager=self.lease_manager,
            advance_once=lambda run_id, worker_id: self.execution_service.advance_once(
                run_id=run_id,
                worker_id=worker_id,
            ),
            advance_once_async=lambda run_id, worker_id: self.execution_service.advance_once_async(
                run_id=run_id,
                worker_id=worker_id,
            ),
            heartbeat_assignment=lambda run_id, worker_id: self.executor_service.heartbeat_assignment(
                run_id=run_id,
                worker_id=worker_id,
            ),
            get_run=self.run_query_service.get_run,
            apply_compaction_summary=self.maintenance_service.apply_compaction_summary,
            maybe_request_auto_compaction=(
                self.maintenance_service.maybe_request_auto_compaction
            ),
            clear_pending_compaction_marker=(
                self.request_coordinator.clear_pending_compaction_marker
            ),
            clear_pending_memory_flush_marker=(
                self.request_coordinator.clear_pending_memory_flush_marker
            ),
            is_compaction_run=self.maintenance_service.is_compaction_run,
            is_memory_flush_run=self.maintenance_service.is_memory_flush_run,
        )
        self.cancellation_service = RunCancellationService(
            uow_factory=uow_factory,
            session_service=session_service,
            get_run=self.run_query_service.get_run,
            list_runs=self.run_query_service.list_runs,
            cancel_run_record=self.progress_coordinator.cancel_run,
            release_executor_assignment=self.lease_manager.release_executor_assignment,
            cancel_tool_run=(
                engine.tool_execution_port.cancel_tool_run
                if engine is not None
                else None
            ),
        )
        self.approval_service = ApprovalResolutionService(
            authorization_port=authorization_port,
            session_service=session_service,
            get_run=self.run_query_service.get_run,
        )
        self.wait_coordinator = RunWaitCoordinator(
            uow_factory=uow_factory,
            dispatch_port=self.dispatch_port,
            engine=engine,
            session_service=session_service,
            agent_service=agent_service,
            get_run=self.run_query_service.get_run,
            resume_input_factory=lambda **kwargs: ResumeOrchestrationRunInput(
                **kwargs,
            ),
            grant_run_tool_access=self.approval_service.grant_run_tool_access,
            grant_session_tool_access=self.approval_service.grant_session_tool_access,
            grant_agent_effect_access=self.approval_service.grant_agent_effect_access,
            append_approval_resolution_message=(
                self.approval_service.append_resolution_message
            ),
            reconcile_tool_waits=(
                lambda tool_run_ids: self.recovery_coordinator.reconcile_tool_waits(
                    tool_run_ids,
                )
            ),
            continue_recovery_contract_fn=(
                lambda run_id: self._continue_recovery_contract(run_id)
            ),
        )
        self.approval_control_service = ApprovalControlService(
            resolve_approval_request_fn=(
                self.wait_coordinator.resolve_approval_request
            ),
        )
        self.tool_resume = (
            OrchestrationToolResumeCoordinator(
                uow_factory=uow_factory,
                engine=engine,
                get_run=self.run_query_service.get_run,
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
        self.scheduler_service = OrchestrationSchedulerService(
            ingress_coordinator=self.ingress_coordinator,
            intake_port=self.intake_service,
            scheduler_signal_coordinator=self.scheduler_signal_coordinator,
            get_run_fn=self.run_query_service.get_run,
            assign_next_assignment_fn=self._assign_next_assignment,
            recover_abandoned_runs_fn=self._recover_abandoned_runs,
            expire_executor_leases_fn=self._expire_executor_leases,
            handle_recovered_dispatch_task_fn=self._handle_recovered_dispatch_task,
            handle_terminal_tool_run_fn=self._handle_terminal_tool_run,
            process_sessions_spawn_followup_fn=(
                lambda child_run_id: self.sessions_spawn_followup_service.process_child_completion(
                    child_run_id,
                )
            ),
            request_compaction_fn=self._request_compaction,
            request_heartbeat_fn=self._request_heartbeat,
            request_memory_flush_fn=self._request_memory_flush,
            request_due_heartbeats_fn=self._request_due_heartbeats,
            resume_run_fn=self._resume_run,
            fail_assignment_fn=self._fail_assignment,
            events_service=events_service,
        )
        self.sessions_spawn_followup_service = SessionsSpawnFollowupService(
            session_service=session_service,
            get_run=self.run_query_service.get_run,
            submit_bound_turn=self.scheduler_service.submit_bound_turn,
            queue_followup_signal=(
                lambda child_run_id: self.scheduler_service.queue_sessions_spawn_followup_signal(
                    child_run_id=child_run_id,
                )
            ),
        )

    def get_run(self, run_id: str) -> OrchestrationRun:
        return self.run_query_service.get_run(run_id)

    def preview_prompt(self, run_id: str) -> PromptPreview:
        return self.inspection_service.preview_prompt(run_id)

    def resolve_tools(self, run: OrchestrationRun) -> ResolvedToolSet:
        return self.inspection_service.resolve_tools(run)

    def decide_tool_execution(
        self,
        run: OrchestrationRun,
        *,
        tool: Tool,
        target: ToolExecutionTarget,
    ) -> ToolExecutionDecision:
        return self.inspection_service.decide_tool_execution(
            run,
            tool=tool,
            target=target,
        )

    def set_memory_flush_transcript_max_chars(self, max_chars: int) -> None:
        self.inspection_service.set_memory_flush_transcript_max_chars(max_chars)

    def list_runs(
        self,
        *,
        status: OrchestrationRunStatus | None = None,
    ) -> list[OrchestrationRun]:
        return self.run_query_service.list_runs(status=status)

    def resolve_approval_request(
        self,
        data: ResolveApprovalRequestInput,
    ) -> OrchestrationRun:
        return self.approval_control_service.resolve_approval_request(data)

    def _assign_next_assignment(self) -> OrchestrationRun | None:
        return self.lease_manager.assign_next_assignment()

    def _process_next_assigned_assignment(
        self,
        *,
        worker_id: str,
        exclude_run_ids: tuple[str, ...] = (),
    ) -> OrchestrationRun | None:
        return self.progress_coordinator.process_next_assigned_assignment(
            worker_id=worker_id,
            exclude_run_ids=exclude_run_ids,
        )

    def _next_assigned_assignment(
        self,
        *,
        worker_id: str,
        exclude_run_ids: tuple[str, ...] = (),
    ) -> OrchestrationRun | None:
        return self.progress_coordinator.next_assigned_assignment(
            worker_id=worker_id,
            exclude_run_ids=exclude_run_ids,
        )

    def _process_assigned_assignment(
        self,
        *,
        run_id: str,
        worker_id: str,
    ) -> OrchestrationRun:
        return self.progress_coordinator.process_assigned_assignment(
            run_id=run_id,
            worker_id=worker_id,
        )

    async def _process_assigned_assignment_async(
        self,
        *,
        run_id: str,
        worker_id: str,
    ) -> OrchestrationRun:
        return await self.progress_coordinator.process_assigned_assignment_async(
            run_id=run_id,
            worker_id=worker_id,
        )

    def _advance_assignment(self, data: AdvanceAssignmentInput) -> OrchestrationRun:
        return self.progress_coordinator.advance_assignment(data)

    def _wait_assignment_on_tool(self, data: WaitAssignmentOnToolInput) -> OrchestrationRun:
        run = self.wait_coordinator.wait_assignment_on_tool(data)
        self.lease_manager.release_executor_assignment(worker_id=data.worker_id)
        return run

    def _wait_for_confirmation(
        self,
        data: WaitForConfirmationInput,
    ) -> OrchestrationRun:
        run = self.wait_coordinator.wait_for_confirmation(data)
        self.lease_manager.release_executor_assignment(worker_id=data.worker_id)
        return run

    def _heartbeat_assignment(
        self,
        run_id: str,
        *,
        worker_id: str,
    ) -> OrchestrationRun:
        return self.lease_manager.heartbeat_assignment(
            run_id,
            worker_id=worker_id,
            get_run=self._get_run,
        )

    def _resume_run(self, data: ResumeOrchestrationRunInput) -> OrchestrationRun:
        return self.wait_coordinator.resume_run(data)

    def _complete_assignment(self, data: CompleteAssignmentInput) -> OrchestrationRun:
        completed = self.progress_coordinator.complete_assignment(data)
        self.lease_manager.release_executor_assignment(worker_id=data.worker_id)
        self.sessions_spawn_followup_service.queue_child_completion_signal(completed)
        return completed

    def _fail_assignment(self, data: FailAssignmentInput) -> OrchestrationRun:
        current_run = self.get_run(data.run_id)
        if current_run.status in {
            OrchestrationRunStatus.COMPLETED,
            OrchestrationRunStatus.FAILED,
            OrchestrationRunStatus.CANCELLED,
        }:
            return current_run
        release_worker_id = (
            (data.worker_id or current_run.worker_id)
            if current_run.status is OrchestrationRunStatus.RUNNING
            else None
        )
        failed = self.progress_coordinator.fail_assignment(data)
        if release_worker_id is not None:
            self.lease_manager.release_executor_assignment(worker_id=release_worker_id)
        return failed

    def _continue_recovery_contract(self, run_id: str) -> OrchestrationRun:
        return self.wait_coordinator.continue_recovery_contract(run_id)

    def _request_compaction(self, data: RequestCompactionInput) -> OrchestrationRun:
        return self.request_coordinator.request_compaction(data)

    def _request_heartbeat(self, data: RequestHeartbeatInput) -> OrchestrationRun:
        return self.request_coordinator.request_heartbeat(data)

    def _request_memory_flush(self, data: RequestMemoryFlushInput) -> OrchestrationRun:
        return self.request_coordinator.request_memory_flush(data)

    def _request_due_heartbeats(
        self,
        data: RequestDueHeartbeatsInput,
    ) -> list[OrchestrationRun]:
        return self.request_coordinator.request_due_heartbeats(data)

    def _recover_abandoned_runs(self) -> list[OrchestrationRun]:
        return self.recovery_coordinator.recover_abandoned_runs()

    def _expire_executor_leases(self) -> list[OrchestrationExecutorLease]:
        return self.recovery_coordinator.expire_executor_leases()

    def _handle_recovered_dispatch_task(
        self,
        *,
        orchestration_run_id: str,
        reason: str,
    ) -> OrchestrationRun | None:
        return self.recovery_coordinator.handle_recovered_dispatch_task(
            orchestration_run_id=orchestration_run_id,
            reason=reason,
        )

    def _handle_terminal_tool_run(self, tool_run_id: str) -> list[OrchestrationRun]:
        return self.recovery_coordinator.handle_terminal_tool_run(tool_run_id)

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

    def _admit_assignment(
        self,
        *,
        run_id: str,
        worker_id: str,
        acquire_lane_lock: bool = True,
    ) -> OrchestrationRun:
        return self.lease_manager.admit_assignment(
            run_id,
            worker_id=worker_id,
            get_run=self._get_run,
            acquire_lane_lock=acquire_lane_lock,
        )

    @staticmethod
    def _session_start_prompt_flow_hint(
        bundle: ResolvedSessionBundle,
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
