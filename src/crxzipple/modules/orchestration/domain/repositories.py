from __future__ import annotations

from datetime import datetime
from typing import Protocol

from crxzipple.modules.orchestration.domain.entities import (
    ExecutionChain,
    ExecutionStep,
    ExecutionStepItem,
    OrchestrationExecutorLease,
    OrchestrationIngressRequest,
    OrchestrationRun,
)
from crxzipple.modules.orchestration.domain.value_objects import (
    ExecutionChainStatus,
    ExecutionOwnerReference,
    ExecutionStepItemStatus,
    ExecutionStepStatus,
    OrchestrationExecutorLeaseStatus,
    OrchestrationIngressStatus,
    OrchestrationRunStatus,
)


class ExecutionChainRepository(Protocol):
    def add(self, chain: ExecutionChain) -> None:
        ...

    def get(self, chain_id: str) -> ExecutionChain | None:
        ...

    def get_active_for_turn(self, turn_id: str) -> ExecutionChain | None:
        ...

    def list_for_turn(
        self,
        turn_id: str,
        *,
        status: ExecutionChainStatus | None = None,
    ) -> list[ExecutionChain]:
        ...


class ExecutionStepRepository(Protocol):
    def add(self, step: ExecutionStep) -> None:
        ...

    def get(self, step_id: str) -> ExecutionStep | None:
        ...

    def get_by_correlation_key(self, correlation_key: str) -> ExecutionStep | None:
        ...

    def list_for_chain(
        self,
        chain_id: str,
        *,
        status: ExecutionStepStatus | None = None,
    ) -> list[ExecutionStep]:
        ...


class ExecutionStepItemRepository(Protocol):
    def add(self, item: ExecutionStepItem) -> None:
        ...

    def get(self, item_id: str) -> ExecutionStepItem | None:
        ...

    def find_by_owner_reference(
        self,
        owner: ExecutionOwnerReference,
        *,
        status: ExecutionStepItemStatus | None = None,
    ) -> list[ExecutionStepItem]:
        ...

    def list_for_step(
        self,
        step_id: str,
        *,
        status: ExecutionStepItemStatus | None = None,
    ) -> list[ExecutionStepItem]:
        ...

    def list_for_steps(
        self,
        step_ids: tuple[str, ...],
        *,
        status: ExecutionStepItemStatus | None = None,
    ) -> list[ExecutionStepItem]:
        ...


class OrchestrationRunRepository(Protocol):
    def add(self, run: OrchestrationRun) -> None:
        ...

    def get(self, run_id: str) -> OrchestrationRun | None:
        ...

    def list(
        self,
        *,
        status: OrchestrationRunStatus | None = None,
        session_key: str | None = None,
    ) -> list[OrchestrationRun]:
        ...

    def find_next_assigned(
        self,
        *,
        worker_id: str,
        exclude_run_ids: tuple[str, ...] = (),
    ) -> OrchestrationRun | None:
        ...

    def claim_queued_for_assignment(
        self,
        *,
        run_id: str,
        worker_id: str,
        claimed_at: datetime | None = None,
    ) -> OrchestrationRun | None:
        ...


class OrchestrationRunWaitRepository(Protocol):
    def replace_tool_waits(self, run_id: str, tool_run_ids: tuple[str, ...]) -> None:
        ...

    def delete_for_run(self, run_id: str) -> None:
        ...

    def list_run_ids_for_tool_run(self, tool_run_id: str) -> list[str]:
        ...


class OrchestrationIngressRequestRepository(Protocol):
    def add(self, request: OrchestrationIngressRequest) -> None:
        ...

    def get(self, request_id: str) -> OrchestrationIngressRequest | None:
        ...

    def get_by_run_id(self, run_id: str) -> OrchestrationIngressRequest | None:
        ...

    def list(
        self,
        *,
        status: OrchestrationIngressStatus | None = None,
    ) -> list[OrchestrationIngressRequest]:
        ...


class OrchestrationExecutorLeaseRepository(Protocol):
    def add(self, lease: OrchestrationExecutorLease) -> None:
        ...

    def get(self, worker_id: str) -> OrchestrationExecutorLease | None:
        ...

    def heartbeat(
        self,
        *,
        worker_id: str,
        max_inflight_assignments: int | None = None,
        inflight_assignment_count: int | None = None,
        draining: bool | None = None,
        metadata: dict[str, object] | None = None,
        lease_seconds: int | None = None,
    ) -> OrchestrationExecutorLease | None:
        ...

    def claim_assignment_capacity(
        self,
        *,
        worker_id: str,
        lease_seconds: int | None = None,
    ) -> OrchestrationExecutorLease | None:
        ...

    def release_assignment_capacity(self, *, worker_id: str, count: int = 1) -> None:
        ...

    def list(
        self,
        *,
        status: OrchestrationExecutorLeaseStatus | None = None,
    ) -> list[OrchestrationExecutorLease]:
        ...
