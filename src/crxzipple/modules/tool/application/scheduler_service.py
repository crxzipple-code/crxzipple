from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from threading import Event as ThreadEvent
from uuid import uuid4

from crxzipple.core.logger import get_logger
from crxzipple.modules.dispatch.application import dispatch_wakeup_topic
from crxzipple.modules.dispatch.domain import (
    DispatchPolicy,
    DispatchTask,
    DispatchTaskStatus,
)
from crxzipple.modules.events import EventsApplicationService
from crxzipple.modules.events.domain import EventTopicWatch
from crxzipple.modules.tool.application.catalog_service import ToolCatalogService
from crxzipple.modules.tool.application.concurrency import ToolRunConcurrencyPolicy
from crxzipple.modules.tool.application.service_support import (
    DISPATCH_LEASE_EXPIRED_REASON,
    ToolServiceBase,
    ToolServiceDependencies,
)
from crxzipple.modules.tool.domain.entities import (
    ToolRun,
    ToolRunAssignment,
    ToolWorkerRegistration,
)
from crxzipple.modules.tool.domain.exceptions import ToolRunNotFoundError
from crxzipple.modules.tool.domain.value_objects import (
    ToolRunAssignmentStatus,
    ToolWorkerStatus,
)
from crxzipple.shared.domain.events import Event, named_event_topic

logger = get_logger(__name__)
TOOL_RUN_DISPATCH_OWNER_KIND = "tool_run"


