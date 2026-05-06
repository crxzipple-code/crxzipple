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
class RunDispatchClaim:
    run_id: str
    claimed_at: datetime | None = None


class RunDispatchPort(Protocol):
    def enqueue(
        self,
        dispatch_tasks: DispatchTaskRepository,
        collector: DispatchAggregateCollector,
        run: OrchestrationRun,
    ) -> None:
        ...

    def claim_queued(
        self,
        dispatch_tasks: DispatchTaskRepository,
        collector: DispatchAggregateCollector,
        run: OrchestrationRun,
        *,
        worker_id: str,
        lease_seconds: int | None = None,
    ) -> RunDispatchClaim | None:
        ...

    def heartbeat(
        self,
        dispatch_tasks: DispatchTaskRepository,
        collector: DispatchAggregateCollector,
        run: OrchestrationRun,
        *,
        worker_id: str,
        lease_seconds: int,
    ) -> None:
        ...

    def wait(
        self,
        dispatch_tasks: DispatchTaskRepository,
        collector: DispatchAggregateCollector,
        run: OrchestrationRun,
    ) -> None:
        ...

    def complete(
        self,
        dispatch_tasks: DispatchTaskRepository,
        collector: DispatchAggregateCollector,
        run: OrchestrationRun,
    ) -> None:
        ...

    def fail(
        self,
        dispatch_tasks: DispatchTaskRepository,
        collector: DispatchAggregateCollector,
        run: OrchestrationRun,
    ) -> None:
        ...

    def cancel(
        self,
        dispatch_tasks: DispatchTaskRepository,
        collector: DispatchAggregateCollector,
        run: OrchestrationRun,
    ) -> None:
        ...

    def recover_abandoned_run_ids(self, *, reason: str) -> list[str]:
        ...
