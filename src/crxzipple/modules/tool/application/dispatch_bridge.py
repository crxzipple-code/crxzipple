from __future__ import annotations

from crxzipple.modules.dispatch.domain import (
    DispatchPolicy,
    DispatchTask,
    DispatchTaskRepository,
)
from crxzipple.modules.tool.domain.entities import ToolRun
from crxzipple.shared.domain.aggregates import AggregateRoot

DISPATCH_OWNER_KIND = "tool_run"


class ToolDispatchBridge:
    """Maps background tool run scheduling onto the dispatch domain."""

    def enqueue(
        self,
        dispatch_tasks: DispatchTaskRepository,
        collector: "_AggregateCollector",
        run: ToolRun,
    ) -> DispatchTask:
        task = self._ensure_task(dispatch_tasks, collector, run)
        task.enqueue(
            policy=DispatchPolicy.FIFO,
            priority=100,
        )
        dispatch_tasks.add(task)
        collector.collect(task)
        return task

    def claim_next_queued(
        self,
        dispatch_tasks: DispatchTaskRepository,
        collector: "_AggregateCollector",
        *,
        worker_id: str,
        lease_seconds: int | None = None,
    ) -> DispatchTask | None:
        task = dispatch_tasks.claim_next_queued(
            owner_kind=DISPATCH_OWNER_KIND,
            worker_id=worker_id,
            claim_token=self._claim_token_for_worker(worker_id),
            lease_seconds=lease_seconds,
        )
        if task is None:
            return None
        task.claim(
            worker_id=worker_id,
            claim_token=task.claim_token or self._claim_token_for_worker(worker_id),
            lease_seconds=lease_seconds,
            claimed_at=task.claimed_at,
        )
        dispatch_tasks.add(task)
        collector.collect(task)
        return task

    def heartbeat(
        self,
        dispatch_tasks: DispatchTaskRepository,
        collector: "_AggregateCollector",
        run: ToolRun,
        *,
        worker_id: str,
        lease_seconds: int,
    ) -> DispatchTask | None:
        task = dispatch_tasks.get(run.id)
        if task is None:
            return None
        task.heartbeat(
            worker_id=worker_id,
            lease_seconds=lease_seconds,
            claim_token=self._claim_token_for_worker(worker_id),
            now=run.heartbeat_at,
        )
        dispatch_tasks.add(task)
        collector.collect(task)
        return task

    def requeue(
        self,
        dispatch_tasks: DispatchTaskRepository,
        collector: "_AggregateCollector",
        run: ToolRun,
        *,
        reason: str | None = None,
    ) -> DispatchTask | None:
        task = dispatch_tasks.get(run.id)
        if task is None:
            return None
        task.requeue(
            policy=DispatchPolicy.FIFO,
            priority=100,
            reason=reason,
        )
        dispatch_tasks.add(task)
        collector.collect(task)
        return task

    def complete(
        self,
        dispatch_tasks: DispatchTaskRepository,
        collector: "_AggregateCollector",
        run: ToolRun,
    ) -> DispatchTask | None:
        task = dispatch_tasks.get(run.id)
        if task is None:
            return None
        task.complete(now=run.completed_at)
        dispatch_tasks.add(task)
        collector.collect(task)
        return task

    def fail(
        self,
        dispatch_tasks: DispatchTaskRepository,
        collector: "_AggregateCollector",
        run: ToolRun,
    ) -> DispatchTask | None:
        task = dispatch_tasks.get(run.id)
        if task is None:
            return None
        error = run.error
        task.fail(
            message=error.message if error is not None else "tool run failed",
            code=error.code if error is not None else "tool_run_failed",
            details=error.details if error is not None else {},
            now=run.completed_at,
        )
        dispatch_tasks.add(task)
        collector.collect(task)
        return task

    def cancel(
        self,
        dispatch_tasks: DispatchTaskRepository,
        collector: "_AggregateCollector",
        run: ToolRun,
    ) -> DispatchTask | None:
        task = dispatch_tasks.get(run.id)
        if task is None:
            return None
        task.cancel(reason=run.error_message, now=run.completed_at)
        dispatch_tasks.add(task)
        collector.collect(task)
        return task

    def _ensure_task(
        self,
        dispatch_tasks: DispatchTaskRepository,
        collector: "_AggregateCollector",
        run: ToolRun,
    ) -> DispatchTask:
        task = dispatch_tasks.get(run.id)
        if task is not None:
            return task
        task = DispatchTask.create(
            task_id=run.id,
            owner_kind=DISPATCH_OWNER_KIND,
            owner_id=run.id,
            policy=DispatchPolicy.FIFO,
            priority=100,
            payload_ref=run.id,
            metadata={
                "tool_id": run.tool_id,
                "mode": run.target.mode.value,
                "strategy": run.target.strategy.value,
                "environment": run.target.environment.value,
            },
        )
        collector.collect(task)
        return task

    @staticmethod
    def _claim_token_for_worker(worker_id: str) -> str:
        return f"tool:{worker_id}"


class _AggregateCollector:
    def collect(self, aggregate: AggregateRoot[object]) -> None:
        ...
