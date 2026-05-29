from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from crxzipple.core.logger import get_logger
from crxzipple.modules.orchestration.application.commands import (
    FailAssignmentInput,
    RequestCompactionInput,
    RequestMemoryFlushInput,
)
from crxzipple.modules.orchestration.application.engine import (
    OrchestrationEngine,
    PromptSurfacePreview,
)
from crxzipple.modules.orchestration.application.ports import (
    LlmPort,
    SessionMaintenancePort,
)
from crxzipple.modules.orchestration.application.prompting import (
    PromptMode,
    estimate_text_tokens,
)
from crxzipple.modules.orchestration.application.unit_of_work import (
    OrchestrationUnitOfWork,
)
from crxzipple.modules.orchestration.domain import (
    OrchestrationRun,
    OrchestrationRunNotFoundError,
    OrchestrationRunStage,
    OrchestrationRunStatus,
)
from crxzipple.modules.session.application import (
    ArchiveSessionMessagesInput,
    ListSessionMessagesInput,
    MergeSessionMessageMetadataInput,
)
from crxzipple.shared.time import format_datetime_utc
from crxzipple.modules.session.domain import SessionMessageNotFoundError
from crxzipple.shared.content_blocks import extract_text_content

logger = get_logger(__name__)


@dataclass(slots=True)
class OrchestrationMaintenanceService:
    uow_factory: Callable[[], OrchestrationUnitOfWork]
    engine: OrchestrationEngine | None
    session_service: SessionMaintenancePort | None
    llm_port: LlmPort | None
    request_coordinator: Any
    request_memory_flush: Callable[[RequestMemoryFlushInput], OrchestrationRun]
    request_compaction: Callable[[RequestCompactionInput], OrchestrationRun]
    fail_assignment: Callable[[FailAssignmentInput], OrchestrationRun]
    process_requested_run_inline: Callable[..., OrchestrationRun]
    auto_compaction_enabled: bool
    auto_compaction_reserve_tokens: int
    auto_compaction_soft_threshold_tokens: int

    def maybe_run_preflight_maintenance(
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
        if self.is_maintenance_mode_run(run):
            return False, None
        session_key = str(run.metadata.get("session_key", "")).strip()
        if not session_key:
            return False, None
        preview: PromptSurfacePreview | None = None
        trigger = self._preflight_compaction_trigger(
            run=run,
            preview=preview,
            force=force,
            failure_message=failure_message,
        )
        if trigger is None and self._should_build_preflight_preview(
            run,
            force=force,
            failure_message=failure_message,
        ):
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
            return False, self.fail_assignment(
                FailAssignmentInput(
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

        flush_run = self.request_coordinator.existing_pending_memory_flush_run(
            session_key,
        )
        compaction_run = self.request_coordinator.existing_pending_compaction_run(
            session_key,
        )
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
            processed_flush = self.process_requested_run_inline(
                run_id=flush_run.id,
                worker_id=worker_id,
            )
            if processed_flush.status is not OrchestrationRunStatus.COMPLETED:
                return False, self.fail_assignment(
                    FailAssignmentInput(
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
            return False, self.fail_assignment(
                FailAssignmentInput(
                    run_id=run.id,
                    worker_id=worker_id,
                    message=(
                        "Preflight maintenance did not schedule a compaction run."
                    ),
                    code="preflight_maintenance_failed",
                    details=trigger,
                ),
            )
        processed_compaction = self.process_requested_run_inline(
            run_id=compaction_run.id,
            worker_id=worker_id,
        )
        if processed_compaction.status is not OrchestrationRunStatus.COMPLETED:
            return False, self.fail_assignment(
                FailAssignmentInput(
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

    def rewind_llm_attempt(
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

    def apply_compaction_summary(self, run: OrchestrationRun) -> None:
        prompt_mode = str(run.metadata.get("prompt_mode", "")).strip().lower()
        if prompt_mode != "compaction":
            return
        session_key = str(run.metadata.get("session_key", "")).strip()
        if not session_key:
            return
        if run.active_session_id is None or not run.active_session_id.strip():
            return
        if self.session_service is None:
            return
        result_payload = run.result_payload or {}
        summary_message_id = result_payload.get("assistant_message_id")
        summary_text = result_payload.get("output_text")
        if not isinstance(summary_message_id, str) or not summary_message_id.strip():
            return
        if not isinstance(summary_text, str) or not summary_text.strip():
            return
        try:
            summary_message = self.session_service.get_message(
                summary_message_id.strip(),
            )
        except SessionMessageNotFoundError:
            return
        self.session_service.merge_message_metadata(
            MergeSessionMessageMetadataInput(
                message_id=summary_message.id,
                metadata={
                    "maintenance_kind": "compaction_summary",
                    "maintenance_run_id": run.id,
                },
            ),
        )
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
                        format_datetime_utc(run.completed_at)
                        if run.completed_at is not None
                        else format_datetime_utc(run.updated_at)
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
                format_datetime_utc(run.completed_at)
                if run.completed_at is not None
                else format_datetime_utc(run.updated_at)
            )
            persisted_run.result_payload = updated_result_payload
            uow.orchestration_runs.add(persisted_run)
            uow.collect(persisted_run)
            uow.commit()

    def maybe_request_auto_compaction(
        self,
        run: OrchestrationRun,
    ) -> OrchestrationRun | None:
        if not self.auto_compaction_enabled:
            return None
        if self.session_service is None:
            return None
        if self.is_memory_flush_run(run):
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
            compaction_trigger_details = trigger_details.get(
                "compaction_trigger_details",
            )
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
        if self.is_compaction_run(run):
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

    @staticmethod
    def is_context_limit_error(exc: Exception) -> bool:
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

    def is_maintenance_mode_run(self, run: OrchestrationRun) -> bool:
        if self.is_memory_flush_run(run):
            return True
        if self.is_compaction_run(run):
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

    @staticmethod
    def is_memory_flush_run(run: OrchestrationRun) -> bool:
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
    def is_compaction_run(run: OrchestrationRun) -> bool:
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

    def _preflight_compaction_trigger(
        self,
        *,
        run: OrchestrationRun,
        preview: PromptSurfacePreview | None,
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
        preview: PromptSurfacePreview | None,
    ) -> dict[str, int | None]:
        estimated_total_tokens = 0
        transcript_chars = 0
        transcript_estimated_tokens = 0
        prompt_threshold_tokens: int | None = None
        if preview is not None and preview.prompt_report is not None:
            report = preview.prompt_report
            estimated_total_tokens = (
                report.context_estimated_tokens + report.transcript_estimated_tokens
            )
            transcript_chars = report.transcript_chars
            transcript_estimated_tokens = report.transcript_estimated_tokens
            prompt_threshold_tokens = self._auto_compaction_prompt_threshold_tokens_for_context_window(
                report.llm_context_window_tokens,
            )
        else:
            prompt_report = run.metadata.get("prompt_report")
            if isinstance(prompt_report, dict):
                estimated_total_tokens = _coerce_non_negative_int(
                    prompt_report.get("estimated_total_tokens"),
                )
                transcript_payload = prompt_report.get("transcript")
                if isinstance(transcript_payload, dict):
                    transcript_chars = _coerce_non_negative_int(
                        transcript_payload.get("chars"),
                    )
                    transcript_estimated_tokens = _coerce_non_negative_int(
                        transcript_payload.get("estimated_tokens"),
                    )
                context_budget_payload = prompt_report.get("context_budget")
                context_window_tokens = None
                if isinstance(context_budget_payload, dict):
                    context_window_tokens = _coerce_optional_positive_int(
                        context_budget_payload.get("llm_context_window_tokens"),
                    )
                prompt_threshold_tokens = self._auto_compaction_prompt_threshold_tokens_for_context_window(
                    context_window_tokens,
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

    def _safe_preview_prompt(self, run: OrchestrationRun) -> PromptSurfacePreview | None:
        if self.engine is None:
            return None
        try:
            return self.engine.preview_prompt(run)
        except Exception:
            logger.exception(
                "failed to build prompt surface preview for preflight maintenance",
                extra={"run_id": run.id},
            )
            return None

    def _should_build_preflight_preview(
        self,
        run: OrchestrationRun,
        *,
        force: bool,
        failure_message: str | None,
    ) -> bool:
        if force or (failure_message is not None and failure_message.strip()):
            return True
        if isinstance(run.metadata.get("prompt_report"), dict):
            return False
        pending_chars, pending_tokens = self._pending_inbound_prompt_metrics(run)
        if pending_chars > 0 and pending_tokens >= self.auto_compaction_soft_threshold_tokens:
            return True
        return self._active_session_has_preflight_history(run)

    def _active_session_has_preflight_history(self, run: OrchestrationRun) -> bool:
        if self.session_service is None:
            return False
        session_key = str(run.metadata.get("session_key", "")).strip()
        if not session_key:
            return False
        try:
            messages = self.session_service.list_messages(
                ListSessionMessagesInput(
                    session_key=session_key,
                    limit=2,
                    active_session_only=True,
                    include_archived=False,
                ),
            )
        except Exception:
            logger.debug(
                "could not inspect session history for preflight maintenance",
                exc_info=True,
                extra={"run_id": run.id, "session_key": session_key},
            )
            return True
        return bool(messages)

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
    def _get_run(
        uow: OrchestrationUnitOfWork,
        run_id: str,
    ) -> OrchestrationRun:
        run = uow.orchestration_runs.get(run_id)
        if run is None:
            raise OrchestrationRunNotFoundError(
                f"Orchestration run '{run_id}' was not found.",
            )
        return run


def _coerce_non_negative_int(value: object) -> int:
    try:
        resolved = int(value)
    except (TypeError, ValueError):
        return 0
    return max(0, resolved)


def _coerce_optional_positive_int(value: object) -> int | None:
    try:
        resolved = int(value)
    except (TypeError, ValueError):
        return None
    return resolved if resolved > 0 else None
