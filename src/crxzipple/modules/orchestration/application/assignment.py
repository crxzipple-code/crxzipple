from __future__ import annotations

from dataclasses import dataclass

from crxzipple.modules.orchestration.domain import (
    OrchestrationExecutorLease,
    OrchestrationQueuePolicy,
    OrchestrationRun,
    OrchestrationRunStatus,
)


@dataclass(frozen=True, slots=True)
class OrchestrationAssignmentSelector:
    """Scheduler-owned assignment rules for executor and lane selection."""

    def available_executors(
        self,
        leases: list[OrchestrationExecutorLease],
    ) -> list[OrchestrationExecutorLease]:
        return sorted(
            (
                lease
                for lease in leases
                if lease.can_accept_assignment and not lease.is_expired()
            ),
            key=self.executor_sort_key,
        )

    def select_runnable_run(
        self,
        *,
        queued_runs: list[OrchestrationRun],
        active_runs: list[OrchestrationRun],
    ) -> OrchestrationRun | None:
        active_lane_keys = {
            run.lane_lock_key
            for run in active_runs
            if run.lane_lock_key is not None
            and run.status in {
                OrchestrationRunStatus.RUNNING,
                OrchestrationRunStatus.WAITING,
            }
        }
        eligible_runs = [
            run
            for run in queued_runs
            if run.status is OrchestrationRunStatus.QUEUED
            and (run.lane_key is None or run.lane_key not in active_lane_keys)
        ]
        lane_heads: dict[str, OrchestrationRun] = {}
        for run in sorted(eligible_runs, key=self.lane_sort_key):
            lane_group = run.lane_key or run.id
            lane_heads.setdefault(lane_group, run)
        runnable_runs = sorted(lane_heads.values(), key=self.global_sort_key)
        return runnable_runs[0] if runnable_runs else None

    @staticmethod
    def executor_sort_key(
        lease: OrchestrationExecutorLease,
    ) -> tuple[float, int, object, str]:
        capacity = max(lease.max_inflight_assignments, 1)
        utilization = lease.inflight_assignment_count / capacity
        return (
            utilization,
            lease.inflight_assignment_count,
            lease.updated_at,
            lease.worker_id,
        )

    @staticmethod
    def lane_sort_key(run: OrchestrationRun) -> tuple[object, ...]:
        return (
            run.priority,
            OrchestrationAssignmentSelector._lane_policy_rank(run.queue_policy),
            run.queued_at or run.created_at,
            run.created_at,
            run.id,
        )

    @staticmethod
    def global_sort_key(run: OrchestrationRun) -> tuple[object, ...]:
        return (
            run.priority,
            OrchestrationAssignmentSelector._global_policy_rank(run.queue_policy),
            run.queued_at or run.created_at,
            run.created_at,
            run.id,
        )

    @staticmethod
    def _lane_policy_rank(policy: OrchestrationQueuePolicy) -> int:
        if policy is OrchestrationQueuePolicy.RESUME_FIRST:
            return 0
        if policy in {
            OrchestrationQueuePolicy.JUMP_QUEUE,
            OrchestrationQueuePolicy.LANE_JUMP_QUEUE,
        }:
            return 1
        return 2

    @staticmethod
    def _global_policy_rank(policy: OrchestrationQueuePolicy) -> int:
        if policy is OrchestrationQueuePolicy.RESUME_FIRST:
            return 0
        if policy is OrchestrationQueuePolicy.JUMP_QUEUE:
            return 1
        return 2
