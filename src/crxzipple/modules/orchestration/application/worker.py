from __future__ import annotations

from dataclasses import dataclass

from crxzipple.modules.orchestration.domain.entities import OrchestrationRun
from crxzipple.modules.orchestration.application.services import (
    AdvanceOrchestrationRunInput,
    CompleteOrchestrationRunInput,
    FailOrchestrationRunInput,
    OrchestrationApplicationService,
    ResumeOrchestrationRunInput,
    WaitOnToolInput,
)
from crxzipple.modules.orchestration.domain.value_objects import OrchestrationRunStage
from crxzipple.modules.orchestration.domain.value_objects import OrchestrationQueuePolicy


@dataclass(slots=True)
class OrchestrationWorker:
    """Queue consumer helpers for orchestration workers."""

    service: OrchestrationApplicationService

    def claim_next(self, *, worker_id: str) -> OrchestrationRun | None:
        return self.service.claim_next_queued_run(worker_id=worker_id)

    def process_next(self, *, worker_id: str) -> OrchestrationRun | None:
        return self.service.process_next_queued_run(worker_id=worker_id)

    def heartbeat(
        self,
        *,
        run_id: str,
        worker_id: str,
    ) -> OrchestrationRun:
        return self.service.heartbeat_run(run_id, worker_id=worker_id)

    def recover_abandoned(self) -> list[OrchestrationRun]:
        return self.service.recover_abandoned_runs()

    def advance_once(
        self,
        *,
        run_id: str,
        worker_id: str,
    ) -> OrchestrationRun:
        return self.service.advance_once(
            run_id=run_id,
            worker_id=worker_id,
        )

    def advance(
        self,
        *,
        run_id: str,
        worker_id: str,
        stage: OrchestrationRunStage,
        step_increment: int = 0,
        metadata: dict[str, object] | None = None,
    ) -> OrchestrationRun:
        return self.service.advance_run(
            AdvanceOrchestrationRunInput(
                run_id=run_id,
                worker_id=worker_id,
                stage=stage,
                step_increment=step_increment,
                metadata=metadata or {},
            ),
        )

    def wait_on_tool(
        self,
        *,
        run_id: str,
        worker_id: str,
        pending_tool_run_ids: tuple[str, ...],
        reason: str | None = None,
    ) -> OrchestrationRun:
        return self.service.wait_on_tool(
            WaitOnToolInput(
                run_id=run_id,
                worker_id=worker_id,
                pending_tool_run_ids=pending_tool_run_ids,
                reason=reason,
            ),
        )

    def resume(
        self,
        *,
        run_id: str,
        lane_key: str | None = None,
        queue_policy: OrchestrationQueuePolicy | None = None,
        priority: int | None = None,
        reason: str | None = None,
        clear_pending_tool_run_ids: bool = True,
    ) -> OrchestrationRun:
        return self.service.resume_run(
            ResumeOrchestrationRunInput(
                run_id=run_id,
                lane_key=lane_key,
                queue_policy=queue_policy,
                priority=priority,
                reason=reason,
                clear_pending_tool_run_ids=clear_pending_tool_run_ids,
            ),
        )

    def complete(
        self,
        *,
        run_id: str,
        worker_id: str,
        result_payload: dict[str, object] | None = None,
    ) -> OrchestrationRun:
        return self.service.complete_run(
            CompleteOrchestrationRunInput(
                run_id=run_id,
                worker_id=worker_id,
                result_payload=result_payload or {},
            ),
        )

    def fail(
        self,
        *,
        run_id: str,
        message: str,
        code: str = "orchestration_failed",
        details: dict[str, object] | None = None,
        worker_id: str | None = None,
    ) -> OrchestrationRun:
        return self.service.fail_run(
            FailOrchestrationRunInput(
                run_id=run_id,
                message=message,
                code=code,
                details=details or {},
                worker_id=worker_id,
            ),
        )
