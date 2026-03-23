from __future__ import annotations

from dataclasses import dataclass

from crxzipple.modules.dispatch.application.services import (
    CancelDispatchTaskInput,
    CompleteDispatchTaskInput,
    DispatchApplicationService,
    FailDispatchTaskInput,
    HeartbeatDispatchTaskInput,
    RequeueDispatchTaskInput,
    RecoverAbandonedDispatchTasksInput,
    WaitDispatchTaskInput,
)
from crxzipple.modules.dispatch.domain import DispatchPolicy, DispatchTask


@dataclass(slots=True)
class DispatchWorker:
    service: DispatchApplicationService

    def claim_next(
        self,
        *,
        owner_kind: str | None = None,
        worker_id: str,
        claim_token: str | None = None,
        lease_seconds: int | None = None,
    ) -> DispatchTask | None:
        return self.service.claim_next_queued_task(
            owner_kind=owner_kind,
            worker_id=worker_id,
            claim_token=claim_token,
            lease_seconds=lease_seconds,
        )

    def wait(
        self,
        *,
        task_id: str,
        reason: str | None = None,
    ) -> DispatchTask:
        return self.service.wait_task(
            WaitDispatchTaskInput(task_id=task_id, reason=reason),
        )

    def heartbeat(
        self,
        *,
        task_id: str,
        worker_id: str,
        lease_seconds: int,
        claim_token: str | None = None,
    ) -> DispatchTask:
        return self.service.heartbeat_task(
            HeartbeatDispatchTaskInput(
                task_id=task_id,
                worker_id=worker_id,
                lease_seconds=lease_seconds,
                claim_token=claim_token,
            ),
        )

    def requeue(
        self,
        *,
        task_id: str,
        policy: DispatchPolicy | None = None,
        priority: int | None = None,
        reason: str | None = None,
    ) -> DispatchTask:
        return self.service.requeue_task(
            RequeueDispatchTaskInput(
                task_id=task_id,
                policy=policy,
                priority=priority,
                reason=reason,
            ),
        )

    def recover_abandoned(
        self,
        *,
        owner_kind: str | None = None,
        reason: str = "Dispatch worker lease expired before completion.",
    ) -> list[DispatchTask]:
        return self.service.recover_abandoned_tasks(
            RecoverAbandonedDispatchTasksInput(
                owner_kind=owner_kind,
                reason=reason,
            ),
        )

    def complete(self, *, task_id: str) -> DispatchTask:
        return self.service.complete_task(CompleteDispatchTaskInput(task_id=task_id))

    def cancel(self, *, task_id: str, reason: str | None = None) -> DispatchTask:
        return self.service.cancel_task(
            CancelDispatchTaskInput(task_id=task_id, reason=reason),
        )

    def fail(
        self,
        *,
        task_id: str,
        message: str,
        code: str = "dispatch_failed",
        details: dict[str, object] | None = None,
    ) -> DispatchTask:
        return self.service.fail_task(
            FailDispatchTaskInput(
                task_id=task_id,
                message=message,
                code=code,
                details=details or {},
            ),
        )
