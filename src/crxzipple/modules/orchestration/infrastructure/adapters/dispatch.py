from __future__ import annotations

from dataclasses import dataclass

from crxzipple.modules.dispatch.application import (
    DispatchApplicationService,
    RecoverAbandonedDispatchTasksInput,
)
from crxzipple.modules.orchestration.application.dispatch_bridge import (
    OrchestrationDispatchBridge,
)
from crxzipple.modules.orchestration.application.ports import (
    RunDispatchClaim,
    RunDispatchPort,
)

DISPATCH_OWNER_KIND = "orchestration_run"


@dataclass(slots=True)
class OrchestrationRunDispatchAdapter(RunDispatchPort):
    bridge: OrchestrationDispatchBridge
    dispatch_service: DispatchApplicationService | None = None

    def enqueue(self, dispatch_tasks, collector, run) -> None:
        self.bridge.enqueue(dispatch_tasks, collector, run)

    def claim_next_queued(
        self,
        dispatch_tasks,
        collector,
        *,
        worker_id: str,
        lease_seconds: int | None = None,
    ) -> RunDispatchClaim | None:
        task = self.bridge.claim_next_queued(
            dispatch_tasks,
            collector,
            worker_id=worker_id,
            lease_seconds=lease_seconds,
        )
        if task is None:
            return None
        return RunDispatchClaim(
            run_id=task.owner_id,
            claimed_at=task.claimed_at,
        )

    def heartbeat(self, dispatch_tasks, collector, run, *, worker_id: str, lease_seconds: int) -> None:
        self.bridge.heartbeat(
            dispatch_tasks,
            collector,
            run,
            worker_id=worker_id,
            lease_seconds=lease_seconds,
        )

    def wait(self, dispatch_tasks, collector, run) -> None:
        self.bridge.wait(dispatch_tasks, collector, run)

    def complete(self, dispatch_tasks, collector, run) -> None:
        self.bridge.complete(dispatch_tasks, collector, run)

    def fail(self, dispatch_tasks, collector, run) -> None:
        self.bridge.fail(dispatch_tasks, collector, run)

    def cancel(self, dispatch_tasks, collector, run) -> None:
        self.bridge.cancel(dispatch_tasks, collector, run)

    def recover_abandoned_run_ids(self, *, reason: str) -> list[str]:
        if self.dispatch_service is None:
            raise RuntimeError("Orchestration dispatch service is not configured.")
        recovered_tasks = self.dispatch_service.recover_abandoned_tasks(
            RecoverAbandonedDispatchTasksInput(
                owner_kind=DISPATCH_OWNER_KIND,
                reason=reason,
            ),
        )
        return [task.owner_id for task in recovered_tasks]
