from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from crxzipple.modules.orchestration.application.engine import PromptPreview
    from crxzipple.modules.orchestration.application.commands import (
        RequestCompactionInput,
        RequestDueHeartbeatsInput,
        RequestHeartbeatInput,
        RequestMemoryFlushInput,
        ResolveApprovalRequestInput,
        ResumeOrchestrationRunInput,
        SubmitBoundOrchestrationTurnInput,
        SubmitOrchestrationTurnInput,
    )
    from crxzipple.modules.orchestration.application.intake_commands import (
        AcceptOrchestrationRunInput,
        BindSessionInput,
        EnqueueOrchestrationRunInput,
        PrepareSessionRunInput,
        RouteOrchestrationRunInput,
    )
    from crxzipple.modules.orchestration.application.tool_resolver import (
        ResolvedToolSet,
        ToolExecutionDecision,
    )
    from crxzipple.modules.orchestration.domain import (
        OrchestrationExecutorLease,
        OrchestrationExecutorLeaseStatus,
        OrchestrationRun,
        OrchestrationRunStage,
        OrchestrationRunStatus,
    )
    from crxzipple.modules.tool.domain import Tool, ToolExecutionTarget


class OrchestrationSchedulerSubmitPort(Protocol):
    def submit_turn(
        self,
        data: "SubmitOrchestrationTurnInput",
        *,
        inline_worker_id: str | None = None,
    ) -> "OrchestrationRun":
        ...

    def submit_bound_turn(
        self,
        data: "SubmitBoundOrchestrationTurnInput",
        *,
        inline_worker_id: str | None = None,
    ) -> "OrchestrationRun":
        ...

    def process_run_request(
        self,
        *,
        run_id: str,
        worker_id: str,
    ) -> "OrchestrationRun | None":
        ...


class OrchestrationSchedulerMaintenancePort(Protocol):
    def request_compaction(
        self,
        data: "RequestCompactionInput",
    ) -> "OrchestrationRun":
        ...

    def request_heartbeat(
        self,
        data: "RequestHeartbeatInput",
    ) -> "OrchestrationRun":
        ...

    def request_memory_flush(
        self,
        data: "RequestMemoryFlushInput",
    ) -> "OrchestrationRun":
        ...

    def request_due_heartbeats(
        self,
        data: "RequestDueHeartbeatsInput",
    ) -> "list[OrchestrationRun]":
        ...

    def recover_abandoned_runs(self) -> "list[OrchestrationRun]":
        ...

    def expire_executor_leases(self) -> "list[OrchestrationExecutorLease]":
        ...

    def assign_next_assignment(self) -> "OrchestrationRun | None":
        ...

    def resume_run(self, data: "ResumeOrchestrationRunInput") -> "OrchestrationRun":
        ...


class OrchestrationSchedulerRuntimePort(
    OrchestrationSchedulerSubmitPort,
    OrchestrationSchedulerMaintenancePort,
    Protocol,
):
    pass


class OrchestrationRunLookupPort(Protocol):
    def get_run(self, run_id: str) -> "OrchestrationRun":
        ...


class OrchestrationRunQueryPort(OrchestrationRunLookupPort, Protocol):
    def list_runs(
        self,
        *,
        status: "OrchestrationRunStatus | None" = None,
    ) -> "list[OrchestrationRun]":
        ...


class OrchestrationInspectionPort(Protocol):
    def preview_prompt(self, run_id: str) -> "PromptPreview":
        ...

    def resolve_tools(self, run: "OrchestrationRun") -> "ResolvedToolSet":
        ...

    def decide_tool_execution(
        self,
        run: "OrchestrationRun",
        *,
        tool: "Tool",
        target: "ToolExecutionTarget",
    ) -> "ToolExecutionDecision":
        ...

    def set_memory_flush_transcript_max_chars(self, max_chars: int) -> None:
        ...


class OrchestrationApprovalControlPort(Protocol):
    def resolve_approval_request(
        self,
        data: "ResolveApprovalRequestInput",
    ) -> "OrchestrationRun":
        ...


class OrchestrationCancellationPort(Protocol):
    def cancel_run(
        self,
        run_id: str,
        *,
        reason: str | None = None,
    ) -> "OrchestrationRun":
        ...

    def cancel_session_tree(
        self,
        session_key: str,
        *,
        reason: str | None = None,
    ) -> "dict[str, object]":
        ...


