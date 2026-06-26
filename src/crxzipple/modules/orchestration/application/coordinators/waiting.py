from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Protocol

from crxzipple.modules.dispatch.domain import DispatchTaskRepository
from crxzipple.modules.orchestration.application.coordinators.execution_payloads import (
    continuation_payload,
    llm_step_summary,
    tool_run_links,
)
from crxzipple.modules.orchestration.application.coordinators.waiting_approval_recovery import (
    RunWaitApprovalRecoveryMixin,
)
from crxzipple.modules.orchestration.application.coordinators.waiting_recovery_payloads import (
    approval_llm_invocation_id,
    approval_recovery_contract_payload,
    recovery_contract_payload,
    resume_reason_from_tool_runs,
    tool_wait_recovery_contract_payload,
)
from crxzipple.modules.orchestration.application.engine import OrchestrationEngine
from crxzipple.modules.orchestration.application.execution_chain_lifecycle import (
    complete_llm_execution_step,
    current_dispatch_task_id,
    mark_approval_request_step_item_terminal,
    materialize_approval_execution_step,
    materialize_resume_execution_step,
    materialize_tool_batch_execution_step,
    materialize_tool_result_session_item_items,
    prepare_dispatch_execution_step,
    require_current_dispatch_task_id,
)
from crxzipple.modules.orchestration.application.ports import (
    OrchestrationDispatchPort,
)
from crxzipple.modules.orchestration.domain import (
    ApprovalDecision,
    ExecutionChainRepository,
    ExecutionStepItemRepository,
    ExecutionStepRepository,
    OrchestrationQueuePolicy,
    OrchestrationRun,
    OrchestrationRunRepository,
    OrchestrationRunStage,
    OrchestrationRunStatus,
    OrchestrationRunWaitRepository,
)
from crxzipple.modules.orchestration.domain.exceptions import (
    OrchestrationRunNotFoundError,
)
from crxzipple.modules.session.application import ListSessionItemsInput
from crxzipple.modules.tool.domain import ToolRun
from crxzipple.shared.domain.aggregates import AggregateRoot
from crxzipple.shared.time import format_datetime_utc

if TYPE_CHECKING:
    from crxzipple.modules.orchestration.application.commands import (
        ResolveApprovalRequestInput,
        ResumeOrchestrationRunInput,
        WaitForConfirmationInput,
        WaitAssignmentOnToolInput,
    )


class WaitCoordinatorUnitOfWork(Protocol):
    execution_chains: ExecutionChainRepository
    execution_steps: ExecutionStepRepository
    execution_step_items: ExecutionStepItemRepository
    orchestration_runs: OrchestrationRunRepository
    orchestration_waits: OrchestrationRunWaitRepository
    dispatch_tasks: DispatchTaskRepository

    def __enter__(self) -> "WaitCoordinatorUnitOfWork":
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


class SessionItemListPort(Protocol):
    def list_items(
        self,
        data: ListSessionItemsInput,
    ) -> list[object]:
        ...


