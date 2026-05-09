from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, Protocol

from crxzipple.modules.agent.application import AgentApplicationService
from crxzipple.modules.dispatch.domain import DispatchTaskRepository
from crxzipple.modules.llm.domain import ToolCallIntent
from crxzipple.modules.orchestration.application.engine import OrchestrationEngine
from crxzipple.modules.orchestration.application.ports import RunDispatchPort
from crxzipple.modules.orchestration.domain import (
    ApprovalDecision,
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
)
from crxzipple.modules.session.application import (
    ListSessionMessagesInput,
    SessionApplicationService,
)
from crxzipple.modules.session.domain import SessionMessageKind
from crxzipple.modules.tool.domain import ToolRun, ToolRunStatus
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


@dataclass(slots=True)
class RunWaitCoordinator:
    uow_factory: Callable[[], WaitCoordinatorUnitOfWork]
    dispatch_port: RunDispatchPort
    engine: OrchestrationEngine | None
    session_service: SessionApplicationService | None
    agent_service: AgentApplicationService | None
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
            run.metadata["recovery_contract"] = self._tool_wait_recovery_contract_payload(
                pending_tool_run_ids=run.pending_tool_run_ids,
                pending_background_tools=tuple(
                    dict(item)
                    for item in (
                        run.metadata.get("pending_background_tools", [])
                        if isinstance(run.metadata.get("pending_background_tools"), list)
                        else []
                    )
                    if isinstance(item, dict)
                ),
                source="tool_wait",
            )
            self.dispatch_port.wait(uow.dispatch_tasks, uow, run)
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
            run.metadata["llm_invocation_id"] = data.llm_invocation_id
            if data.metadata:
                run.metadata.update(data.metadata)
            run.metadata["recovery_contract"] = self._approval_recovery_contract_payload(
                request=data.request,
                state="pending_decision",
            )
            self.dispatch_port.wait(uow.dispatch_tasks, uow, run)
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
            run.resume(
                lane_key=data.lane_key,
                queue_policy=data.queue_policy,
                priority=data.priority,
                reason=data.reason,
                clear_pending_tool_run_ids=data.clear_pending_tool_run_ids,
                happened_at=data.now,
            )
            self.dispatch_port.enqueue(uow.dispatch_tasks, uow, run)
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
            pending_request = run.resolve_approval_request(
                request_id=data.request_id,
                decision=data.decision,
                happened_at=data.now,
            )
            run.metadata["recovery_contract"] = self._approval_recovery_contract_payload(
                request=pending_request,
                state=(
                    "resolved_deny_pending_resume"
                    if data.decision is ApprovalDecision.DENY
                    else "resolved_allow_pending_replay"
                ),
                decision=data.decision,
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
        pending_background_tools = tuple(
            {
                "tool_run_id": tool_run.id,
                "tool_call_id": tool_call.id,
                "tool_name": tool_call.name,
            }
            for tool_call, tool_run in background_runs
        )
        with self.uow_factory() as uow:
            run = self._get_run(uow, run_id)
            run.metadata["pending_background_tools"] = [
                dict(item) for item in pending_background_tools
            ]
            run.metadata["recovery_contract"] = self._tool_wait_recovery_contract_payload(
                pending_tool_run_ids=pending_tool_run_ids,
                pending_background_tools=pending_background_tools,
                source="approval_replay",
            )
            run.wait_on_tool_after_confirmation(
                pending_tool_run_ids=pending_tool_run_ids,
                reason="tool_background_wait",
            )
            self.dispatch_port.wait(uow.dispatch_tasks, uow, run)
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
        existing_tool_result_message_ids = self._tool_result_message_ids_for_call(
            run=run,
            tool_call_id=request.request_id,
        )
        if existing_tool_result_message_ids:
            self._store_recovery_contract(
                run.id,
                self._approval_recovery_contract_payload(
                    request=request,
                    state="inline_replayed_pending_resume",
                    decision=decision,
                    tool_result_message_ids=existing_tool_result_message_ids,
                ),
            )
            return self._resume_after_approval_resolution(
                run_id=run.id,
                request=request,
                decision=decision,
            )
        replay_outcome = self.engine.replay_approved_tool_call(
            self.get_run(run.id),
            request=request,
        )
        if replay_outcome.background_runs:
            pending_tool_run_ids = tuple(
                tool_run.id for _, tool_run in replay_outcome.background_runs
            )
            pending_background_tools = tuple(
                {
                    "tool_run_id": tool_run.id,
                    "tool_call_id": tool_call.id,
                    "tool_name": tool_call.name,
                }
                for tool_call, tool_run in replay_outcome.background_runs
            )
            self._store_recovery_contract(
                run.id,
                self._approval_recovery_contract_payload(
                    request=request,
                    state="background_replayed_pending_wait",
                    decision=decision,
                    pending_tool_run_ids=pending_tool_run_ids,
                    pending_background_tools=pending_background_tools,
                ),
            )
            return self._wait_on_replayed_background_tools(
                run_id=run.id,
                background_runs=replay_outcome.background_runs,
            )
        inline_message_ids = tuple(
            message_id for message_id, _ in replay_outcome.inline_runs
            if message_id is not None
        )
        self._store_recovery_contract(
            run.id,
            self._approval_recovery_contract_payload(
                request=request,
                state="inline_replayed_pending_resume",
                decision=decision,
                tool_result_message_ids=inline_message_ids,
            ),
        )
        return self._resume_after_approval_resolution(
            run_id=run.id,
            request=request,
            decision=decision,
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
        if not all(tool_run.is_terminal() for tool_run in pending_tool_runs):
            return run
        self.engine.append_completed_background_tool_results(
            run,
            tool_runs=pending_tool_runs,
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
        raw_pending_background_tools = contract.get("pending_background_tools")
        pending_background_tools = (
            tuple(
                dict(item)
                for item in raw_pending_background_tools
                if isinstance(item, dict)
            )
            if isinstance(raw_pending_background_tools, list | tuple)
            else ()
        )
        if not pending_tool_run_ids:
            return self.get_run(run_id)
        with self.uow_factory() as uow:
            run = self._get_run(uow, run_id)
            run.metadata["pending_background_tools"] = [
                dict(item) for item in pending_background_tools
            ]
            run.metadata["recovery_contract"] = self._tool_wait_recovery_contract_payload(
                pending_tool_run_ids=pending_tool_run_ids,
                pending_background_tools=pending_background_tools,
                source="approval_replay",
            )
            run.wait_on_tool_after_confirmation(
                pending_tool_run_ids=pending_tool_run_ids,
                reason="tool_background_wait",
            )
            self.dispatch_port.wait(uow.dispatch_tasks, uow, run)
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
            run.metadata["recovery_contract"] = dict(payload)
            uow.orchestration_runs.add(run)
            uow.collect(run)
            uow.commit()
            return run

    @staticmethod
    def _recovery_contract_payload(run: OrchestrationRun) -> dict[str, object] | None:
        raw_payload = run.metadata.get("recovery_contract")
        return dict(raw_payload) if isinstance(raw_payload, dict) else None

    @staticmethod
    def _approval_recovery_contract_payload(
        *,
        request: PendingApprovalRequest,
        state: str,
        decision: ApprovalDecision | None = None,
        pending_tool_run_ids: tuple[str, ...] = (),
        pending_background_tools: tuple[dict[str, str], ...] = (),
        tool_result_message_ids: tuple[str, ...] = (),
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "kind": "approval",
            "state": state,
            "request": request.to_payload(),
        }
        if decision is not None:
            payload["decision"] = decision.value
        if pending_tool_run_ids:
            payload["pending_tool_run_ids"] = list(pending_tool_run_ids)
        if pending_background_tools:
            payload["pending_background_tools"] = [
                dict(item) for item in pending_background_tools
            ]
        if tool_result_message_ids:
            payload["tool_result_message_ids"] = list(tool_result_message_ids)
        return payload

    @staticmethod
    def _tool_wait_recovery_contract_payload(
        *,
        pending_tool_run_ids: tuple[str, ...],
        pending_background_tools: tuple[dict[str, object], ...],
        source: str,
    ) -> dict[str, object]:
        return {
            "kind": "tool_wait",
            "state": "waiting_on_tool",
            "source": source,
            "pending_tool_run_ids": list(pending_tool_run_ids),
            "pending_background_tools": [
                dict(item) for item in pending_background_tools
            ],
        }

    def _tool_result_message_ids_for_call(
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
        messages = self.session_service.list_messages(
            ListSessionMessagesInput(
                session_key=session_key,
                include_archived=False,
            ),
        )
        return tuple(
            message.id
            for message in messages
            if message.session_id == run.active_session_id
            and message.kind is SessionMessageKind.TOOL_RESULT
            and message.source_kind == "tool_run"
            and str(message.metadata.get("tool_call_id", "")).strip() == tool_call_id
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
