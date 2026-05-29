"""Composition graph for orchestration application services."""

from __future__ import annotations

from typing import Callable

from crxzipple.modules.memory.application import MemoryRuntimePort
from crxzipple.modules.orchestration.application.approval import (
    ApprovalControlService,
    ApprovalResolutionService,
)
from crxzipple.modules.orchestration.application.assignment_lifecycle import (
    RunAssignmentLifecycleService,
)
from crxzipple.modules.orchestration.application.cancellation import (
    RunCancellationService,
)
from crxzipple.modules.orchestration.application.commands import (
    RequestHeartbeatInput,
    ResolveApprovalRequestInput,
    ResumeOrchestrationRunInput,
)
from crxzipple.modules.orchestration.application.coordinators import (
    RunIngressCoordinator,
    RunProgressCoordinator,
    RunRecoveryCoordinator,
    RunRequestCoordinator,
    RunSchedulerSignalCoordinator,
    RunWaitCoordinator,
)
from crxzipple.modules.orchestration.application.engine import (
    OrchestrationEngine,
    PromptSurfacePreview,
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
    build_run_intake_coordinator,
)
from crxzipple.modules.orchestration.application.lease_manager import (
    OrchestrationLeaseManager,
)
from crxzipple.modules.orchestration.application.maintenance import (
    OrchestrationMaintenanceService,
)
from crxzipple.modules.orchestration.application.ports import (
    AgentProfileCatalogPort,
    AuthorizationPort,
    EventBusPort,
    LlmPort,
    OrchestrationSessionPort,
    RunDispatchPort,
    SessionResolutionPort,
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
from crxzipple.modules.orchestration.domain.entities import OrchestrationRun
from crxzipple.modules.orchestration.domain.value_objects import (
    OrchestrationRunStatus,
)
from crxzipple.modules.tool.domain import Tool, ToolExecutionTarget
from crxzipple.shared.runtime_metrics import (
    RuntimeMetricsRegistry,
    get_runtime_metrics_registry,
)


class OrchestrationServiceGraph:
    """Owns the wiring between orchestration scheduler, executor, and side services."""

    def __init__(
        self,
        uow_factory: Callable[[], OrchestrationUnitOfWork],
        *,
        scheduler: OrchestrationScheduler | None = None,
        dispatch_port: RunDispatchPort | None = None,
        agent_service: AgentProfileCatalogPort | None = None,
        authorization_port: AuthorizationPort | None = None,
        llm_port: LlmPort | None = None,
        memory_port: MemoryRuntimePort | None = None,
        session_service: OrchestrationSessionPort | None = None,
        session_resolution_service: SessionResolutionPort | None = None,
        engine: OrchestrationEngine | None = None,
        worker_lease_seconds: int = 30,
        worker_heartbeat_seconds: float = 5.0,
        auto_compaction_enabled: bool = True,
        auto_compaction_reserve_tokens: int = 20_000,
        auto_compaction_soft_threshold_tokens: int = 4_000,
        events_service: EventBusPort | None = None,
        runtime_metrics: RuntimeMetricsRegistry | None = None,
        run_query_service: OrchestrationRunQueryService | None = None,
    ) -> None:
        if dispatch_port is None:
            raise RuntimeError("Orchestration dispatch port is not configured.")
        self.run_query_service = run_query_service or OrchestrationRunQueryService(
            uow_factory,
        )
        scheduler_instance = scheduler or OrchestrationScheduler()
        if session_resolution_service is None:
            raise RuntimeError("Session resolution service is not configured.")
        dispatch = dispatch_port
        metrics = runtime_metrics or get_runtime_metrics_registry()
        self.inspection_service = OrchestrationInspectionService(
            engine=engine,
            get_run=self.run_query_service.get_run,
        )

        self.ingress_coordinator = RunIngressCoordinator(uow_factory=uow_factory)
        self.scheduler_signal_coordinator = RunSchedulerSignalCoordinator(
            uow_factory=uow_factory,
        )
        self.intake_coordinator = build_run_intake_coordinator(
            uow_factory=uow_factory,
            scheduler=scheduler_instance,
            dispatch_port=dispatch,
            resolve_session_bundle=session_resolution_service.resolve,
        )
        self.intake_service = OrchestrationIntakeService(
            coordinator=self.intake_coordinator,
        )
        self.request_coordinator = RunRequestCoordinator(
            uow_factory=uow_factory,
            scheduler=scheduler_instance,
            dispatch_port=dispatch,
            session_service=session_service,
            request_heartbeat_input_factory=lambda **kwargs: RequestHeartbeatInput(
                **kwargs,
            ),
        )
        self.lease_manager = OrchestrationLeaseManager(
            uow_factory=uow_factory,
            dispatch_port=dispatch,
            worker_lease_seconds=worker_lease_seconds,
            worker_heartbeat_seconds=worker_heartbeat_seconds,
        )
        self.assignment_lifecycle = RunAssignmentLifecycleService(
            uow_factory=uow_factory,
            lease_manager=self.lease_manager,
            get_run=self.run_query_service.get_run,
            progress_coordinator=lambda: self.progress_coordinator,
            wait_coordinator=lambda: self.wait_coordinator,
            queue_child_completion_signal=(
                lambda run: self.sessions_spawn_followup_service.queue_child_completion_signal(
                    run,
                )
            ),
        )
        self.maintenance_service = OrchestrationMaintenanceService(
            uow_factory=uow_factory,
            engine=engine,
            session_service=session_service,
            llm_port=llm_port,
            request_coordinator=self.request_coordinator,
            request_memory_flush=self.request_coordinator.request_memory_flush,
            request_compaction=self.request_coordinator.request_compaction,
            fail_assignment=self.assignment_lifecycle.fail_assignment,
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
            advance_assignment=self.assignment_lifecycle.advance_assignment,
            wait_assignment_on_tool=self.assignment_lifecycle.wait_assignment_on_tool,
            wait_for_confirmation=self.assignment_lifecycle.wait_for_confirmation,
            complete_assignment=self.assignment_lifecycle.complete_assignment,
            fail_assignment=self.assignment_lifecycle.fail_assignment,
            clear_prompt_flow_hint=self.assignment_lifecycle.clear_prompt_flow_hint,
            events_service=events_service,
            metrics=metrics,
        )
        self.executor_service = OrchestrationExecutorService(
            uow_factory=uow_factory,
            events_service=events_service,
            worker_lease_seconds=worker_lease_seconds,
            lease_manager=self.lease_manager,
            admit_assignment_fn=self.assignment_lifecycle.admit_assignment,
            advance_once_fn=self.execution_service.advance_once,
            next_assigned_assignment_fn=(
                self.assignment_lifecycle.next_assigned_assignment
            ),
            process_assigned_assignment_fn=(
                self.assignment_lifecycle.process_assigned_assignment
            ),
            process_assigned_assignment_async_fn=(
                self.assignment_lifecycle.process_assigned_assignment_async
            ),
            process_next_assigned_assignment_fn=(
                self.assignment_lifecycle.process_next_assigned_assignment
            ),
            heartbeat_assignment_fn=self.assignment_lifecycle.heartbeat_assignment,
            advance_assignment_fn=self.assignment_lifecycle.advance_assignment,
            wait_assignment_on_tool_fn=self.assignment_lifecycle.wait_assignment_on_tool,
            complete_assignment_fn=self.assignment_lifecycle.complete_assignment,
            fail_assignment_fn=self.assignment_lifecycle.fail_assignment,
        )
        self.progress_coordinator = RunProgressCoordinator(
            uow_factory=uow_factory,
            dispatch_port=dispatch,
            lease_manager=self.lease_manager,
            advance_once=lambda run_id, worker_id: self.execution_service.advance_once(
                run_id=run_id,
                worker_id=worker_id,
            ),
            advance_once_async=lambda run_id, worker_id: self.execution_service.advance_once_async(
                run_id=run_id,
                worker_id=worker_id,
            ),
            heartbeat_assignment=self.assignment_lifecycle.heartbeat_assignment,
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
            dispatch_port=dispatch,
            engine=engine,
            session_service=session_service,
            agent_service=agent_service,
            get_run=self.run_query_service.get_run,
            resume_input_factory=lambda **kwargs: ResumeOrchestrationRunInput(
                **kwargs,
            ),
            grant_run_tool_authorization=(
                self.approval_service.grant_run_tool_authorization
            ),
            grant_session_tool_authorization=(
                self.approval_service.grant_session_tool_authorization
            ),
            grant_agent_effect_authorization=(
                self.approval_service.grant_agent_effect_authorization
            ),
            append_approval_resolution_message=(
                self.approval_service.append_resolution_message
            ),
            reconcile_tool_waits=(
                lambda tool_run_ids: self.recovery_coordinator.reconcile_tool_waits(
                    tool_run_ids,
                )
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
            continue_recovery_contract=self.wait_coordinator.continue_recovery_contract,
            tool_resume=self.tool_resume,
        )
        self.scheduler_service = OrchestrationSchedulerService(
            ingress_coordinator=self.ingress_coordinator,
            intake_port=self.intake_service,
            scheduler_signal_coordinator=self.scheduler_signal_coordinator,
            get_run_fn=self.run_query_service.get_run,
            assign_next_assignment_fn=self.lease_manager.assign_next_assignment,
            recover_abandoned_runs_fn=self.recovery_coordinator.recover_abandoned_runs,
            expire_executor_leases_fn=self.recovery_coordinator.expire_executor_leases,
            handle_recovered_dispatch_task_fn=(
                self.recovery_coordinator.handle_recovered_dispatch_task
            ),
            handle_terminal_tool_run_fn=self.recovery_coordinator.handle_terminal_tool_run,
            process_sessions_spawn_followup_fn=(
                lambda child_run_id: self.sessions_spawn_followup_service.process_child_completion(
                    child_run_id,
                )
            ),
            request_compaction_fn=self.request_coordinator.request_compaction,
            request_heartbeat_fn=self.request_coordinator.request_heartbeat,
            request_memory_flush_fn=self.request_coordinator.request_memory_flush,
            request_due_heartbeats_fn=self.request_coordinator.request_due_heartbeats,
            resume_run_fn=self.wait_coordinator.resume_run,
            fail_assignment_fn=self.assignment_lifecycle.fail_assignment,
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

    def preview_prompt(self, run_id: str) -> PromptSurfacePreview:
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
