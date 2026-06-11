from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from crxzipple.modules.orchestration.application.commands import (
    AdvanceAssignmentInput,
    CompleteAssignmentInput,
    FailAssignmentInput,
    WaitAssignmentOnToolInput,
    WaitForConfirmationInput,
)
from crxzipple.modules.orchestration.application.lease_manager import (
    OrchestrationLeaseManager,
)
from crxzipple.modules.orchestration.domain.entities import OrchestrationRun
from crxzipple.modules.orchestration.domain.exceptions import (
    OrchestrationRunNotFoundError,
)
from crxzipple.modules.orchestration.domain.value_objects import (
    OrchestrationRunStatus,
)

if TYPE_CHECKING:
    from crxzipple.modules.orchestration.application.coordinators import (
        RunProgressCoordinator,
        RunWaitCoordinator,
    )
    from crxzipple.modules.orchestration.application.unit_of_work import (
        OrchestrationUnitOfWork,
    )


@dataclass(slots=True)
class RunAssignmentLifecycleService:
    """Owns assignment lifecycle side effects across progress, wait and leases."""

    uow_factory: Callable[[], "OrchestrationUnitOfWork"]
    lease_manager: OrchestrationLeaseManager
    get_run: Callable[[str], OrchestrationRun]
    progress_coordinator: Callable[[], "RunProgressCoordinator"]
    wait_coordinator: Callable[[], "RunWaitCoordinator"]
    queue_child_completion_continuation: Callable[[OrchestrationRun], None]

    def process_next_assigned_assignment(
        self,
        *,
        worker_id: str,
        exclude_run_ids: tuple[str, ...] = (),
    ) -> OrchestrationRun | None:
        return self.progress_coordinator().process_next_assigned_assignment(
            worker_id=worker_id,
            exclude_run_ids=exclude_run_ids,
        )

    def next_assigned_assignment(
        self,
        *,
        worker_id: str,
        exclude_run_ids: tuple[str, ...] = (),
    ) -> OrchestrationRun | None:
        return self.progress_coordinator().next_assigned_assignment(
            worker_id=worker_id,
            exclude_run_ids=exclude_run_ids,
        )

    def process_assigned_assignment(
        self,
        *,
        run_id: str,
        worker_id: str,
    ) -> OrchestrationRun:
        return self.progress_coordinator().process_assigned_assignment(
            run_id=run_id,
            worker_id=worker_id,
        )

    async def process_assigned_assignment_async(
        self,
        *,
        run_id: str,
        worker_id: str,
    ) -> OrchestrationRun:
        return await self.progress_coordinator().process_assigned_assignment_async(
            run_id=run_id,
            worker_id=worker_id,
        )

    def advance_assignment(self, data: AdvanceAssignmentInput) -> OrchestrationRun:
        return self.progress_coordinator().advance_assignment(data)

    def wait_assignment_on_tool(
        self,
        data: WaitAssignmentOnToolInput,
    ) -> OrchestrationRun:
        run = self.wait_coordinator().wait_assignment_on_tool(data)
        self.lease_manager.release_executor_assignment(worker_id=data.worker_id)
        return run

    def wait_for_confirmation(
        self,
        data: WaitForConfirmationInput,
    ) -> OrchestrationRun:
        run = self.wait_coordinator().wait_for_confirmation(data)
        self.lease_manager.release_executor_assignment(worker_id=data.worker_id)
        return run

    def heartbeat_assignment(
        self,
        run_id: str,
        *,
        worker_id: str,
    ) -> OrchestrationRun:
        return self.lease_manager.heartbeat_assignment(
            run_id,
            worker_id=worker_id,
            get_run=self._get_run_from_uow,
        )

    def complete_assignment(self, data: CompleteAssignmentInput) -> OrchestrationRun:
        completed = self.progress_coordinator().complete_assignment(data)
        self.lease_manager.release_executor_assignment(worker_id=data.worker_id)
        self.queue_child_completion_continuation(completed)
        return completed

    def fail_assignment(self, data: FailAssignmentInput) -> OrchestrationRun:
        current_run = self.get_run(data.run_id)
        if current_run.status in {
            OrchestrationRunStatus.COMPLETED,
            OrchestrationRunStatus.FAILED,
            OrchestrationRunStatus.CANCELLED,
        }:
            return current_run
        release_worker_id = (
            (data.worker_id or current_run.worker_id)
            if current_run.status is OrchestrationRunStatus.RUNNING
            else None
        )
        failed = self.progress_coordinator().fail_assignment(data)
        if release_worker_id is not None:
            self.lease_manager.release_executor_assignment(worker_id=release_worker_id)
        return failed

    def clear_prompt_flow_hint(self, run_id: str) -> None:
        with self.uow_factory() as uow:
            run = self._get_run_from_uow(uow, run_id)
            if "prompt_flow_hint" not in run.metadata:
                return
            run.metadata.pop("prompt_flow_hint", None)
            uow.orchestration_runs.add(run)
            uow.collect(run)
            uow.commit()

    def admit_assignment(
        self,
        *,
        run_id: str,
        worker_id: str,
        acquire_lane_lock: bool = True,
    ) -> OrchestrationRun:
        return self.lease_manager.admit_assignment(
            run_id,
            worker_id=worker_id,
            get_run=self._get_run_from_uow,
            acquire_lane_lock=acquire_lane_lock,
        )

    @staticmethod
    def _get_run_from_uow(uow: Any, run_id: str) -> OrchestrationRun:
        run = uow.orchestration_runs.get(run_id)
        if run is None:
            raise OrchestrationRunNotFoundError(
                f"Orchestration run '{run_id}' was not found.",
            )
        return run


__all__ = ["RunAssignmentLifecycleService"]
