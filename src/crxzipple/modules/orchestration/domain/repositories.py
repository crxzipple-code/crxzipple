from __future__ import annotations

from datetime import datetime
from typing import Protocol

from crxzipple.modules.orchestration.domain.entities import (
    OrchestrationExecutorLease,
    OrchestrationIngressRequest,
    OrchestrationRun,
    OrchestrationSchedulerSignal,
)
from crxzipple.modules.orchestration.domain.value_objects import (
    OrchestrationExecutorLeaseStatus,
    OrchestrationIngressStatus,
    OrchestrationSchedulerSignalStatus,
    OrchestrationRunStatus,
)


class OrchestrationRunRepository(Protocol):
    def add(self, run: OrchestrationRun) -> None:
        ...

    def get(self, run_id: str) -> OrchestrationRun | None:
        ...

    def list(
        self,
        *,
        status: OrchestrationRunStatus | None = None,
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

    def claim_next(self, *, worker_id: str) -> OrchestrationIngressRequest | None:
        ...

    def claim_for_run(
        self,
        *,
        run_id: str,
        worker_id: str,
    ) -> OrchestrationIngressRequest | None:
        ...

    def list(
        self,
        *,
        status: OrchestrationIngressStatus | None = None,
    ) -> list[OrchestrationIngressRequest]:
        ...


class OrchestrationSchedulerSignalRepository(Protocol):
    def add(self, signal: OrchestrationSchedulerSignal) -> None:
        ...

    def get(self, signal_id: str) -> OrchestrationSchedulerSignal | None:
        ...

    def claim_next(self, *, worker_id: str) -> OrchestrationSchedulerSignal | None:
        ...

    def list(
        self,
        *,
        status: OrchestrationSchedulerSignalStatus | None = None,
    ) -> list[OrchestrationSchedulerSignal]:
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
