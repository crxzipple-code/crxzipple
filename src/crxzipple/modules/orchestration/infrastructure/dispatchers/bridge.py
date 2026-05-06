from __future__ import annotations

from crxzipple.modules.dispatch.domain import (
    DispatchPolicy,
    DispatchTask,
    DispatchTaskRepository,
)
from crxzipple.modules.orchestration.domain import (
    OrchestrationQueuePolicy,
    OrchestrationRun,
)
from crxzipple.shared.domain.aggregates import AggregateRoot

DISPATCH_OWNER_KIND = "orchestration_run"


class OrchestrationDispatchBridge:
    """Maps orchestration run queue transitions onto the dispatch domain."""

    def enqueue(
        self,
        dispatch_tasks: DispatchTaskRepository,
        collector: "_AggregateCollector",
        run: OrchestrationRun,
    ) -> DispatchTask:
        task = self._ensure_task(dispatch_tasks, collector, run)
        task.enqueue(
            lane_key=run.lane_key,
            policy=self._to_dispatch_policy(run.queue_policy),
            priority=run.priority,
            queued_at=run.queued_at,
        )
        dispatch_tasks.add(task)
        collector.collect(task)
        return task

    def claim_queued(
        self,
        dispatch_tasks: DispatchTaskRepository,
        collector: "_AggregateCollector",
        run: OrchestrationRun,
        *,
        worker_id: str,
        lease_seconds: int | None = None,
    ) -> DispatchTask | None:
        task = dispatch_tasks.claim_queued(
            task_id=run.id,
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
        run: OrchestrationRun,
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
            now=run.updated_at,
        )
        dispatch_tasks.add(task)
        collector.collect(task)
        return task

    def wait(
        self,
        dispatch_tasks: DispatchTaskRepository,
        collector: "_AggregateCollector",
        run: OrchestrationRun,
    ) -> DispatchTask:
        task = self._require_task(dispatch_tasks, run.id)
        task.wait(reason=run.waiting_reason, now=run.updated_at)
        dispatch_tasks.add(task)
        collector.collect(task)
        return task

    def complete(
        self,
        dispatch_tasks: DispatchTaskRepository,
        collector: "_AggregateCollector",
        run: OrchestrationRun,
    ) -> DispatchTask:
        task = self._require_task(dispatch_tasks, run.id)
        task.complete(now=run.completed_at)
        dispatch_tasks.add(task)
        collector.collect(task)
        return task

    def fail(
        self,
        dispatch_tasks: DispatchTaskRepository,
        collector: "_AggregateCollector",
        run: OrchestrationRun,
    ) -> DispatchTask:
        task = self._require_task(dispatch_tasks, run.id)
        error = run.error
        task.fail(
            message=error.message if error is not None else "orchestration failed",
            code=error.code if error is not None else "orchestration_failed",
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
        run: OrchestrationRun,
    ) -> DispatchTask | None:
        task = dispatch_tasks.get(run.id)
        if task is None:
            return None
        task.cancel(reason=run.waiting_reason, now=run.completed_at)
        dispatch_tasks.add(task)
        collector.collect(task)
        return task

    def _ensure_task(
        self,
        dispatch_tasks: DispatchTaskRepository,
        collector: "_AggregateCollector",
        run: OrchestrationRun,
    ) -> DispatchTask:
        task = dispatch_tasks.get(run.id)
        if task is not None:
            return task
        task = DispatchTask.create(
            task_id=run.id,
            owner_kind=DISPATCH_OWNER_KIND,
            owner_id=run.id,
            lane_key=run.lane_key,
            policy=self._to_dispatch_policy(run.queue_policy),
            priority=run.priority,
            payload_ref=run.id,
            metadata={
                "session_key": run.session_key,
                "agent_id": run.agent_id,
            },
        )
        collector.collect(task)
        return task

    @staticmethod
    def _require_task(
        dispatch_tasks: DispatchTaskRepository,
        task_id: str,
    ) -> DispatchTask:
        task = dispatch_tasks.get(task_id)
        if task is None:
            raise RuntimeError(
                f"Dispatch task '{task_id}' was not found for orchestration run.",
            )
        return task

    @staticmethod
    def _claim_token_for_worker(worker_id: str) -> str:
        return f"orchestration:{worker_id}"

    @staticmethod
    def _to_dispatch_policy(policy: OrchestrationQueuePolicy) -> DispatchPolicy:
        return DispatchPolicy(policy.value)


class _AggregateCollector:
    def collect(self, aggregate: AggregateRoot[object]) -> None:
        ...
