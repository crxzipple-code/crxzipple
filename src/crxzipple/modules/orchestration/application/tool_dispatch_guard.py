from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from crxzipple.modules.orchestration.domain import (
    OrchestrationRun,
    OrchestrationRunStatus,
)


@dataclass(frozen=True, slots=True)
class ToolDispatchGuard:
    external_guard: Callable[[OrchestrationRun], bool] | None = None

    def accepts(
        self,
        run: OrchestrationRun,
        *,
        require_running_run: bool,
    ) -> bool:
        if require_running_run and run.status is not OrchestrationRunStatus.RUNNING:
            return False
        if run.status in TERMINAL_RUN_STATUSES:
            return False
        if self.external_guard is None:
            return True
        return bool(self.external_guard(run))


TERMINAL_RUN_STATUSES = frozenset(
    {
        OrchestrationRunStatus.COMPLETED,
        OrchestrationRunStatus.FAILED,
        OrchestrationRunStatus.CANCELLED,
    },
)


__all__ = [
    "TERMINAL_RUN_STATUSES",
    "ToolDispatchGuard",
]
