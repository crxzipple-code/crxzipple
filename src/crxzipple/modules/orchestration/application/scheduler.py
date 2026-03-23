from __future__ import annotations

from crxzipple.modules.orchestration.domain.entities import OrchestrationRun
from crxzipple.modules.orchestration.domain.value_objects import (
    OrchestrationQueuePolicy,
)


class OrchestrationScheduler:
    """Minimal queue coordination helper for phase 1."""

    def enqueue(
        self,
        run: OrchestrationRun,
        *,
        lane_key: str | None = None,
        queue_policy: OrchestrationQueuePolicy | None = None,
        priority: int | None = None,
    ) -> None:
        run.enqueue(
            lane_key=lane_key,
            queue_policy=queue_policy,
            priority=priority,
        )
