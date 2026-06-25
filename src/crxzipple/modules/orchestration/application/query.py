"""Read-side queries for orchestration runs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from crxzipple.modules.dispatch.domain import DispatchTask, DispatchTaskStatus
from crxzipple.modules.orchestration.application.unit_of_work import (
    OrchestrationUnitOfWork,
)
from crxzipple.modules.orchestration.application.coordinators.continuation_tasks import (
    OrchestrationContinuationStatus,
    OrchestrationContinuationTask,
    continuation_dispatch_owner_kind,
    continuation_task_from_dispatch_task,
)
from crxzipple.modules.orchestration.domain.entities import (
    ExecutionChain,
    ExecutionStep,
    ExecutionStepItem,
    OrchestrationExecutorLease,
    OrchestrationIngressRequest,
    OrchestrationRun,
)
from crxzipple.modules.orchestration.domain.exceptions import (
    OrchestrationRunNotFoundError,
)
from crxzipple.modules.orchestration.domain.value_objects import (
    ExecutionChainStatus,
    ExecutionOwnerReference,
    ExecutionStepItemStatus,
    ExecutionStepStatus,
    OrchestrationExecutorLeaseStatus,
    OrchestrationIngressStatus,
    OrchestrationRunStatus,
    PendingApprovalRequest,
)


@dataclass(frozen=True, slots=True)
class ExecutionStepSnapshot:
    step: ExecutionStep
    items: tuple[ExecutionStepItem, ...]


@dataclass(frozen=True, slots=True)
class ExecutionChainSnapshot:
    chain: ExecutionChain
    steps: tuple[ExecutionStepSnapshot, ...]


@dataclass(frozen=True, slots=True)
class ExecutionWaitingItemRef:
    item: ExecutionStepItem
    step: ExecutionStep
    chain: ExecutionChain


@dataclass(frozen=True, slots=True)
class ExecutionWaitingStatus:
    run: OrchestrationRun
    active_chain: ExecutionChain | None
    waiting_steps: tuple[ExecutionStep, ...]
    waiting_items: tuple[ExecutionWaitingItemRef, ...]
    pending_tool_run_ids: tuple[str, ...]
    pending_approval_request: PendingApprovalRequest | None
    waiting_reason: str | None


@dataclass(slots=True)
class OrchestrationRunQueryService:
    uow_factory: Callable[[], OrchestrationUnitOfWork]

    def get_run(self, run_id: str) -> OrchestrationRun:
        with self.uow_factory() as uow:
            run = uow.orchestration_runs.get(run_id)
            if run is None:
                raise OrchestrationRunNotFoundError(
                    f"Orchestration run '{run_id}' was not found.",
                )
            return run

    def list_runs(
        self,
        *,
        status: OrchestrationRunStatus | None = None,
        session_key: str | None = None,
    ) -> list[OrchestrationRun]:
        with self.uow_factory() as uow:
            return uow.orchestration_runs.list(
                status=status,
                session_key=session_key,
            )

    def get_active_execution_chain(self, turn_id: str) -> ExecutionChain | None:
        with self.uow_factory() as uow:
            return uow.execution_chains.get_active_for_turn(turn_id)

    def list_execution_chains(
        self,
        turn_id: str,
        *,
        status: ExecutionChainStatus | None = None,
    ) -> list[ExecutionChain]:
        with self.uow_factory() as uow:
            return uow.execution_chains.list_for_turn(turn_id, status=status)

    def get_execution_step(self, step_id: str) -> ExecutionStep | None:
        with self.uow_factory() as uow:
            return uow.execution_steps.get(step_id)

    def get_execution_step_by_correlation_key(
        self,
        correlation_key: str,
    ) -> ExecutionStep | None:
        with self.uow_factory() as uow:
            return uow.execution_steps.get_by_correlation_key(correlation_key)

    def list_execution_chain_snapshots(
        self,
        turn_id: str,
        *,
        chain_status: ExecutionChainStatus | None = None,
        step_status: ExecutionStepStatus | None = None,
        item_status: ExecutionStepItemStatus | None = None,
    ) -> list[ExecutionChainSnapshot]:
        with self.uow_factory() as uow:
            snapshots: list[ExecutionChainSnapshot] = []
            chains = uow.execution_chains.list_for_turn(
                turn_id,
                status=chain_status,
            )
            for chain in chains:
                step_snapshots: list[ExecutionStepSnapshot] = []
                steps = uow.execution_steps.list_for_chain(
                    chain.id,
                    status=step_status,
                )
                items_by_step: dict[str, list[ExecutionStepItem]] = {
                    step.id: [] for step in steps
                }
                step_items = uow.execution_step_items.list_for_steps(
                    tuple(step.id for step in steps),
                    status=item_status,
                )
                for item in step_items:
                    items_by_step.setdefault(item.step_id, []).append(item)
                for step in steps:
                    step_snapshots.append(
                        ExecutionStepSnapshot(
                            step=step,
                            items=tuple(items_by_step.get(step.id, ())),
                        ),
                    )
                snapshots.append(
                    ExecutionChainSnapshot(
                        chain=chain,
                        steps=tuple(step_snapshots),
                    ),
                )
            return snapshots

    def get_execution_waiting_status(self, run_id: str) -> ExecutionWaitingStatus:
        with self.uow_factory() as uow:
            run = uow.orchestration_runs.get(run_id)
            if run is None:
                raise OrchestrationRunNotFoundError(
                    f"Orchestration run '{run_id}' was not found.",
                )
            active_chain = uow.execution_chains.get_active_for_turn(run.id)
            waiting_steps: list[ExecutionStep] = []
            waiting_items: list[ExecutionWaitingItemRef] = []
            if active_chain is not None:
                waiting_steps = uow.execution_steps.list_for_chain(
                    active_chain.id,
                    status=ExecutionStepStatus.WAITING,
                )
                for step in waiting_steps:
                    for item in uow.execution_step_items.list_for_step(
                        step.id,
                        status=ExecutionStepItemStatus.WAITING,
                    ):
                        waiting_items.append(
                            ExecutionWaitingItemRef(
                                item=item,
                                step=step,
                                chain=active_chain,
                            ),
                        )
            return ExecutionWaitingStatus(
                run=run,
                active_chain=active_chain,
                waiting_steps=tuple(waiting_steps),
                waiting_items=tuple(waiting_items),
                pending_tool_run_ids=tuple(run.pending_tool_run_ids),
                pending_approval_request=run.pending_approval_request(),
                waiting_reason=run.waiting_reason,
            )

    def list_execution_steps(
        self,
        chain_id: str,
        *,
        status: ExecutionStepStatus | None = None,
    ) -> list[ExecutionStep]:
        with self.uow_factory() as uow:
            return uow.execution_steps.list_for_chain(chain_id, status=status)

    def get_execution_step_item(self, item_id: str) -> ExecutionStepItem | None:
        with self.uow_factory() as uow:
            return uow.execution_step_items.get(item_id)

    def list_execution_step_items(
        self,
        step_id: str,
        *,
        status: ExecutionStepItemStatus | None = None,
    ) -> list[ExecutionStepItem]:
        with self.uow_factory() as uow:
            return uow.execution_step_items.list_for_step(step_id, status=status)

    def find_execution_step_items_by_owner(
        self,
        owner: ExecutionOwnerReference,
        *,
        status: ExecutionStepItemStatus | None = None,
    ) -> list[ExecutionStepItem]:
        with self.uow_factory() as uow:
            return uow.execution_step_items.find_by_owner_reference(
                owner,
                status=status,
            )

    def list_ingress_requests(
        self,
        *,
        status: OrchestrationIngressStatus | None = None,
    ) -> list[OrchestrationIngressRequest]:
        with self.uow_factory() as uow:
            return uow.orchestration_ingress_requests.list(status=status)

    def list_continuation_tasks(
        self,
        *,
        status: OrchestrationContinuationStatus | None = None,
    ) -> list[OrchestrationContinuationTask]:
        with self.uow_factory() as uow:
            continuations = [
                continuation
                for task in uow.dispatch_tasks.list(
                    owner_kind=continuation_dispatch_owner_kind(),
                )
                for continuation in (continuation_task_from_dispatch_task(task),)
                if continuation is not None
            ]
            if status is not None:
                continuations = [
                    continuation
                    for continuation in continuations
                    if continuation.status is status
                ]
            return continuations

    def list_dispatch_tasks(
        self,
        *,
        status: DispatchTaskStatus | None = None,
        owner_kind: str | None = None,
        lane_key: str | None = None,
    ) -> list[DispatchTask]:
        with self.uow_factory() as uow:
            return uow.dispatch_tasks.list(
                status=status,
                owner_kind=owner_kind,
                lane_key=lane_key,
            )

    def list_executor_leases(
        self,
        *,
        status: OrchestrationExecutorLeaseStatus | None = None,
    ) -> list[OrchestrationExecutorLease]:
        with self.uow_factory() as uow:
            return uow.orchestration_executor_leases.list(status=status)
