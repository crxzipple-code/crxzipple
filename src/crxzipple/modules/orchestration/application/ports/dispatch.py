from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from crxzipple.modules.dispatch.domain import DispatchTaskRepository
from crxzipple.modules.orchestration.domain import OrchestrationRun
from crxzipple.shared.domain.aggregates import AggregateRoot


class DispatchAggregateCollector(Protocol):
    def collect(self, aggregate: AggregateRoot[Any]) -> None:
        ...


@dataclass(frozen=True, slots=True)
class OrchestrationDispatchClaim:
    run_id: str
    claimed_at: datetime | None = None


class OrchestrationDispatchPort(Protocol):
    def enqueue(
        self,
        dispatch_tasks: DispatchTaskRepository,
        collector: DispatchAggregateCollector,
        run: OrchestrationRun,
        *,
        dispatch_task_id: str,
    ) -> None:
        ...

    def claim_queued(
        self,
        dispatch_tasks: DispatchTaskRepository,
        collector: DispatchAggregateCollector,
        run: OrchestrationRun,
        *,
        dispatch_task_id: str,
        worker_id: str,
        lease_seconds: int | None = None,
    ) -> OrchestrationDispatchClaim | None:
        ...

    def heartbeat(
        self,
        dispatch_tasks: DispatchTaskRepository,
        collector: DispatchAggregateCollector,
        run: OrchestrationRun,
        *,
        dispatch_task_id: str,
        worker_id: str,
        lease_seconds: int,
    ) -> None:
        ...

    def wait(
        self,
        dispatch_tasks: DispatchTaskRepository,
        collector: DispatchAggregateCollector,
        run: OrchestrationRun,
        *,
        dispatch_task_id: str,
    ) -> None:
        ...

    def complete(
        self,
        dispatch_tasks: DispatchTaskRepository,
        collector: DispatchAggregateCollector,
        run: OrchestrationRun,
        *,
        dispatch_task_id: str,
    ) -> None:
        ...

    def fail(
        self,
        dispatch_tasks: DispatchTaskRepository,
        collector: DispatchAggregateCollector,
        run: OrchestrationRun,
        *,
        dispatch_task_id: str,
    ) -> None:
        ...

    def cancel(
        self,
        dispatch_tasks: DispatchTaskRepository,
        collector: DispatchAggregateCollector,
        run: OrchestrationRun,
        *,
        dispatch_task_id: str,
    ) -> None:
        ...

    def recover_abandoned_dispatch_task_ids(self, *, reason: str) -> list[str]:
        ...
