from __future__ import annotations

from dataclasses import dataclass, field

from crxzipple.modules.dispatch.application import (
    DispatchApplicationService,
    RecoverAbandonedDispatchTasksInput,
)
from crxzipple.modules.orchestration.application.dispatch_owner_kinds import (
    ORCHESTRATION_STEP_DISPATCH_OWNER_KIND,
)
from crxzipple.modules.orchestration.application.ports import (
    OrchestrationDispatchClaim,
    OrchestrationDispatchPort,
)
from crxzipple.modules.orchestration.infrastructure.dispatchers import (
    OrchestrationDispatchBridge,
)

DISPATCH_OWNER_KIND = ORCHESTRATION_STEP_DISPATCH_OWNER_KIND


@dataclass(slots=True)
class OrchestrationDispatchAdapter(OrchestrationDispatchPort):
    bridge: OrchestrationDispatchBridge = field(
        default_factory=OrchestrationDispatchBridge,
    )
    dispatch_service: DispatchApplicationService | None = None

    def enqueue(self, dispatch_tasks, collector, run, *, dispatch_task_id: str) -> None:
        self.bridge.enqueue(
            dispatch_tasks,
            collector,
            run,
            dispatch_task_id=dispatch_task_id,
        )

    def claim_queued(
        self,
        dispatch_tasks,
        collector,
        run,
        *,
        dispatch_task_id: str,
        worker_id: str,
        lease_seconds: int | None = None,
    ) -> OrchestrationDispatchClaim | None:
        task = self.bridge.claim_queued(
            dispatch_tasks,
            collector,
            run,
            dispatch_task_id=dispatch_task_id,
            worker_id=worker_id,
            lease_seconds=lease_seconds,
        )
        if task is None:
            return None
        return OrchestrationDispatchClaim(
            run_id=self._run_id_from_task(task),
            claimed_at=task.claimed_at,
        )

    def heartbeat(
        self,
        dispatch_tasks,
        collector,
        run,
        *,
        dispatch_task_id: str,
        worker_id: str,
        lease_seconds: int,
    ) -> None:
        self.bridge.heartbeat(
            dispatch_tasks,
            collector,
            run,
            dispatch_task_id=dispatch_task_id,
            worker_id=worker_id,
            lease_seconds=lease_seconds,
        )

    def wait(self, dispatch_tasks, collector, run, *, dispatch_task_id: str) -> None:
        self.bridge.wait(
            dispatch_tasks,
            collector,
            run,
            dispatch_task_id=dispatch_task_id,
        )

    def complete(self, dispatch_tasks, collector, run, *, dispatch_task_id: str) -> None:
        self.bridge.complete(
            dispatch_tasks,
            collector,
            run,
            dispatch_task_id=dispatch_task_id,
        )

    def fail(self, dispatch_tasks, collector, run, *, dispatch_task_id: str) -> None:
        self.bridge.fail(
            dispatch_tasks,
            collector,
            run,
            dispatch_task_id=dispatch_task_id,
        )

    def cancel(self, dispatch_tasks, collector, run, *, dispatch_task_id: str) -> None:
        self.bridge.cancel(
            dispatch_tasks,
            collector,
            run,
            dispatch_task_id=dispatch_task_id,
        )

    def recover_abandoned_dispatch_task_ids(self, *, reason: str) -> list[str]:
        if self.dispatch_service is None:
            raise RuntimeError("Orchestration dispatch service is not configured.")
        recovered_tasks = self.dispatch_service.recover_abandoned_tasks(
            RecoverAbandonedDispatchTasksInput(
                owner_kind=DISPATCH_OWNER_KIND,
                reason=reason,
            ),
        )
        return [task.id for task in recovered_tasks]

    @staticmethod
    def _run_id_from_task(task) -> str:
        if isinstance(task.payload_ref, str) and task.payload_ref.strip():
            return task.payload_ref.strip()
        raw_run_id = task.metadata.get("run_id")
        if isinstance(raw_run_id, str) and raw_run_id.strip():
            return raw_run_id.strip()
        raise RuntimeError(
            f"Dispatch task '{task.id}' does not reference an orchestration run.",
        )
