"""Run execution service for orchestration executor workers."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field

from crxzipple.modules.orchestration.application.commands import (
    AdvanceAssignmentInput,
    CompleteAssignmentInput,
    FailAssignmentInput,
    WaitAssignmentOnToolInput,
    WaitForConfirmationInput,
)
from crxzipple.modules.orchestration.application.engine import (
    EngineAdvanceOutcome,
    OrchestrationEngine,
)
from crxzipple.modules.orchestration.application.maintenance import (
    OrchestrationMaintenanceService,
)
from crxzipple.modules.orchestration.application.ports import EventPublishManyPort
from crxzipple.modules.orchestration.domain import (
    OrchestrationRun,
    OrchestrationRunStage,
    OrchestrationRunStatus,
)
from crxzipple.shared.orchestration_observation import (
    ORCHESTRATION_RUN_LLM_TEXT_DELTA_EVENT,
)
from crxzipple.shared.domain.events import Event
from crxzipple.shared.runtime_metrics import (
    RuntimeMetricsRegistry,
    get_runtime_metrics_registry,
)


@dataclass(slots=True)
class RunExecutionService:
    """Owns the executor-side run advancement loop."""

    engine: OrchestrationEngine | None
    maintenance_service: OrchestrationMaintenanceService
    get_run: Callable[[str], OrchestrationRun]
    advance_assignment: Callable[[AdvanceAssignmentInput], OrchestrationRun]
    wait_assignment_on_tool: Callable[[WaitAssignmentOnToolInput], OrchestrationRun]
    wait_for_confirmation: Callable[[WaitForConfirmationInput], OrchestrationRun]
    complete_assignment: Callable[[CompleteAssignmentInput], OrchestrationRun]
    fail_assignment: Callable[[FailAssignmentInput], OrchestrationRun]
    clear_prompt_flow_hint: Callable[[str], None]
    events_service: EventPublishManyPort | None = None
    metrics: RuntimeMetricsRegistry = field(
        default_factory=get_runtime_metrics_registry,
    )

    def advance_once(self, *, run_id: str, worker_id: str) -> OrchestrationRun:
        if self.engine is None:
            raise RuntimeError("Orchestration engine is not configured.")
        while True:
            with self.metrics.timed(
                "orchestration.executor.advance_phase_seconds",
                labels={"phase": "preflight"},
            ):
                run = self.get_run(run_id)
                maintenance_ran, terminal_run = (
                    self.maintenance_service.maybe_run_preflight_maintenance(
                        run=run,
                        worker_id=worker_id,
                    )
                )
            if terminal_run is not None:
                return terminal_run
            if maintenance_ran:
                continue
            if run.current_step >= run.max_steps:
                return self.fail_assignment(
                    FailAssignmentInput(
                        run_id=run_id,
                        worker_id=worker_id,
                        message="Orchestration run exceeded its maximum step budget.",
                        code="max_steps_exceeded",
                        details={"max_steps": run.max_steps},
                    ),
                )

            pre_invoke_stage = run.stage
            pre_invoke_step = run.current_step
            with self.metrics.timed(
                "orchestration.executor.advance_phase_seconds",
                labels={"phase": "advance_to_llm"},
            ):
                run = self._advance_assignment_to_llm(
                    run_id=run_id,
                    worker_id=worker_id,
                )
            try:
                with self.metrics.timed(
                    "orchestration.executor.advance_phase_seconds",
                    labels={"phase": "engine"},
                ):
                    outcome = self.engine.advance_once(
                        run,
                        on_llm_stream_update=lambda invocation_id, text, text_delta: self.publish_llm_stream_update(
                            run_id=run_id,
                            worker_id=worker_id,
                            invocation_id=invocation_id,
                            text=text,
                            text_delta=text_delta,
                        ),
                    )
            except Exception as exc:
                with self.metrics.timed(
                    "orchestration.executor.advance_phase_seconds",
                    labels={"phase": "handle_exception"},
                ):
                    handled = self._handle_engine_exception(
                        exc,
                        run_id=run_id,
                        worker_id=worker_id,
                        pre_invoke_stage=pre_invoke_stage,
                        pre_invoke_step=pre_invoke_step,
                    )
                if handled is None:
                    continue
                return handled
            with self.metrics.timed(
                "orchestration.executor.advance_phase_seconds",
                labels={"phase": "handle_outcome"},
            ):
                handled = self._handle_engine_outcome(
                    run,
                    outcome,
                    run_id=run_id,
                    worker_id=worker_id,
                )
            if handled is None:
                continue
            return handled

    async def advance_once_async(
        self,
        *,
        run_id: str,
        worker_id: str,
    ) -> OrchestrationRun:
        if self.engine is None:
            raise RuntimeError("Orchestration engine is not configured.")
        while True:
            with self.metrics.timed(
                "orchestration.executor.advance_phase_seconds",
                labels={"phase": "preflight"},
            ):
                run, maintenance_ran, terminal_run = await asyncio.to_thread(
                    self._prepare_advance_preflight,
                    run_id=run_id,
                    worker_id=worker_id,
                )
            if terminal_run is not None:
                return terminal_run
            if maintenance_ran:
                continue
            if run.current_step >= run.max_steps:
                return await asyncio.to_thread(
                    self.fail_assignment,
                    FailAssignmentInput(
                        run_id=run_id,
                        worker_id=worker_id,
                        message="Orchestration run exceeded its maximum step budget.",
                        code="max_steps_exceeded",
                        details={"max_steps": run.max_steps},
                    ),
                )

            pre_invoke_stage = run.stage
            pre_invoke_step = run.current_step
            with self.metrics.timed(
                "orchestration.executor.advance_phase_seconds",
                labels={"phase": "advance_to_llm"},
            ):
                run = await asyncio.to_thread(
                    self._advance_assignment_to_llm,
                    run_id=run_id,
                    worker_id=worker_id,
                )
            try:
                with self.metrics.timed(
                    "orchestration.executor.advance_phase_seconds",
                    labels={"phase": "engine"},
                ):
                    outcome = await self.engine.advance_once_async(
                        run,
                        on_llm_stream_update=lambda invocation_id, text, text_delta: self.publish_llm_stream_update(
                            run_id=run_id,
                            worker_id=worker_id,
                            invocation_id=invocation_id,
                            text=text,
                            text_delta=text_delta,
                        ),
                    )
            except Exception as exc:
                with self.metrics.timed(
                    "orchestration.executor.advance_phase_seconds",
                    labels={"phase": "handle_exception"},
                ):
                    handled = await asyncio.to_thread(
                        self._handle_engine_exception,
                        exc,
                        run_id=run_id,
                        worker_id=worker_id,
                        pre_invoke_stage=pre_invoke_stage,
                        pre_invoke_step=pre_invoke_step,
                    )
                if handled is None:
                    continue
                return handled
            with self.metrics.timed(
                "orchestration.executor.advance_phase_seconds",
                labels={"phase": "handle_outcome"},
            ):
                handled = await asyncio.to_thread(
                    self._handle_engine_outcome,
                    run,
                    outcome,
                    run_id=run_id,
                    worker_id=worker_id,
                )
            if handled is None:
                continue
            return handled

    def _prepare_advance_preflight(
        self,
        *,
        run_id: str,
        worker_id: str,
    ) -> tuple[OrchestrationRun, bool, OrchestrationRun | None]:
        run = self.get_run(run_id)
        maintenance_ran, terminal_run = (
            self.maintenance_service.maybe_run_preflight_maintenance(
                run=run,
                worker_id=worker_id,
            )
        )
        return run, maintenance_ran, terminal_run

    def _advance_assignment_to_llm(
        self,
        *,
        run_id: str,
        worker_id: str,
    ) -> OrchestrationRun:
        return self.advance_assignment(
            AdvanceAssignmentInput(
                run_id=run_id,
                worker_id=worker_id,
                stage=OrchestrationRunStage.LLM,
                step_increment=1,
            ),
        )

    def _handle_engine_exception(
        self,
        exc: Exception,
        *,
        run_id: str,
        worker_id: str,
        pre_invoke_stage: OrchestrationRunStage,
        pre_invoke_step: int,
    ) -> OrchestrationRun | None:
        current_run = self.get_run(run_id)
        if self._run_has_left_worker_control(
            current_run,
            worker_id=worker_id,
        ):
            return current_run
        if self.maintenance_service.is_context_limit_error(exc):
            self.maintenance_service.rewind_llm_attempt(
                run_id=run_id,
                worker_id=worker_id,
                previous_stage=pre_invoke_stage,
                previous_step=pre_invoke_step,
            )
            refreshed_run = self.get_run(run_id)
            maintenance_ran, terminal_run = (
                self.maintenance_service.maybe_run_preflight_maintenance(
                    run=refreshed_run,
                    worker_id=worker_id,
                    force=True,
                    failure_message=str(exc) or type(exc).__name__,
                )
            )
            if terminal_run is not None:
                return terminal_run
            if maintenance_ran:
                return None
        return self.fail_assignment(
            FailAssignmentInput(
                run_id=run_id,
                worker_id=worker_id,
                message=str(exc) or type(exc).__name__,
                code=_exception_code(exc, default="engine_failed"),
                details={
                    "stage": OrchestrationRunStage.LLM.value,
                    **_exception_details(exc),
                },
            ),
        )

    def _handle_engine_outcome(
        self,
        run: OrchestrationRun,
        outcome: EngineAdvanceOutcome,
        *,
        run_id: str,
        worker_id: str,
    ) -> OrchestrationRun | None:
        current_run = self.get_run(run_id)
        if self._run_has_left_worker_control(
            current_run,
            worker_id=worker_id,
        ):
            return current_run
        self.clear_prompt_flow_hint(run_id)

        if outcome.pending_tool_run_ids:
            self.advance_assignment(
                AdvanceAssignmentInput(
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
            return self.wait_assignment_on_tool(
                WaitAssignmentOnToolInput(
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
            self.advance_assignment(
                AdvanceAssignmentInput(
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
            return None

        if (
            self.maintenance_service.is_memory_flush_run(run)
            and not outcome.inline_tool_run_ids
        ):
            return self.fail_assignment(
                FailAssignmentInput(
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

        return self.complete_assignment(
            CompleteAssignmentInput(
                run_id=run_id,
                worker_id=worker_id,
                result_payload=self._result_payload_from_outcome(outcome),
                metadata=self._prompt_metadata_from_outcome(outcome),
            ),
        )

    def publish_llm_stream_update(
        self,
        *,
        run_id: str,
        worker_id: str,
        invocation_id: str,
        text: str,
        text_delta: str | None = None,
    ) -> OrchestrationRun:
        from crxzipple.modules.orchestration.application.observers import (
            turn_session_live_topic,
        )

        run = self.get_run(run_id)
        if self._run_has_left_worker_control(
            run,
            worker_id=worker_id,
        ):
            return run
        session_key = run.session_key
        active_session_id = run.active_session_id
        status = run.status.value
        stage = run.stage.value
        current_step = run.current_step
        if self.events_service is not None and session_key:
            payload = {
                "event_name": ORCHESTRATION_RUN_LLM_TEXT_DELTA_EVENT,
                "run_id": run_id,
                "session_key": session_key,
                "active_session_id": active_session_id,
                "status": status,
                "stage": stage,
                "current_step": current_step,
                "invocation_id": invocation_id,
                "text_delta": text_delta,
                "text": text,
                "text_length": len(text),
            }
            self.events_service.publish_many(
                (
                    Event(
                        topic=turn_session_live_topic(session_key),
                        kind="live",
                        ordering_key=run_id,
                        payload=payload,
                    ),
                    Event(
                        name=ORCHESTRATION_RUN_LLM_TEXT_DELTA_EVENT,
                        kind="live",
                        ordering_key=run_id,
                        payload=payload,
                    ),
                ),
            )
        return run

    @staticmethod
    def _result_payload_from_outcome(
        outcome: EngineAdvanceOutcome,
    ) -> dict[str, object]:
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
        if outcome.yield_requested:
            payload["yield_requested"] = True
            if outcome.yield_reason is not None:
                payload["yield_reason"] = outcome.yield_reason
        return payload

    @staticmethod
    def _prompt_metadata_from_outcome(
        outcome: EngineAdvanceOutcome,
    ) -> dict[str, object]:
        metadata: dict[str, object] = {}
        if outcome.user_message_id is not None:
            metadata["user_message_id"] = outcome.user_message_id
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

    @staticmethod
    def _run_has_left_worker_control(
        run: OrchestrationRun,
        *,
        worker_id: str,
    ) -> bool:
        if run.status is not OrchestrationRunStatus.RUNNING:
            return True
        return run.worker_id != worker_id


def _exception_code(exc: Exception, *, default: str) -> str:
    code = getattr(exc, "code", None)
    if isinstance(code, str) and code.strip():
        return code.strip()
    return default


def _exception_details(exc: Exception) -> dict[str, object]:
    details = getattr(exc, "details", None)
    if isinstance(details, dict):
        return dict(details)
    return {}
