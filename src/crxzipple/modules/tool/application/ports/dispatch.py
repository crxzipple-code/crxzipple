from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol

from crxzipple.modules.dispatch.domain import DispatchTaskRepository
from crxzipple.modules.tool.domain import ToolRun
from crxzipple.shared.domain.aggregates import AggregateRoot


class DispatchAggregateCollector(Protocol):
    def collect(self, aggregate: AggregateRoot[Any]) -> None:
        ...


@dataclass(frozen=True, slots=True)
class ToolOrchestrationDispatchClaim:
    run_id: str
    claimed_at: datetime | None = None


class ToolOrchestrationDispatchPort(Protocol):
    def enqueue(
        self,
        dispatch_tasks: DispatchTaskRepository,
        collector: DispatchAggregateCollector,
        run: ToolRun,
    ) -> None:
        ...

    def claim_next_queued(
        self,
        dispatch_tasks: DispatchTaskRepository,
        collector: DispatchAggregateCollector,
        *,
        worker_id: str,
        lease_seconds: int | None = None,
    ) -> ToolOrchestrationDispatchClaim | None:
        ...

    def claim_queued(
        self,
        dispatch_tasks: DispatchTaskRepository,
        collector: DispatchAggregateCollector,
        *,
        run_id: str,
        worker_id: str,
        lease_seconds: int | None = None,
    ) -> ToolOrchestrationDispatchClaim | None:
        ...

    def heartbeat(
        self,
        dispatch_tasks: DispatchTaskRepository,
        collector: DispatchAggregateCollector,
        run: ToolRun,
        *,
        worker_id: str,
        lease_seconds: int,
    ) -> None:
        ...

    def requeue(
        self,
        dispatch_tasks: DispatchTaskRepository,
        collector: DispatchAggregateCollector,
        run: ToolRun,
        *,
        reason: str | None = None,
    ) -> None:
        ...

    def complete(
        self,
        dispatch_tasks: DispatchTaskRepository,
        collector: DispatchAggregateCollector,
        run: ToolRun,
    ) -> None:
        ...

    def fail(
        self,
        dispatch_tasks: DispatchTaskRepository,
        collector: DispatchAggregateCollector,
        run: ToolRun,
    ) -> None:
        ...

    def cancel(
        self,
        dispatch_tasks: DispatchTaskRepository,
        collector: DispatchAggregateCollector,
        run: ToolRun,
    ) -> None:
        ...

    def recover_abandoned_run_ids(self, *, reason: str) -> list[str]:
        ...
