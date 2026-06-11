from __future__ import annotations

from dataclasses import dataclass

from crxzipple.modules.orchestration.domain import (
    OrchestrationExecutorLease,
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
