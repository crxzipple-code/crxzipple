from __future__ import annotations

from crxzipple.core.logger import get_logger
from crxzipple.modules.orchestration.application.engine import (
    RuntimeLlmRequestPreview,
)
from crxzipple.modules.orchestration.domain import OrchestrationRun
from crxzipple.modules.session.application import (
    GetSessionItemBySourceInput,
    ListSessionItemsInput,
)
from crxzipple.modules.session.domain import SessionItem
from crxzipple.shared.content_blocks import extract_text_content
from crxzipple.shared.token_estimates import estimate_text_tokens

logger = get_logger(__name__)


class OrchestrationMaintenanceContextBudgetMixin:
    def _preflight_compaction_trigger(
        self,
        *,
        run: OrchestrationRun,
        preview: RuntimeLlmRequestPreview | None,
        force: bool,
        failure_message: str | None,
    ) -> dict[str, object] | None:
        metrics = self._preflight_context_budget_metrics(run, preview=preview)
        trigger = self._compaction_trigger_from_metrics(
            estimated_total_tokens=metrics["estimated_total_tokens"],
            dynamic_threshold=metrics["context_threshold_tokens"],
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

    def _preflight_context_budget_metrics(
        self,
        run: OrchestrationRun,
        *,
        preview: RuntimeLlmRequestPreview | None,
    ) -> dict[str, int | None]:
        estimated_total_tokens = 0
        transcript_chars = 0
        transcript_estimated_tokens = 0
        context_threshold_tokens: int | None = None
        if preview is not None and preview.runtime_request_report is not None:
            report = preview.runtime_request_report
            context_estimated_tokens = _compaction_pressure_context_tokens(report)
            estimated_total_tokens = (
                context_estimated_tokens + report.transcript_estimated_tokens
            )
            transcript_chars = report.transcript_chars
            transcript_estimated_tokens = report.transcript_estimated_tokens
            context_threshold_tokens = self._auto_compaction_context_threshold_tokens_for_context_window(
                report.llm_context_window_tokens,
            )
        else:
            runtime_request_report = run.metadata.get("runtime_request_report")
            if isinstance(runtime_request_report, dict):
                estimated_total_tokens = _coerce_non_negative_int(
                    runtime_request_report.get("estimated_total_tokens"),
                )
                transcript_payload = runtime_request_report.get("transcript")
                if isinstance(transcript_payload, dict):
                    transcript_chars = _coerce_non_negative_int(
                        transcript_payload.get("chars"),
                    )
                    transcript_estimated_tokens = _coerce_non_negative_int(
                        transcript_payload.get("estimated_tokens"),
                    )
                context_budget_payload = runtime_request_report.get("context_budget")
                context_window_tokens = None
                if isinstance(context_budget_payload, dict):
                    context_window_tokens = _coerce_optional_positive_int(
                        context_budget_payload.get("llm_context_window_tokens"),
                    )
                context_threshold_tokens = self._auto_compaction_context_threshold_tokens_for_context_window(
                    context_window_tokens,
                )

        active_session_estimated_tokens = self._active_session_context_pressure_tokens(run)
        estimated_total_tokens = max(
            estimated_total_tokens,
            active_session_estimated_tokens,
        )
        pending_inbound_chars, pending_inbound_tokens = self._pending_inbound_context_metrics(
            run,
        )
        return {
            "estimated_total_tokens": estimated_total_tokens + pending_inbound_tokens,
            "transcript_chars": transcript_chars + pending_inbound_chars,
            "transcript_estimated_tokens": (
                transcript_estimated_tokens + pending_inbound_tokens
            ),
            "context_threshold_tokens": context_threshold_tokens,
            "pending_inbound_chars": pending_inbound_chars,
            "pending_inbound_estimated_tokens": pending_inbound_tokens,
        }

    def _active_session_context_pressure_tokens(self, run: OrchestrationRun) -> int:
        session_key = str(run.metadata.get("session_key", "")).strip()
        if self.session_service is None or not session_key:
            return 0
        try:
            items = self.session_service.list_items(
                ListSessionItemsInput(
                    session_key=session_key,
                    active_session_only=True,
                ),
            )
        except Exception:
            logger.debug(
                "could not estimate active session context pressure",
                exc_info=True,
                extra={"run_id": run.id, "session_key": session_key},
            )
            return 0
        return sum(
            estimate_text_tokens(_session_item_text_content(item))
            for item in items
            if item.model_visible and _session_item_text_content(item)
        )

    def _pending_inbound_context_metrics(
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
        existing_item = self.session_service.get_item_by_source(
            GetSessionItemBySourceInput(
                session_key=session_key,
                session_id=run.active_session_id,
                source_module="orchestration",
                source_kind="orchestration_run",
                source_id=run.id,
            ),
        )
        if existing_item is not None and existing_item.role == "user":
            return 0, 0
        content = extract_text_content(run.inbound_instruction.content)
        if content is None or not content.strip():
            return 0, 0
        return len(content), estimate_text_tokens(content)

    def _safe_preview_runtime_llm_request(self, run: OrchestrationRun) -> RuntimeLlmRequestPreview | None:
        if self.engine is None:
            return None
        try:
            return self.engine.preview_runtime_llm_request(run)
        except Exception:
            logger.exception(
                "failed to build runtime request preview for preflight maintenance",
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
        if isinstance(run.metadata.get("runtime_request_report"), dict):
            return False
        pending_chars, pending_tokens = self._pending_inbound_context_metrics(run)
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
            items = self.session_service.list_items(
                ListSessionItemsInput(
                    session_key=session_key,
                    limit=2,
                    active_session_only=True,
                ),
            )
        except Exception:
            logger.debug(
                "could not inspect session history for preflight maintenance",
                exc_info=True,
                extra={"run_id": run.id, "session_key": session_key},
            )
            return True
        return bool(items)

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
            "context_threshold_tokens": dynamic_threshold,
        }
        return {
            "trigger_basis": "context_budget",
            "compaction_reason": (
                "auto_compaction_context_budget_exceeded"
                f":{estimated_total_tokens}/{dynamic_threshold}"
            ),
            "trigger_details": trigger_details,
        }

    def _auto_compaction_context_threshold_tokens(
        self,
        run: OrchestrationRun,
    ) -> int | None:
        return self._auto_compaction_context_threshold_tokens_for_context_window(
            self._context_window_tokens_for_run(run),
        )

    def _auto_compaction_context_threshold_tokens_for_context_window(
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


def _compaction_pressure_context_tokens(report: object) -> int:
    base_tokens = _coerce_non_negative_int(
        getattr(report, "context_estimated_tokens", 0),
    )
    request_render_snapshot = getattr(report, "request_render_snapshot", None)
    estimate = getattr(request_render_snapshot, "estimate", None)
    if not isinstance(estimate, dict):
        return base_tokens
    breakdown = estimate.get("breakdown")
    if not isinstance(breakdown, dict):
        return base_tokens
    by_owner = breakdown.get("by_owner")
    if not isinstance(by_owner, dict):
        return base_tokens
    session_estimate = by_owner.get("session")
    if not isinstance(session_estimate, dict):
        return base_tokens
    return base_tokens + _coerce_non_negative_int(
        session_estimate.get("text_tokens"),
    )


def _session_item_text_content(item: SessionItem) -> str:
    content = extract_text_content(item.content_payload)
    if content is not None and content.strip():
        return content
    text = item.content_payload.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()
    return ""
