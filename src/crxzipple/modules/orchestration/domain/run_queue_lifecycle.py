from __future__ import annotations

from datetime import datetime

from crxzipple.modules.orchestration.domain.exceptions import (
    OrchestrationValidationError,
)
from crxzipple.modules.orchestration.domain.value_objects import (
    OrchestrationQueuePolicy,
    OrchestrationRunStage,
    OrchestrationRunStatus,
    utcnow,
)
from crxzipple.shared.domain.events import Event
from crxzipple.shared.orchestration_observation import (
    ORCHESTRATION_RUN_QUEUED_EVENT,
    ORCHESTRATION_RUN_RESUMED_EVENT,
    ORCHESTRATION_RUN_SESSION_BINDING_REFRESHED_EVENT,
)


class OrchestrationRunQueueLifecycleMixin:
    def route(
        self,
        *,
        agent_id: str,
        lane_key: str | None = None,
        priority: int | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        normalized_agent_id = agent_id.strip()
        if not normalized_agent_id:
            raise OrchestrationValidationError("Orchestration run agent_id cannot be empty.")
        if priority is not None and priority < 0:
            raise OrchestrationValidationError(
                "Orchestration run priority cannot be negative.",
            )
        self.agent_id = normalized_agent_id
        self.lane_key = lane_key.strip() if lane_key is not None and lane_key.strip() else self.lane_key
        if priority is not None:
            self.priority = priority
        if metadata:
            self.metadata.update(metadata)
        self.stage = OrchestrationRunStage.ROUTED
        self.updated_at = utcnow()
        self.record_event(
            Event(
                name="orchestration.run.routed",
                payload={
                    "run_id": self.id,
                    "agent_id": self.agent_id,
                    "session_key": self.session_key,
                    "lane_key": self.lane_key,
                    "status": self.status.value,
                    "stage": self.stage.value,
                    "current_step": self.current_step,
                    "priority": self.priority,
                },
            ),
        )

    def bind_session(
        self,
        *,
        active_session_id: str,
    ) -> None:
        normalized_session_id = active_session_id.strip()
        if not normalized_session_id:
            raise OrchestrationValidationError(
                "Orchestration run active_session_id cannot be empty.",
            )
        self.active_session_id = normalized_session_id
        self.stage = OrchestrationRunStage.BULK_READY
        self.updated_at = utcnow()
        self.record_event(
            Event(
                name="orchestration.run.bulk_ready",
                payload={
                    "run_id": self.id,
                    "session_key": self.session_key,
                    "active_session_id": self.active_session_id,
                    "status": self.status.value,
                    "stage": self.stage.value,
                    "current_step": self.current_step,
                },
            ),
        )

    def refresh_active_session_binding(
        self,
        *,
        active_session_id: str,
        reason: str,
    ) -> None:
        if self.status is not OrchestrationRunStatus.RUNNING:
            raise OrchestrationValidationError(
                "Only running orchestration runs can refresh active session binding.",
            )
        normalized_session_id = active_session_id.strip()
        if not normalized_session_id:
            raise OrchestrationValidationError(
                "Orchestration run active_session_id cannot be empty.",
            )
        normalized_reason = reason.strip()
        if not normalized_reason:
            raise OrchestrationValidationError(
                "Orchestration run session binding refresh reason cannot be empty.",
            )
        previous_active_session_id = self.active_session_id
        if previous_active_session_id == normalized_session_id:
            return
        self.active_session_id = normalized_session_id
        self.updated_at = utcnow()
        self.record_event(
            Event(
                name=ORCHESTRATION_RUN_SESSION_BINDING_REFRESHED_EVENT,
                payload={
                    "run_id": self.id,
                    "session_key": self.session_key,
                    "previous_active_session_id": previous_active_session_id,
                    "active_session_id": self.active_session_id,
                    "reason": normalized_reason,
                    "status": self.status.value,
                    "stage": self.stage.value,
                    "current_step": self.current_step,
                },
            ),
        )

    def enqueue(
        self,
        *,
        lane_key: str | None = None,
        queue_policy: OrchestrationQueuePolicy | None = None,
        priority: int | None = None,
    ) -> None:
        if priority is not None and priority < 0:
            raise OrchestrationValidationError(
                "Orchestration run priority cannot be negative.",
            )
        if lane_key is not None:
            normalized_lane_key = lane_key.strip()
            if not normalized_lane_key:
                raise OrchestrationValidationError("Orchestration run lane_key cannot be empty.")
            self.lane_key = normalized_lane_key
        if queue_policy is not None:
            self.queue_policy = queue_policy
        if priority is not None:
            self.priority = priority
        self.status = OrchestrationRunStatus.QUEUED
        self.stage = OrchestrationRunStage.QUEUED
        self.waiting_reason = None
        self.pending_tool_run_ids = ()
        self.worker_id = None
        self.lane_lock_key = None
        self.queued_at = utcnow()
        self.updated_at = self.queued_at
        self.record_event(
            Event(
                name=ORCHESTRATION_RUN_QUEUED_EVENT,
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
                },
            ),
        )

    def resume(
        self,
        *,
        priority: int | None = None,
        lane_key: str | None = None,
        queue_policy: OrchestrationQueuePolicy | None = None,
        reason: str | None = None,
        happened_at: datetime | None = None,
        clear_pending_tool_run_ids: bool = True,
    ) -> None:
        if self.status is not OrchestrationRunStatus.WAITING:
            raise OrchestrationValidationError(
                "Only waiting orchestration runs can be resumed.",
            )
        if priority is not None and priority < 0:
            raise OrchestrationValidationError(
                "Orchestration run priority cannot be negative.",
            )
        if lane_key is not None:
            normalized_lane_key = lane_key.strip()
            if not normalized_lane_key:
                raise OrchestrationValidationError(
                    "Orchestration run lane_key cannot be empty.",
                )
            self.lane_key = normalized_lane_key
        if queue_policy is not None:
            self.queue_policy = queue_policy
        if priority is not None:
            self.priority = priority
        if clear_pending_tool_run_ids:
            self.pending_tool_run_ids = ()
        timestamp = happened_at or utcnow()
        self.status = OrchestrationRunStatus.QUEUED
        self.stage = OrchestrationRunStage.QUEUED
        self.waiting_reason = None
        self.worker_id = None
        self.lane_lock_key = None
        self.queued_at = timestamp
        self.updated_at = timestamp
        self.record_event(
            Event(
                name=ORCHESTRATION_RUN_RESUMED_EVENT,
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
                    "reason": reason.strip() if reason is not None and reason.strip() else None,
                },
            ),
        )
