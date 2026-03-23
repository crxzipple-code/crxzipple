from __future__ import annotations

from datetime import datetime, timedelta

from crxzipple.modules.dispatch.domain import DispatchPolicy, DispatchTask, DispatchTaskStatus
from crxzipple.modules.dispatch.domain.value_objects import utcnow


class InMemoryDispatchTaskRepository:
    def __init__(self) -> None:
        self._items: dict[str, DispatchTask] = {}

    def add(self, task: DispatchTask) -> None:
        self._items[task.id] = task

    def get(self, task_id: str) -> DispatchTask | None:
        return self._items.get(task_id)

    def list(
        self,
        *,
        status: DispatchTaskStatus | None = None,
        owner_kind: str | None = None,
        lane_key: str | None = None,
    ) -> list[DispatchTask]:
        items = list(self._items.values())
        if status is not None:
            items = [item for item in items if item.status is status]
        if owner_kind is not None:
            items = [item for item in items if item.owner_kind == owner_kind]
        if lane_key is not None:
            items = [item for item in items if item.lane_key == lane_key]
        return sorted(items, key=lambda item: (item.created_at, item.id), reverse=True)

    def claim_next_queued(
        self,
        *,
        owner_kind: str | None = None,
        worker_id: str,
        claim_token: str,
        lease_seconds: int | None = None,
    ) -> DispatchTask | None:
        active_lane_keys = {
            item.lane_key
            for item in self._items.values()
            if item.lane_key is not None
            and item.status in {
                DispatchTaskStatus.CLAIMED,
                DispatchTaskStatus.WAITING,
            }
        }
        eligible_tasks = [
            item
            for item in self._items.values()
            if item.status is DispatchTaskStatus.QUEUED
            and (owner_kind is None or item.owner_kind == owner_kind)
            and (item.lane_key is None or item.lane_key not in active_lane_keys)
        ]
        lane_heads: dict[str, DispatchTask] = {}
        for item in sorted(eligible_tasks, key=self._lane_sort_key):
            lane_group = item.lane_key or item.id
            lane_heads.setdefault(lane_group, item)

        queued_tasks = sorted(lane_heads.values(), key=self._global_sort_key)
        if not queued_tasks:
            return None
        task = queued_tasks[0]
        timestamp = utcnow()
        task.status = DispatchTaskStatus.CLAIMED
        task.claimed_by = worker_id
        task.claim_token = claim_token
        task.claimed_at = timestamp
        task.heartbeat_at = timestamp
        task.lease_expires_at = (
            None
            if lease_seconds is None
            else timestamp + timedelta(seconds=lease_seconds)
        )
        task.updated_at = timestamp
        return task

    def recover_abandoned(
        self,
        *,
        owner_kind: str | None = None,
        now: datetime | None = None,
    ) -> list[DispatchTask]:
        timestamp = now or utcnow()
        recovered = [
            item
            for item in self._items.values()
            if item.status is DispatchTaskStatus.CLAIMED
            and item.lease_expires_at is not None
            and item.lease_expires_at < timestamp
            and (owner_kind is None or item.owner_kind == owner_kind)
        ]
        recovered.sort(key=lambda item: (item.lease_expires_at, item.id))
        return recovered

    @staticmethod
    def _lane_sort_key(item: DispatchTask) -> tuple[object, ...]:
        return (
            item.priority,
            InMemoryDispatchTaskRepository._lane_policy_rank(item.policy),
            item.queued_at or item.created_at,
            item.created_at,
            item.id,
        )

    @staticmethod
    def _global_sort_key(item: DispatchTask) -> tuple[object, ...]:
        return (
            item.priority,
            InMemoryDispatchTaskRepository._global_policy_rank(item.policy),
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
