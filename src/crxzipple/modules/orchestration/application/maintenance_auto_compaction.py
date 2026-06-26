from __future__ import annotations

from crxzipple.core.logger import get_logger
from crxzipple.modules.orchestration.application.commands import (
    RequestCompactionInput,
    RequestMemoryFlushInput,
)
from crxzipple.modules.orchestration.application.maintenance_context_budget import (
    _coerce_non_negative_int,
)
from crxzipple.modules.orchestration.application.runtime_request_mode import (
    RuntimeRequestMode,
)
from crxzipple.modules.orchestration.domain import OrchestrationRun

logger = get_logger(__name__)


class OrchestrationMaintenanceAutoCompactionMixin:
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
        if isinstance(preflight_payload, dict) and preflight_payload.get(
            "applied_for_run",
        ):
            return None
        runtime_request_mode = (
            str(run.metadata.get("runtime_request_mode", "")).strip().lower()
        )
        if runtime_request_mode not in {
            RuntimeRequestMode.NORMAL_TURN.value,
            RuntimeRequestMode.RECOVERY_RESUME.value,
        }:
            return None
        session_key = str(run.metadata.get("session_key", "")).strip()
        if not session_key:
            return None
        runtime_request_report = run.metadata.get("runtime_request_report")
        if not isinstance(runtime_request_report, dict):
            return None
        transcript_payload = runtime_request_report.get("transcript")
        if not isinstance(transcript_payload, dict):
            return None
        estimated_total_tokens = _coerce_non_negative_int(
            runtime_request_report.get("estimated_total_tokens"),
        )
        transcript_chars = _coerce_non_negative_int(transcript_payload.get("chars"))
        transcript_estimated_tokens = _coerce_non_negative_int(
            transcript_payload.get("estimated_tokens"),
        )
        dynamic_threshold = self._auto_compaction_context_threshold_tokens(run)
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
