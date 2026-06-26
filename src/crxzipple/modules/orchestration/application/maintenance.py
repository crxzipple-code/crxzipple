from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from crxzipple.modules.orchestration.application.commands import (
    FailAssignmentInput,
    RequestCompactionInput,
    RequestMemoryFlushInput,
)
from crxzipple.modules.orchestration.application.engine import (
    OrchestrationEngine,
    RuntimeLlmRequestPreview,
)
from crxzipple.modules.orchestration.application.maintenance_context_budget import (
    OrchestrationMaintenanceContextBudgetMixin,
)
from crxzipple.modules.orchestration.application.maintenance_compaction_summary import (
    OrchestrationMaintenanceCompactionSummaryMixin,
)
from crxzipple.modules.orchestration.application.maintenance_auto_compaction import (
    OrchestrationMaintenanceAutoCompactionMixin,
)
from crxzipple.modules.orchestration.application.maintenance_run_classification import (
    OrchestrationMaintenanceRunClassificationMixin,
)
from crxzipple.modules.orchestration.application.ports import (
    LlmPort,
    SessionMaintenancePort,
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


@dataclass(slots=True)
class OrchestrationMaintenanceService(
    OrchestrationMaintenanceCompactionSummaryMixin,
    OrchestrationMaintenanceAutoCompactionMixin,
    OrchestrationMaintenanceContextBudgetMixin,
    OrchestrationMaintenanceRunClassificationMixin,
):
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
        preview: RuntimeLlmRequestPreview | None = None
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
            preview = self._safe_preview_runtime_llm_request(run)
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
                        "Context budget remained above the maintenance threshold "
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
        try:
            refreshed_active_session_id = self.session_service.get_session(
                session_key,
            ).active_session_id
        except Exception as exc:
            return False, self.fail_assignment(
                FailAssignmentInput(
                    run_id=run.id,
                    worker_id=worker_id,
                    message=(
                        "Preflight maintenance could not refresh the active "
                        "session binding after compaction."
                    ),
                    code="preflight_maintenance_failed",
                    details={
                        "maintenance_run_id": processed_compaction.id,
                        "maintenance_kind": "session_binding_refresh",
                        "error": str(exc) or type(exc).__name__,
                        **trigger,
                    },
                ),
            )
        self._mark_preflight_maintenance_applied(
            run_id=run.id,
            step=run.current_step,
            details=trigger,
            active_session_id=refreshed_active_session_id,
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
        active_session_id: str,
    ) -> None:
        with self.uow_factory() as uow:
            run = self._get_run(uow, run_id)
            run.refresh_active_session_binding(
                active_session_id=active_session_id,
                reason="preflight_maintenance_compaction",
            )
            current_payload = run.metadata.get("preflight_maintenance")
            payload = dict(current_payload) if isinstance(current_payload, dict) else {}
            payload["applied_for_run"] = True
            payload["applied_step"] = step
            payload["applied_details"] = dict(details)
            payload["active_session_id_after_maintenance"] = active_session_id
            run.metadata["preflight_maintenance"] = payload
            uow.orchestration_runs.add(run)
            uow.collect(run)
            uow.commit()

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