class OrchestrationSchedulerIntakePort(Protocol):
    def accept(self, data: "AcceptOrchestrationRunInput") -> "OrchestrationRun":
        ...

    def route(
        self,
        data: "RouteOrchestrationRunInput",
    ) -> "OrchestrationRun":
        ...

    def bind_session(
        self,
        data: "BindSessionInput",
    ) -> "OrchestrationRun":
        ...

    def prepare_session_run(
        self,
        data: "PrepareSessionRunInput",
    ) -> "OrchestrationRun":
        ...

    def enqueue(self, data: "EnqueueOrchestrationRunInput") -> "OrchestrationRun":
        ...


class OrchestrationExecutorProcessPort(Protocol):
    def process_next_available(
        self,
        *,
        worker_id: str,
        exclude_run_ids: tuple[str, ...] = (),
    ) -> "OrchestrationRun | None":
        ...

    def process_assignment_inline(
        self,
        *,
        run_id: str,
        worker_id: str,
        acquire_lane_lock: bool = True,
    ) -> "OrchestrationRun":
        ...

    def process_next_assigned_assignment(
        self,
        *,
        worker_id: str,
        exclude_run_ids: tuple[str, ...] = (),
    ) -> "OrchestrationRun | None":
        ...

    def next_assigned_assignment(
        self,
        *,
        worker_id: str,
        exclude_run_ids: tuple[str, ...] = (),
    ) -> "OrchestrationRun | None":
        ...

    def process_assigned_assignment(
        self,
        *,
        run_id: str,
        worker_id: str,
    ) -> "OrchestrationRun":
        ...

    async def process_assigned_assignment_async(
        self,
        *,
        run_id: str,
        worker_id: str,
    ) -> "OrchestrationRun":
        ...


class OrchestrationExecutorControlPort(OrchestrationExecutorProcessPort, Protocol):
    def heartbeat_executor(
        self,
        *,
        worker_id: str,
        max_inflight_assignments: int | None = None,
        inflight_assignment_count: int | None = None,
        draining: bool | None = None,
        metadata: dict[str, object] | None = None,
    ) -> "OrchestrationExecutorLease":
        ...

    def list_executor_leases(
        self,
        *,
        status: "OrchestrationExecutorLeaseStatus | None" = None,
    ) -> "list[OrchestrationExecutorLease]":
        ...

    def admit_assignment(
        self,
        *,
        run_id: str,
        worker_id: str,
        acquire_lane_lock: bool = True,
    ) -> "OrchestrationRun":
        ...

    def heartbeat_assignment(
        self,
        *,
        run_id: str,
        worker_id: str,
    ) -> "OrchestrationRun":
        ...

    def advance_assignment(
        self,
        *,
        run_id: str,
        worker_id: str,
        stage: "OrchestrationRunStage",
        step_increment: int = 0,
        metadata: dict[str, object] | None = None,
    ) -> "OrchestrationRun":
        ...

    def wait_assignment_on_tool(
        self,
        *,
        run_id: str,
        worker_id: str,
        pending_tool_run_ids: tuple[str, ...],
        reason: str | None = None,
    ) -> "OrchestrationRun":
        ...

    def complete_assignment(
        self,
        *,
        run_id: str,
        worker_id: str,
        result_payload: dict[str, object] | None = None,
    ) -> "OrchestrationRun":
        ...

    def fail_assignment(
        self,
        *,
        run_id: str,
        message: str,
        code: str = "orchestration_failed",
        details: dict[str, object] | None = None,
        worker_id: str | None = None,
    ) -> "OrchestrationRun":
        ...

    def run_until_stopped(
        self,
        *,
        worker_id: str,
        poll_interval_seconds: float,
        max_runs: int | None = None,
        max_idle_cycles: int | None = None,
        stop_event: object | None = None,
        max_concurrent_assignments: int = 1,
    ) -> int:
        ...

    async def run_until_stopped_async(
        self,
        *,
        worker_id: str,
        poll_interval_seconds: float,
        max_runs: int | None = None,
        max_idle_cycles: int | None = None,
        stop_event: object | None = None,
        max_concurrent_assignments: int = 1,
    ) -> int:
        ...
