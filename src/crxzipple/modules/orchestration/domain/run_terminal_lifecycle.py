from __future__ import annotations

from datetime import datetime

from crxzipple.modules.orchestration.domain.entity_payloads import (
    _normalized_optional_text,
    _waiting_reason,
)
from crxzipple.modules.orchestration.domain.exceptions import (
    OrchestrationValidationError,
)
from crxzipple.modules.orchestration.domain.value_objects import (
    OrchestrationErrorPayload,
    OrchestrationRunStage,
    OrchestrationRunStatus,
    utcnow,
)
from crxzipple.shared.domain.events import Event
from crxzipple.shared.orchestration_observation import (
    ORCHESTRATION_RUN_CANCELLED_EVENT,
    ORCHESTRATION_RUN_COMPLETED_EVENT,
    ORCHESTRATION_RUN_FAILED_EVENT,
)


class OrchestrationRunTerminalLifecycleMixin:
    def complete(
        self,
        *,
        worker_id: str,
        result_payload: dict[str, object] | None = None,
        happened_at: datetime | None = None,
    ) -> None:
        if self.status is not OrchestrationRunStatus.RUNNING:
            raise OrchestrationValidationError(
                "Only running orchestration runs can be completed.",
            )
        normalized_worker_id = self._require_worker(worker_id)
        timestamp = happened_at or utcnow()
        self.status = OrchestrationRunStatus.COMPLETED
        self.stage = OrchestrationRunStage.COMPLETED
        self.worker_id = normalized_worker_id
        self.pending_tool_run_ids = ()
        self.waiting_reason = None
        self.lane_lock_key = None
        self.result_payload = dict(result_payload or {})
        self.completed_at = timestamp
        self.updated_at = timestamp
        self.record_event(
            Event(
                name=ORCHESTRATION_RUN_COMPLETED_EVENT,
                payload={
                    "run_id": self.id,
                    "worker_id": self.worker_id,
                    "session_key": self.session_key,
                    "active_session_id": self.active_session_id,
                    "agent_id": self.agent_id,
                    "status": self.status.value,
                    "stage": self.stage.value,
                    "current_step": self.current_step,
                    "lane_key": self.lane_key,
                },
            ),
        )

    def fail(
        self,
        *,
        worker_id: str | None = None,
        message: str,
        code: str = "orchestration_failed",
        details: dict[str, object] | None = None,
        happened_at: datetime | None = None,
    ) -> None:
        if self.status not in {
            OrchestrationRunStatus.RUNNING,
            OrchestrationRunStatus.WAITING,
        }:
            raise OrchestrationValidationError(
                "Only running or waiting orchestration runs can fail.",
            )
        normalized_worker_id: str | None = None
        if worker_id is not None:
            normalized_worker_id = self._require_worker(worker_id)
        timestamp = happened_at or utcnow()
        self.status = OrchestrationRunStatus.FAILED
        self.stage = OrchestrationRunStage.FAILED
        self.worker_id = normalized_worker_id
        self.pending_tool_run_ids = ()
        self.waiting_reason = None
        self.lane_lock_key = None
        self.error = OrchestrationErrorPayload(
            message=message,
            code=code,
            details=details or {},
        )
        self.completed_at = timestamp
        self.updated_at = timestamp
        self.record_event(
            Event(
                name=ORCHESTRATION_RUN_FAILED_EVENT,
                payload={
                    "run_id": self.id,
                    "worker_id": self.worker_id,
                    "session_key": self.session_key,
                    "active_session_id": self.active_session_id,
                    "agent_id": self.agent_id,
                    "status": self.status.value,
                    "stage": self.stage.value,
                    "current_step": self.current_step,
                    "lane_key": self.lane_key,
                    "code": self.error.code,
                    "message": self.error.message,
                    "details": dict(self.error.details),
                },
            ),
        )

    def cancel(self, *, reason: str | None = None) -> None:
        self.status = OrchestrationRunStatus.CANCELLED
        self.stage = OrchestrationRunStage.CANCELLED
        self.lane_lock_key = None
        self.worker_id = None
        self.pending_tool_run_ids = ()
        self.pending_approval_request_payload = None
        normalized_reason = _normalized_optional_text(reason)
        self.waiting_reason = _waiting_reason(normalized_reason)
        if normalized_reason is not None:
            self.metadata["cancellation_reason"] = normalized_reason
        self.completed_at = utcnow()
        self.updated_at = self.completed_at
        self.record_event(
            Event(
                name=ORCHESTRATION_RUN_CANCELLED_EVENT,
                payload={
                    "run_id": self.id,
                    "session_key": self.session_key,
                    "active_session_id": self.active_session_id,
                    "agent_id": self.agent_id,
                    "status": self.status.value,
                    "stage": self.stage.value,
                    "current_step": self.current_step,
                    "lane_key": self.lane_key,
                    "reason": self.waiting_reason,
                },
            ),
        )
