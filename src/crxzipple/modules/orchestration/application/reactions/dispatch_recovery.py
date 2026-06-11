from __future__ import annotations

from dataclasses import dataclass

from crxzipple.core.logger import get_logger
from crxzipple.modules.orchestration.application.dispatch_owner_kinds import (
    ORCHESTRATION_STEP_DISPATCH_OWNER_KIND,
)
from crxzipple.modules.orchestration.application.scheduler_service import (
    OrchestrationSchedulerService,
)
from crxzipple.shared.domain.events import Event

logger = get_logger(__name__)


@dataclass(slots=True)
class OrchestrationDispatchRecoveryReaction:
    scheduler_service: OrchestrationSchedulerService

    def react_to_recovered_dispatch_task(self, event: Event) -> None:
        if event.payload.get("owner_kind") != ORCHESTRATION_STEP_DISPATCH_OWNER_KIND:
            return
        dispatch_task_id = event.payload.get("owner_id")
        reason = event.payload.get("reason")
        if not isinstance(dispatch_task_id, str) or not dispatch_task_id.strip():
            return
        if not isinstance(reason, str) or not reason.strip():
            return
        try:
            self.scheduler_service.handle_recovered_dispatch_task(
                dispatch_task_id=dispatch_task_id,
                reason=reason,
            )
        except Exception:
            logger.exception(
                "failed to reconcile recovered dispatch task for orchestration run",
                extra={
                    "event_name": event.name,
                    "dispatch_task_id": dispatch_task_id,
                },
            )
