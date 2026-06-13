from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Protocol

from crxzipple.modules.dispatch.domain import DispatchTaskRepository
from crxzipple.modules.llm.domain import ToolCallIntent
from crxzipple.modules.orchestration.application.engine import OrchestrationEngine
from crxzipple.modules.orchestration.application.execution_chain_lifecycle import (
    complete_llm_execution_step,
    current_dispatch_task_id,
    fail_active_execution_step,
    mark_approval_request_step_item_terminal,
    mark_tool_run_step_item_terminal,
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
    PendingApprovalRequest,
)
from crxzipple.modules.orchestration.domain.exceptions import (
    OrchestrationRunNotFoundError,
    OrchestrationValidationError,
)
from crxzipple.modules.session.application import ListSessionItemsInput
from crxzipple.modules.session.domain import SessionItemKind
from crxzipple.modules.tool.domain import ToolError, ToolRun, ToolRunStatus
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
    def list_model_visible_items(
        self,
        data: ListSessionItemsInput,
    ) -> list[object]:
        ...


@dataclass(slots=True)
class RunWaitCoordinator:
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
            run.recovery_contract_payload = self._tool_wait_recovery_contract_payload(
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
                summary_payload=_llm_step_summary(combined_payload),
                continuation_payload=_continuation_payload(combined_payload),
            )
            materialize_tool_batch_execution_step(
                uow,
                run=run,
                llm_invocation_id=data.llm_invocation_id,
                tool_run_links=_tool_run_links(data.execution_payload),
            )
            materialize_approval_execution_step(
                uow,
                run=run,
                request=data.request,
            )
            run.recovery_contract_payload = self._approval_recovery_contract_payload(
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
            current_contract = self._recovery_contract_payload(run) or {}
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
            run.recovery_contract_payload = self._approval_recovery_contract_payload(
                request=pending_request,
                state=(
                    "resolved_deny_pending_resume"
                    if data.decision is ApprovalDecision.DENY
                    else "resolved_allow_pending_replay"
                ),
                decision=data.decision,
                llm_invocation_id=_approval_llm_invocation_id(current_contract),
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
        contract = self._recovery_contract_payload(run)
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
    ) -> OrchestrationRun:
        return self.resume_run(
            self.resume_input_factory(
                run_id=run_id,
                queue_policy=queue_policy,
                reason=reason,
                metadata={
                    "prompt_flow_hint": {
                        "mode": "recovery_resume",
                        "reason": reason,
                    },
                },
            ),
        )

    def _wait_on_replayed_background_tools(
        self,
        *,
        run_id: str,
        background_runs: tuple[tuple[ToolCallIntent, ToolRun], ...],
    ) -> OrchestrationRun:
        pending_tool_run_ids = tuple(tool_run.id for _, tool_run in background_runs)
        with self.uow_factory() as uow:
            run = self._get_run(uow, run_id)
            run.recovery_contract_payload = self._tool_wait_recovery_contract_payload(
                pending_tool_run_ids=pending_tool_run_ids,
                source="approval_replay",
            )
            run.wait_on_tool_after_confirmation(
                pending_tool_run_ids=pending_tool_run_ids,
                reason="tool_background_wait",
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
        self.reconcile_tool_waits(pending_tool_run_ids)
        return self.get_run(run_id)

    def _continue_approval_recovery(
        self,
        run: OrchestrationRun,
        contract: dict[str, object],
    ) -> OrchestrationRun:
        if self.engine is None:
            return run
        if run.status is not OrchestrationRunStatus.WAITING:
            return run
        if run.stage is not OrchestrationRunStage.WAITING_FOR_CONFIRMATION:
            return run
        request_payload = contract.get("request")
        if not isinstance(request_payload, dict):
            return run
        state = str(contract.get("state", "")).strip().lower()
        decision_raw = contract.get("decision")
        decision = (
            ApprovalDecision(str(decision_raw))
            if isinstance(decision_raw, str) and decision_raw.strip()
            else None
        )
        request = PendingApprovalRequest.from_payload(request_payload)
        if decision is ApprovalDecision.DENY or state == "resolved_deny_pending_resume":
            return self._resume_after_approval_resolution(
                run_id=run.id,
                request=request,
                decision=ApprovalDecision.DENY,
            )
        if decision is None:
            return run
        if state == "inline_replayed_pending_resume":
            return self._resume_after_approval_resolution(
                run_id=run.id,
                request=request,
                decision=decision,
            )
        if state == "background_replayed_pending_wait":
            return self._wait_on_replayed_background_tools_from_contract(
                run_id=run.id,
                contract=contract,
            )
        if state != "resolved_allow_pending_replay":
            return run
        existing_tool_result_item_ids = self._tool_result_item_ids_for_call(
            run=run,
            tool_call_id=request.request_id,
        )
        if existing_tool_result_item_ids:
            self._store_recovery_contract(
                run.id,
                self._approval_recovery_contract_payload(
                    request=request,
                    state="inline_replayed_pending_resume",
                    decision=decision,
                    tool_result_item_ids=existing_tool_result_item_ids,
                ),
            )
            return self._resume_after_approval_resolution(
                run_id=run.id,
                request=request,
                decision=decision,
            )
        try:
            replay_outcome = self.engine.replay_approved_tool_call(
                self.get_run(run.id),
                request=request,
            )
        except (ToolError, OrchestrationValidationError) as exc:
            return self._fail_approval_replay_recovery(
                run_id=run.id,
                request=request,
                error=exc,
            )
        if replay_outcome.pending_approval_request is not None:
            pending = replay_outcome.pending_approval_request
            return self._fail_approval_replay_recovery(
                run_id=run.id,
                request=request,
                message=(
                    "Approved tool replay requested additional approval instead of "
                    "executing."
                ),
                code="approval_replay_requires_additional_approval",
                details={
                    "run_id": run.id,
                    "approval_request_id": request.request_id,
                    "tool_name": request.tool_name or "",
                    "additional_effect_id": pending.effect_id,
                },
            )
        llm_invocation_id = _approval_llm_invocation_id(contract)
        if llm_invocation_id is not None:
            self._materialize_replayed_tool_batch(
                run_id=run.id,
                llm_invocation_id=llm_invocation_id,
                tool_run_links=tuple(
                    dict(link.to_payload())
                    for link in replay_outcome.tool_run_links
                ),
            )
        if replay_outcome.background_runs:
            pending_tool_run_ids = tuple(
                tool_run.id for _, tool_run in replay_outcome.background_runs
            )
            self._store_recovery_contract(
                run.id,
                self._approval_recovery_contract_payload(
                    request=request,
                    state="background_replayed_pending_wait",
                    decision=decision,
                    pending_tool_run_ids=pending_tool_run_ids,
                    llm_invocation_id=llm_invocation_id,
                ),
            )
            return self._wait_on_replayed_background_tools(
                run_id=run.id,
                background_runs=replay_outcome.background_runs,
            )
        if not replay_outcome.inline_runs and not replay_outcome.background_runs:
            return self._fail_approval_replay_recovery(
                run_id=run.id,
                request=request,
                message="Approved tool replay did not produce a tool run.",
                code="approval_replay_empty",
                details={
                    "run_id": run.id,
                    "approval_request_id": request.request_id,
                    "tool_name": request.tool_name or "",
                },
            )
        replayed_tool_result_item_ids = self._tool_result_item_ids_for_call(
            run=self.get_run(run.id),
            tool_call_id=request.request_id,
        )
        self._store_recovery_contract(
            run.id,
            self._approval_recovery_contract_payload(
                request=request,
                state="inline_replayed_pending_resume",
                decision=decision,
                tool_result_item_ids=replayed_tool_result_item_ids,
                llm_invocation_id=llm_invocation_id,
            ),
        )
        return self._resume_after_approval_resolution(
            run_id=run.id,
            request=request,
            decision=decision,
        )

    def _fail_approval_replay_recovery(
        self,
        *,
        run_id: str,
        request: PendingApprovalRequest,
        error: BaseException | None = None,
        message: str | None = None,
        code: str | None = None,
        details: dict[str, object] | None = None,
    ) -> OrchestrationRun:
        error_message = message or getattr(error, "message", None) or str(error)
        error_code = code or getattr(error, "code", None) or "approval_replay_failed"
        error_details: dict[str, object] = {
            "approval_request_id": request.request_id,
            "tool_name": request.tool_name or "",
            "effect_id": request.effect_id,
        }
        if details:
            error_details.update(details)
        raw_error_details = getattr(error, "details", None)
        if isinstance(raw_error_details, dict):
            error_details.update(raw_error_details)
        if hasattr(error, "to_payload"):
            try:
                payload = error.to_payload()  # type: ignore[attr-defined]
            except Exception:
                payload = None
            if isinstance(payload, dict):
                payload_details = payload.get("details")
                if isinstance(payload_details, dict):
                    error_details.update(payload_details)
                for key, value in payload.items():
                    if key not in {"message", "code", "details"}:
                        error_details[key] = value

        with self.uow_factory() as uow:
            run = self._get_run(uow, run_id)
            if run.status not in {
                OrchestrationRunStatus.RUNNING,
                OrchestrationRunStatus.WAITING,
            }:
                return run
            dispatch_task_id = current_dispatch_task_id(uow, run=run)
            fail_active_execution_step(
                uow,
                run=run,
                message=error_message,
                code=error_code,
                details=error_details,
            )
            run.pending_approval_request_payload = None
            run.recovery_contract_payload = {
                "kind": "approval",
                "state": "replay_failed",
                "request": request.to_payload(),
                "error": {
                    "message": error_message,
                    "code": error_code,
                    "details": dict(error_details),
                },
            }
            run.fail(
                message=error_message,
                code=error_code,
                details=error_details,
            )
            if dispatch_task_id is not None:
                self.dispatch_port.fail(
                    uow.dispatch_tasks,
                    uow,
                    run,
                    dispatch_task_id=dispatch_task_id,
                )
            uow.orchestration_waits.delete_for_run(run.id)
            uow.orchestration_runs.add(run)
            uow.collect(run)
            uow.commit()
            return run

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
            self._resume_reason_from_tool_runs(pending_tool_runs),
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

    def _wait_on_replayed_background_tools_from_contract(
        self,
        *,
        run_id: str,
        contract: dict[str, object],
    ) -> OrchestrationRun:
        raw_pending_tool_run_ids = contract.get("pending_tool_run_ids")
        pending_tool_run_ids = (
            tuple(
                tool_run_id.strip()
                for tool_run_id in raw_pending_tool_run_ids
                if isinstance(tool_run_id, str) and tool_run_id.strip()
            )
            if isinstance(raw_pending_tool_run_ids, list | tuple)
            else ()
        )
        if not pending_tool_run_ids:
            return self.get_run(run_id)
        with self.uow_factory() as uow:
            run = self._get_run(uow, run_id)
            run.recovery_contract_payload = self._tool_wait_recovery_contract_payload(
                pending_tool_run_ids=pending_tool_run_ids,
                source="approval_replay",
            )
            run.wait_on_tool_after_confirmation(
                pending_tool_run_ids=pending_tool_run_ids,
                reason="tool_background_wait",
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
        self.reconcile_tool_waits(pending_tool_run_ids)
        return self.get_run(run_id)

    def _resume_after_approval_resolution(
        self,
        *,
        run_id: str,
        request: PendingApprovalRequest,
        decision: ApprovalDecision,
    ) -> OrchestrationRun:
        return self.resume_run(
            self.resume_input_factory(
                run_id=run_id,
                reason=f"approval_{decision.value}",
                metadata={
                    "prompt_flow_hint": {
                        "mode": (
                            "approval_denied"
                            if decision is ApprovalDecision.DENY
                            else "approval_resume"
                        ),
                        "decision": decision.value,
                        "effect_id": request.effect_id,
                        "label": request.label,
                    },
                },
            ),
        )

    def _store_recovery_contract(
        self,
        run_id: str,
        payload: dict[str, object],
    ) -> OrchestrationRun:
        with self.uow_factory() as uow:
            run = self._get_run(uow, run_id)
            run.recovery_contract_payload = dict(payload)
            uow.orchestration_runs.add(run)
            uow.collect(run)
            uow.commit()
            return run

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

    def _materialize_replayed_tool_batch(
        self,
        *,
        run_id: str,
        llm_invocation_id: str,
        tool_run_links: tuple[dict[str, object], ...],
    ) -> None:
        if not tool_run_links:
            return
        with self.uow_factory() as uow:
            run = self._get_run(uow, run_id)
            materialize_tool_batch_execution_step(
                uow,
                run=run,
                llm_invocation_id=llm_invocation_id,
                tool_run_links=tool_run_links,
            )
            uow.commit()

    @staticmethod
    def _recovery_contract_payload(run: OrchestrationRun) -> dict[str, object] | None:
        return (
            dict(run.recovery_contract_payload)
            if run.recovery_contract_payload is not None
            else None
        )

    @staticmethod
    def _approval_recovery_contract_payload(
        *,
        request: PendingApprovalRequest,
        state: str,
        decision: ApprovalDecision | None = None,
        pending_tool_run_ids: tuple[str, ...] = (),
        tool_result_item_ids: tuple[str, ...] = (),
        llm_invocation_id: str | None = None,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "kind": "approval",
            "state": state,
            "request": request.to_payload(),
        }
        if llm_invocation_id is not None and llm_invocation_id.strip():
            payload["llm_invocation_id"] = llm_invocation_id.strip()
        if decision is not None:
            payload["decision"] = decision.value
        if pending_tool_run_ids:
            payload["pending_tool_run_ids"] = list(pending_tool_run_ids)
        if tool_result_item_ids:
            payload["tool_result_item_ids"] = list(tool_result_item_ids)
        return payload

    @staticmethod
    def _tool_wait_recovery_contract_payload(
        *,
        pending_tool_run_ids: tuple[str, ...],
        source: str,
    ) -> dict[str, object]:
        return {
            "kind": "tool_wait",
            "state": "waiting_on_tool",
            "source": source,
            "pending_tool_run_ids": list(pending_tool_run_ids),
        }

    def _tool_result_item_ids_for_call(
        self,
        *,
        run: OrchestrationRun,
        tool_call_id: str,
    ) -> tuple[str, ...]:
        if self.session_service is None:
            return ()
        session_key = str(run.metadata.get("session_key", "")).strip()
        if (
            not session_key
            or run.active_session_id is None
            or not run.active_session_id.strip()
        ):
            return ()
        list_items = getattr(self.session_service, "list_model_visible_items", None)
        if not callable(list_items):
            return ()
        items = list_items(
            ListSessionItemsInput(
                session_key=session_key,
                active_session_only=True,
                model_visible=True,
            ),
        )
        return tuple(
            item.id
            for item in items
            if item.session_id == run.active_session_id
            and item.kind is SessionItemKind.TOOL_RESULT
            and item.source_kind == "tool_run"
            and str(item.call_id or "").strip() == tool_call_id
        )

    @staticmethod
    def _resume_reason_from_tool_runs(tool_runs: tuple[object, ...]) -> str:
        for tool_run in tool_runs:
            status = getattr(tool_run, "status", None)
            if status is ToolRunStatus.FAILED:
                return "tool_failed_results_ready"
            if status in {
                ToolRunStatus.CANCELLED,
                ToolRunStatus.TIMED_OUT,
            }:
                return "tool_terminal_results_ready"
        return "tool_results_ready"

    def _mark_terminal_tool_runs(self, tool_runs: tuple[object, ...]) -> None:
        if not tool_runs:
            return
        with self.uow_factory() as uow:
            for tool_run in tool_runs:
                tool_run_id = getattr(tool_run, "id", None)
                status = getattr(tool_run, "status", None)
                if not isinstance(tool_run_id, str):
                    continue
                mark_tool_run_step_item_terminal(
                    uow,
                    tool_run_id=tool_run_id,
                    status=_enum_value(status),
                    summary_payload=_tool_run_terminal_summary(tool_run),
                    error_message=getattr(tool_run, "error_message", None),
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


def _tool_run_terminal_summary(tool_run: object) -> dict[str, object]:
    target = getattr(tool_run, "target", None)
    completed_at = getattr(tool_run, "completed_at", None)
    payload: dict[str, object] = {
        "tool_id": getattr(tool_run, "tool_id", None),
        "function_id": getattr(tool_run, "function_id", None),
        "source_id": getattr(tool_run, "source_id", None),
        "mode": _enum_value(getattr(target, "mode", None)),
        "strategy": _enum_value(getattr(target, "strategy", None)),
        "environment": _enum_value(getattr(target, "environment", None)),
    }
    if completed_at is not None and hasattr(completed_at, "isoformat"):
        payload["completed_at"] = completed_at.isoformat()
    return {key: value for key, value in payload.items() if value is not None}


def _enum_value(value: object) -> str:
    raw_value = getattr(value, "value", value)
    return raw_value if isinstance(raw_value, str) else str(raw_value)


def _llm_step_summary(payload: dict[str, object]) -> dict[str, object]:
    summary: dict[str, object] = {}
    for key in (
        "assistant_progress_item_ids",
        "context_render_snapshot_id",
        "llm_id",
        "llm_invocation_id",
        "llm_response_item_ids",
        "llm_loop_diagnostic",
        "llm_transcript_consumption",
        "prompt_mode",
        "session_item_ids",
        "tool_call_session_item_ids",
        "tool_call_names",
        "tool_result_session_item_ids",
        "user_session_item_id",
    ):
        value = payload.get(key)
        if value is not None:
            summary[key] = value
    return summary


def _continuation_payload(payload: dict[str, object]) -> dict[str, object] | None:
    reason = _first_present(
        payload,
        "llm_continuation_reason",
        "continuation_reason",
    )
    end_turn = _first_present(
        payload,
        "llm_continuation_end_turn",
        "continuation_end_turn",
    )
    follow_up = payload.get("llm_continuation_follow_up")
    if reason is None and end_turn is None and follow_up is None:
        return None
    result: dict[str, object] = {}
    if reason is not None:
        result["reason"] = reason
    if end_turn is not None:
        result["end_turn"] = end_turn
    if follow_up is not None:
        result["needs_follow_up"] = bool(follow_up)
    return result


def _first_present(payload: dict[str, object], *keys: str) -> object | None:
    for key in keys:
        if key in payload and payload[key] is not None:
            return payload[key]
    return None


def _tool_run_links(payload: dict[str, object]) -> tuple[dict[str, object], ...]:
    raw_links = payload.get("tool_run_links")
    if not isinstance(raw_links, (list, tuple)):
        return ()
    links: list[dict[str, object]] = []
    for raw_link in raw_links:
        if isinstance(raw_link, dict):
            links.append(dict(raw_link))
    return tuple(links)


def _approval_llm_invocation_id(
    contract: dict[str, object],
) -> str | None:
    return _optional_text(contract.get("llm_invocation_id"))


def _optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None