class ToolBackgroundSchedulerService(ToolServiceBase):
    def __init__(
        self,
        deps: ToolServiceDependencies,
        *,
        catalog_service: ToolCatalogService,
        concurrency_policy: ToolRunConcurrencyPolicy,
    ) -> None:
        super().__init__(deps)
        self.catalog_service = catalog_service
        self.concurrency_policy = concurrency_policy

    def recover_abandoned_runs(self) -> list[ToolRun]:
        recovered_ids = self.dispatch_port.recover_abandoned_run_ids(
            reason=DISPATCH_LEASE_EXPIRED_REASON,
        )
        if not recovered_ids:
            return []
        with self.uow_factory() as uow:
            recovered_runs = []
            for run_id in recovered_ids:
                run = uow.tool_runs.get(run_id)
                if run is not None:
                    recovered_runs.append(run)
            return recovered_runs

    def assign_next_available(self, *, worker_id: str | None = None) -> ToolRun | None:
        self.recover_abandoned_runs()
        with self.uow_factory() as uow:
            if worker_id is not None:
                worker = uow.tool_workers.get(worker_id)
                if (
                    worker is None
                    or worker.status is not ToolWorkerStatus.ONLINE
                    or self._worker_is_expired(worker)
                    or worker.current_in_flight >= worker.max_in_flight
                ):
                    return None
                selected_worker_id = worker.id
            else:
                workers = self._available_workers(uow)
                if not workers:
                    return None
                for worker in workers:
                    assigned = self._assign_next_queued_run_for_worker_in_uow(
                        uow,
                        worker_id=worker.id,
                    )
                    if assigned is not None:
                        return assigned
                return None
            return self._assign_next_queued_run_for_worker_in_uow(
                uow,
                worker_id=selected_worker_id,
            )

    def run_until_stopped(
        self,
        *,
        poll_interval_seconds: float,
        max_runs: int | None = None,
        max_idle_cycles: int | None = None,
        stop_event: ThreadEvent | None = None,
        events_service: EventsApplicationService | None = None,
    ) -> int:
        processed_runs = 0
        idle_cycles = 0
        stopper = stop_event or ThreadEvent()

        logger.info(
            "tool scheduler started",
            extra={
                "poll_interval_seconds": poll_interval_seconds,
                "max_runs": max_runs,
                "max_idle_cycles": max_idle_cycles,
            },
        )

        while not stopper.is_set():
            run = self.assign_next_available()
            if run is None:
                idle_cycles += 1
                if max_idle_cycles is not None and idle_cycles >= max_idle_cycles:
                    break
                if events_service is None:
                    stopper.wait(poll_interval_seconds)
                    continue
                events_service.wait_for_event_topics(
                    self._build_wait_watches(events_service),
                    timeout_seconds=poll_interval_seconds,
                    stop_event=stopper,
                )
                continue

            idle_cycles = 0
            processed_runs += 1
            if max_runs is not None and processed_runs >= max_runs:
                break

        return processed_runs

    def _assign_next_queued_run_for_worker_in_uow(
        self,
        uow,
        *,
        worker_id: str,
    ) -> ToolRun | None:
        run = self._claim_next_runnable_run_for_worker_in_uow(
            uow,
            worker_id=worker_id,
        )
        if run is None:
            return None
        run.dispatch(
            worker_id=worker_id,
            lease_seconds=self.worker_lease_seconds,
        )
        run.record_event(
            Event(
                name="tool.run.dispatching",
                payload={
                    "run_id": run.id,
                    "tool_id": run.tool_id,
                    "worker_id": worker_id,
                    "attempt_count": run.attempt_count,
                },
            ),
        )
        worker = uow.tool_workers.get(worker_id)
        if worker is None:
            worker = ToolWorkerRegistration.create(
                worker_id=worker_id,
                lease_seconds=self.worker_lease_seconds,
            )
        else:
            worker.refresh(lease_seconds=self.worker_lease_seconds)
        worker.reserve_slot()
        assignment = ToolRunAssignment.create(
            assignment_id=uuid4().hex,
            run_id=run.id,
            tool_id=run.tool_id,
            worker_id=worker_id,
            attempt_count=run.attempt_count,
            lease_seconds=self.worker_lease_seconds,
        )
        if uow.tool_workers.get(worker_id) is None:
            uow.tool_workers.add_new(worker)
        else:
            uow.tool_workers.add(worker)
        uow.tool_run_assignments.add_new(assignment)
        uow.tool_runs.add(run)
        uow.collect(worker)
        uow.collect(assignment)
        uow.collect(run)
        uow.commit()
        return run

    def _claim_next_runnable_run_for_worker_in_uow(
        self,
        uow,
        *,
        worker_id: str,
    ) -> ToolRun | None:
        active_counts = self._active_concurrency_counts_for_worker(
            uow,
            worker_id=worker_id,
        )
        for task in self._queued_dispatch_candidates(uow):
            run = uow.tool_runs.get(task.owner_id)
            if run is None:
                raise ToolRunNotFoundError(f"Tool run '{task.owner_id}' was not found.")
            tool = self.catalog_service.resolve_tool(run.tool_id)
            if not self.concurrency_policy.can_start(
                run=run,
                tool=tool,
                active_counts=active_counts,
            ):
                continue
            claim = self.dispatch_port.claim_queued(
                uow.dispatch_tasks,
                uow,
                run_id=run.id,
                worker_id=worker_id,
                lease_seconds=self.worker_lease_seconds,
            )
            if claim is None:
                continue
            claimed_run = uow.tool_runs.get(claim.run_id)
            if claimed_run is None:
                raise ToolRunNotFoundError(f"Tool run '{claim.run_id}' was not found.")
            return claimed_run
        return None

    def _active_concurrency_counts_for_worker(
        self,
        uow,
        *,
        worker_id: str,
    ) -> Counter[str]:
        counts: Counter[str] = Counter()
        assignments = [
            assignment
            for assignment in uow.tool_run_assignments.list_for_worker(worker_id)
            if assignment.status in {
                ToolRunAssignmentStatus.ASSIGNED,
                ToolRunAssignmentStatus.RUNNING,
            }
        ]
        runs_by_id = uow.tool_runs.get_many(
            tuple(assignment.run_id for assignment in assignments),
        )
        for assignment in assignments:
            run = runs_by_id.get(assignment.run_id)
            if run is None or run.is_terminal():
                continue
            tool = self.catalog_service.resolve_tool(run.tool_id)
            self.concurrency_policy.reserve(
                run=run,
                tool=tool,
                active_counts=counts,
            )
        return counts

    def _queued_dispatch_candidates(self, uow) -> list[DispatchTask]:
        active_lane_keys = {
            item.lane_key
            for status in (DispatchTaskStatus.CLAIMED, DispatchTaskStatus.WAITING)
            for item in uow.dispatch_tasks.list(status=status)
            if item.lane_key is not None
        }
        eligible_tasks = [
            item
            for item in uow.dispatch_tasks.list(
                status=DispatchTaskStatus.QUEUED,
                owner_kind=TOOL_RUN_DISPATCH_OWNER_KIND,
            )
            if item.lane_key is None or item.lane_key not in active_lane_keys
        ]
        lane_heads: dict[str, DispatchTask] = {}
        for item in sorted(eligible_tasks, key=self._lane_sort_key):
            lane_group = item.lane_key or item.id
            lane_heads.setdefault(lane_group, item)
        return sorted(lane_heads.values(), key=self._global_sort_key)

    def _available_workers(self, uow) -> list[ToolWorkerRegistration]:
        workers = []
        for worker in uow.tool_workers.list():
            if worker.status is not ToolWorkerStatus.ONLINE:
                continue
            if self._worker_is_expired(worker):
                worker.mark_stale()
                uow.tool_workers.add(worker)
                uow.collect(worker)
                continue
            if worker.current_in_flight >= worker.max_in_flight:
                continue
            workers.append(worker)
        workers.sort(
            key=lambda worker: (
                worker.current_in_flight,
                worker.heartbeat_at,
                worker.id,
            ),
        )
        return workers

    @staticmethod
    def _worker_is_expired(worker: ToolWorkerRegistration) -> bool:
        return (
            worker.lease_expires_at is not None
            and worker.lease_expires_at <= datetime.now(timezone.utc)
        )

    @staticmethod
    def _lane_sort_key(item: DispatchTask) -> tuple[object, ...]:
        return (
            item.priority,
            ToolBackgroundSchedulerService._lane_policy_rank(item.policy),
            item.queued_at or item.created_at,
            item.created_at,
            item.id,
        )

    @staticmethod
    def _global_sort_key(item: DispatchTask) -> tuple[object, ...]:
        return (
            item.priority,
            ToolBackgroundSchedulerService._global_policy_rank(item.policy),
            item.queued_at or item.created_at,
            item.created_at,
            item.id,
        )

    @staticmethod
    def _lane_policy_rank(policy: DispatchPolicy) -> int:
        if policy is DispatchPolicy.RESUME_FIRST:
            return 0
        if policy in {DispatchPolicy.JUMP_QUEUE, DispatchPolicy.LANE_JUMP_QUEUE}:
            return 1
        return 2

    @staticmethod
    def _global_policy_rank(policy: DispatchPolicy) -> int:
        if policy is DispatchPolicy.RESUME_FIRST:
            return 0
        if policy is DispatchPolicy.JUMP_QUEUE:
            return 1
        return 2

    @staticmethod
    def _build_wait_watches(
        events_service: EventsApplicationService,
    ) -> tuple[EventTopicWatch, ...]:
        topics = (
            dispatch_wakeup_topic("tool_run"),
            named_event_topic("tool.worker.registered"),
            named_event_topic("tool.assignment.succeeded"),
            named_event_topic("tool.assignment.failed"),
            named_event_topic("tool.assignment.cancelled"),
            named_event_topic("tool.assignment.expired"),
        )
        return tuple(
            EventTopicWatch(
                topic=topic,
                after_cursor=events_service.snapshot_event_topic(topic),
            )
            for topic in topics
        )
