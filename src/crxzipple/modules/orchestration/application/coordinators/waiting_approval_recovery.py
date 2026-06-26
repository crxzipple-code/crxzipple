from __future__ import annotations

from crxzipple.modules.llm.domain import ToolCallIntent
from crxzipple.modules.orchestration.application.coordinators.waiting_recovery_payloads import (
    approval_llm_invocation_id,
    approval_recovery_contract_payload,
    enum_value,
    tool_run_terminal_summary,
    tool_wait_recovery_contract_payload,
)
from crxzipple.modules.orchestration.application.execution_chain_lifecycle import (
    current_dispatch_task_id,
    fail_active_execution_step,
    mark_tool_run_step_item_terminal,
    materialize_tool_batch_execution_step,
    require_current_dispatch_task_id,
)
from crxzipple.modules.orchestration.domain import (
    ApprovalDecision,
    OrchestrationRun,
    OrchestrationRunStage,
    OrchestrationRunStatus,
    PendingApprovalRequest,
)
from crxzipple.modules.orchestration.domain.exceptions import (
    OrchestrationValidationError,
)
from crxzipple.modules.session.application import ListSessionItemsInput
from crxzipple.modules.session.domain import SessionItemKind
from crxzipple.modules.tool.domain import ToolError, ToolRun


class RunWaitApprovalRecoveryMixin:
    def _wait_on_replayed_background_tools(
        self,
        *,
        run_id: str,
        background_runs: tuple[tuple[ToolCallIntent, ToolRun], ...],
    ) -> OrchestrationRun:
        pending_tool_run_ids = tuple(tool_run.id for _, tool_run in background_runs)
        with self.uow_factory() as uow:
            run = self._get_run(uow, run_id)
            run.recovery_contract_payload = tool_wait_recovery_contract_payload(
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
                approval_recovery_contract_payload(
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
        llm_invocation_id = approval_llm_invocation_id(contract)
        if llm_invocation_id is not None:
            self._materialize_replayed_tool_batch(
                run_id=run.id,
                llm_invocation_id=llm_invocation_id,
                tool_run_links=tuple(
                    dict(link.to_payload()) for link in replay_outcome.tool_run_links
                ),
            )
        if replay_outcome.background_runs:
            pending_tool_run_ids = tuple(
                tool_run.id for _, tool_run in replay_outcome.background_runs
            )
            self._store_recovery_contract(
                run.id,
                approval_recovery_contract_payload(
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
            approval_recovery_contract_payload(
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
            run.recovery_contract_payload = tool_wait_recovery_contract_payload(
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
                    "runtime_request_flow_hint": {
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
        list_items = getattr(self.session_service, "list_items", None)
        if not callable(list_items):
            return ()
        items = list_items(
            ListSessionItemsInput(
                session_key=session_key,
                active_session_only=True,
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
                    status=enum_value(status),
                    summary_payload=tool_run_terminal_summary(tool_run),
                    error_message=getattr(tool_run, "error_message", None),
                )
            uow.commit()
