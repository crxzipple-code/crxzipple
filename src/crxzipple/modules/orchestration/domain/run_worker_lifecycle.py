from __future__ import annotations

from datetime import datetime

from crxzipple.modules.orchestration.domain.exceptions import (
    OrchestrationValidationError,
)
from crxzipple.modules.orchestration.domain.value_objects import (
    OrchestrationRunStage,
    OrchestrationRunStatus,
    utcnow,
)
from crxzipple.shared.domain.events import Event
from crxzipple.shared.orchestration_observation import (
    ORCHESTRATION_RUN_CLAIMED_EVENT,
    ORCHESTRATION_RUN_WORKER_LEASE_RECOVERED_EVENT,
)


class OrchestrationRunWorkerLifecycleMixin:
    def claim(
        self,
        *,
        worker_id: str,
        claimed_at: datetime | None = None,
        acquire_lane_lock: bool = True,
    ) -> None:
        normalized_worker_id = worker_id.strip()
        if not normalized_worker_id:
            raise OrchestrationValidationError("Orchestration worker_id cannot be empty.")
        timestamp = claimed_at or utcnow()
        self.status = OrchestrationRunStatus.RUNNING
        self.stage = OrchestrationRunStage.RUNNING
        self.worker_id = normalized_worker_id
        self.lane_lock_key = self.lane_key if acquire_lane_lock else None
        self.started_at = timestamp
        self.updated_at = timestamp
        self.record_event(
            Event(
                name=ORCHESTRATION_RUN_CLAIMED_EVENT,
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
                    "lane_lock_key": self.lane_lock_key,
                    "priority": self.priority,
                },
            ),
        )

    def heartbeat(
        self,
        *,
        worker_id: str,
        happened_at: datetime | None = None,
    ) -> None:
        if self.status is not OrchestrationRunStatus.RUNNING:
            raise OrchestrationValidationError(
                "Only running orchestration runs can be heartbeated.",
            )
        normalized_worker_id = self._require_worker(worker_id)
        timestamp = happened_at or utcnow()
        self.worker_id = normalized_worker_id
        self.updated_at = timestamp
        self.record_event(
            Event(
                name="orchestration.run.heartbeated",
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
                    "lane_lock_key": self.lane_lock_key,
                },
            ),
        )

    def recover_worker_lease(
        self,
        *,
        reason: str,
        happened_at: datetime | None = None,
    ) -> None:
        if self.status is not OrchestrationRunStatus.RUNNING:
            raise OrchestrationValidationError(
                "Only running orchestration runs can recover a worker lease.",
            )
        normalized_reason = reason.strip()
        if not normalized_reason:
            raise OrchestrationValidationError(
                "Orchestration run recovery reason cannot be empty.",
            )
        timestamp = happened_at or utcnow()
        previous_worker_id = self.worker_id
        previous_stage = self.stage
        self.status = OrchestrationRunStatus.QUEUED
        self.stage = OrchestrationRunStage.QUEUED
        self.worker_id = None
        self.lane_lock_key = None
        self.waiting_reason = None
        self.queued_at = timestamp
        self.updated_at = timestamp
        self.metadata["last_worker_lease_recovery"] = {
            "reason": normalized_reason,
            "previous_worker_id": previous_worker_id,
            "previous_stage": previous_stage.value,
            "recovered_at": timestamp.isoformat(),
        }
        self.record_event(
            Event(
                name=ORCHESTRATION_RUN_WORKER_LEASE_RECOVERED_EVENT,
                payload={
                    "run_id": self.id,
                    "session_key": self.session_key,
                    "active_session_id": self.active_session_id,
                    "agent_id": self.agent_id,
                    "status": self.status.value,
                    "stage": self.stage.value,
                    "current_step": self.current_step,
                    "lane_key": self.lane_key,
                    "priority": self.priority,
                    "queue_policy": self.queue_policy.value,
                    "previous_worker_id": previous_worker_id,
                    "previous_stage": previous_stage.value,
                    "reason": normalized_reason,
                },
            ),
        )

    def _require_worker(self, worker_id: str) -> str:
        normalized_worker_id = worker_id.strip()
        if not normalized_worker_id:
            raise OrchestrationValidationError("Orchestration worker_id cannot be empty.")
        if self.worker_id is not None and self.worker_id != normalized_worker_id:
            raise OrchestrationValidationError(
                "Orchestration run is already owned by a different worker.",
            )
        return normalized_worker_id