@dataclass(slots=True)
class RunWaitCoordinator(RunWaitApprovalRecoveryMixin):
    uow_factory: Callable[[], WaitCoordinatorUnitOfWork]
    dispatch_port: OrchestrationDispatchPort
    engine: OrchestrationEngine | None
    session_service: SessionItemListPort | None
    agent_service: object | None
    get_run: Callable[[str], OrchestrationRun]
    resume_input_factory: Callable[..., "ResumeOrchestrationRunInput"]
    grant_run_tool_authorization: Callable[..., None]
    grant_session_tool_authorization: Callable[..., None]
    grant_agent_effect_authorization: Callable[..., None]
    append_approval_resolution_message: Callable[..., None]
    reconcile_tool_waits: Callable[[tuple[str, ...]], None]
    continue_recovery_contract_fn: Callable[[str], OrchestrationRun] | None = None

    def wait_assignment_on_tool(self, data: "WaitAssignmentOnToolInput") -> OrchestrationRun:
        with self.uow_factory() as uow:
            run = self._get_run(uow, data.run_id)
            run.wait_on_tool(
                worker_id=data.worker_id,
                pending_tool_run_ids=data.pending_tool_run_ids,
                reason=data.reason,
                happened_at=data.now,
            )
            run.recovery_contract_payload = tool_wait_recovery_contract_payload(
                pending_tool_run_ids=run.pending_tool_run_ids,
                source="tool_wait",
            )
            self.dispatch_port.wait(
                uow.dispatch_tasks,
                uow,
                run,
                dispatch_task_id=require_current_dispatch_task_id(uow, run=run),
            )
            uow.orchestration_waits.replace_tool_waits(
                run.id,
                run.pending_tool_run_ids,
            )
            uow.orchestration_runs.add(run)
            uow.collect(run)
            uow.commit()
        self.reconcile_tool_waits(data.pending_tool_run_ids)
        return self.get_run(data.run_id)

    def wait_for_confirmation(
        self,
        data: "WaitForConfirmationInput",
    ) -> OrchestrationRun:
        with self.uow_factory() as uow:
            run = self._get_run(uow, data.run_id)
            run.wait_for_confirmation(
                worker_id=data.worker_id,
                request=data.request,
                reason=data.reason,
                happened_at=data.now,
            )
            if data.metadata:
                run.metadata.update(data.metadata)
            combined_payload = {
                **data.metadata,
                **data.execution_payload,
                "llm_invocation_id": data.llm_invocation_id,
            }
            complete_llm_execution_step(
                uow,
                run=run,
                llm_invocation_id=data.llm_invocation_id,
                summary_payload=llm_step_summary(
                    combined_payload,
                    include_invocation_id=True,
                ),
                continuation_payload=continuation_payload(combined_payload),
            )
            materialize_tool_batch_execution_step(
                uow,
                run=run,
                llm_invocation_id=data.llm_invocation_id,
                tool_run_links=tool_run_links(data.execution_payload),
            )
            materialize_approval_execution_step(
                uow,
                run=run,
                request=data.request,
            )
            run.recovery_contract_payload = approval_recovery_contract_payload(
                request=data.request,
                state="pending_decision",
                llm_invocation_id=data.llm_invocation_id,
            )
            self.dispatch_port.wait(
                uow.dispatch_tasks,
                uow,
                run,
                dispatch_task_id=require_current_dispatch_task_id(uow, run=run),
            )
            uow.orchestration_waits.delete_for_run(run.id)
            uow.orchestration_runs.add(run)
            uow.collect(run)
            uow.commit()
            return run

    def resume_run(self, data: "ResumeOrchestrationRunInput") -> OrchestrationRun:
        with self.uow_factory() as uow:
            run = self._get_run(uow, data.run_id)
            if data.metadata:
                run.metadata.update(data.metadata)
            previous_dispatch_task_id = current_dispatch_task_id(uow, run=run)
            materialize_resume_execution_step(
                uow,
                run=run,
                reason=data.reason,
            )
            run.resume(
                lane_key=data.lane_key,
                queue_policy=data.queue_policy,
                priority=data.priority,
                reason=data.reason,
                clear_pending_tool_run_ids=data.clear_pending_tool_run_ids,
                happened_at=data.now,
            )
            if previous_dispatch_task_id is not None:
                self.dispatch_port.complete(
                    uow.dispatch_tasks,
                    uow,
                    run,
                    dispatch_task_id=previous_dispatch_task_id,
                )
            dispatch_step = prepare_dispatch_execution_step(uow, run=run)
            self.dispatch_port.enqueue(
                uow.dispatch_tasks,
                uow,
                run,
                dispatch_task_id=dispatch_step.step.dispatch_task_id
                or dispatch_step.step.id,
            )
            uow.orchestration_waits.delete_for_run(run.id)
            uow.orchestration_runs.add(run)
            uow.collect(run)
            uow.commit()
            return run

    def resolve_approval_request(
        self,
        data: "ResolveApprovalRequestInput",
    ) -> OrchestrationRun:
        if self.session_service is None:
            raise RuntimeError("Orchestration session service is not configured.")
        if self.agent_service is None:
            raise RuntimeError("Orchestration agent service is not configured.")

        with self.uow_factory() as uow:
            run = self._get_run(uow, data.run_id)
            current_contract = recovery_contract_payload(run) or {}
            pending_request = run.resolve_approval_request(
                request_id=data.request_id,
                decision=data.decision,
                happened_at=data.now,
            )
            mark_approval_request_step_item_terminal(
                uow,
                request_id=pending_request.request_id,
                decision=data.decision.value,
            )
            run.recovery_contract_payload = approval_recovery_contract_payload(
                request=pending_request,
                state=(
                    "resolved_deny_pending_resume"
                    if data.decision is ApprovalDecision.DENY
                    else "resolved_allow_pending_replay"
                ),
                decision=data.decision,
                llm_invocation_id=approval_llm_invocation_id(current_contract),
            )
            uow.orchestration_runs.add(run)
            uow.collect(run)
            uow.commit()

        if data.decision is ApprovalDecision.ALLOW_ONCE:
            self.grant_run_tool_authorization(
                run_id=data.run_id,
                approval_request_id=pending_request.request_id,
                effect_ids=(pending_request.effect_id,),
                tool_ids=pending_request.tool_ids,
            )
        elif data.decision is ApprovalDecision.ALLOW_FOR_SESSION:
            self.grant_session_tool_authorization(
                run_id=data.run_id,
                approval_request_id=pending_request.request_id,
                effect_ids=(pending_request.effect_id,),
                tool_ids=pending_request.tool_ids,
            )
        elif data.decision is ApprovalDecision.ALWAYS_FOR_AGENT:
            self.grant_agent_effect_authorization(
                run_id=data.run_id,
                effect_ids=(pending_request.effect_id,),
            )

        self.append_approval_resolution_message(
            run_id=data.run_id,
            request=pending_request,
            decision=data.decision,
        )
        continuation = self.continue_recovery_contract_fn or self.continue_recovery_contract
        return continuation(data.run_id)

    def continue_recovery_contract(self, run_id: str) -> OrchestrationRun:
        run = self.get_run(run_id)
        contract = recovery_contract_payload(run)
        if contract is None:
            return run
        kind = str(contract.get("kind", "")).strip().lower()
        if kind == "approval":
            return self._continue_approval_recovery(run, contract)
        if kind == "tool_wait":
            return self._continue_tool_wait_recovery(run, contract)
        return run

    def resume_after_tool_completion(
        self,
        run_id: str,
        queue_policy: OrchestrationQueuePolicy,
        reason: str,
        *,
        metadata: dict[str, object] | None = None,
    ) -> OrchestrationRun:
        resume_metadata = {
            **dict(metadata or {}),
            "runtime_request_flow_hint": {
                "mode": "recovery_resume",
                "reason": reason,
            },
        }
        return self.resume_run(
            self.resume_input_factory(
                run_id=run_id,
                queue_policy=queue_policy,
                reason=reason,
                metadata=resume_metadata,
            ),
        )

    def _continue_tool_wait_recovery(
        self,
        run: OrchestrationRun,
        contract: dict[str, object],
    ) -> OrchestrationRun:
        if run.status is not OrchestrationRunStatus.WAITING:
            return run
        if run.stage is not OrchestrationRunStage.WAITING_ON_TOOL:
            return run
        if self.engine is None:
            return run
        pending_tool_run_ids = tuple(
            tool_run_id
            for tool_run_id in run.pending_tool_run_ids
            if tool_run_id is not None and tool_run_id.strip()
        )
        if not pending_tool_run_ids:
            return run
        pending_tool_runs = tuple(
            self.engine.tool_execution_port.get_tool_run(tool_run_id)
            for tool_run_id in pending_tool_run_ids
        )
        self._mark_terminal_tool_runs(
            tuple(tool_run for tool_run in pending_tool_runs if tool_run.is_terminal()),
        )
        if not all(tool_run.is_terminal() for tool_run in pending_tool_runs):
            return run
        item_ids = self.engine.append_completed_background_tool_results(
            run,
            tool_runs=pending_tool_runs,
        )
        self._materialize_tool_result_items(
            run=run,
            tool_runs=pending_tool_runs,
            item_ids=item_ids,
        )
        resumed = self.resume_after_tool_completion(
            run.id,
            OrchestrationQueuePolicy.RESUME_FIRST,
            resume_reason_from_tool_runs(pending_tool_runs),
        )
        self._store_recovery_contract(
            resumed.id,
            {
                **contract,
                "state": "resumed",
                "resumed_at": format_datetime_utc(resumed.updated_at),
            },
        )
        return resumed

    def _materialize_tool_result_items(
        self,
        *,
        run: OrchestrationRun,
        tool_runs: tuple[ToolRun, ...],
        item_ids: tuple[str, ...],
    ) -> None:
        links = tuple(
            (tool_run.id, item_id)
            for tool_run, item_id in zip(tool_runs, item_ids, strict=False)
        )
        if not links:
            return
        with self.uow_factory() as uow:
            materialize_tool_result_session_item_items(
                uow,
                run=run,
                tool_result_item_links=links,
            )
            uow.commit()

    @staticmethod
    def _get_run(
        uow: WaitCoordinatorUnitOfWork,
        run_id: str,
    ) -> OrchestrationRun:
        run = uow.orchestration_runs.get(run_id)
        if run is None:
            raise OrchestrationRunNotFoundError(
                f"Orchestration run '{run_id}' was not found.",
            )
        return run
