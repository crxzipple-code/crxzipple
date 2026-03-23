from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Protocol
from uuid import uuid4

from crxzipple.modules.dispatch.domain import (
    DispatchPolicy,
    DispatchTask,
    DispatchTaskNotFoundError,
    DispatchTaskRepository,
    DispatchTaskStatus,
)
from crxzipple.shared.domain.aggregates import AggregateRoot


@dataclass(frozen=True, slots=True)
class CreateDispatchTaskInput:
    owner_kind: str
    owner_id: str
    lane_key: str | None = None
    task_id: str | None = None
    policy: DispatchPolicy = DispatchPolicy.FIFO
    priority: int = 100
    payload_ref: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class EnqueueDispatchTaskInput:
    task_id: str
    lane_key: str | None = None
    policy: DispatchPolicy | None = None
    priority: int | None = None
    now: datetime | None = None


@dataclass(frozen=True, slots=True)
class WaitDispatchTaskInput:
    task_id: str
    reason: str | None = None
    now: datetime | None = None


@dataclass(frozen=True, slots=True)
class HeartbeatDispatchTaskInput:
    task_id: str
    worker_id: str
    lease_seconds: int
    claim_token: str | None = None
    now: datetime | None = None


@dataclass(frozen=True, slots=True)
class RequeueDispatchTaskInput:
    task_id: str
    policy: DispatchPolicy | None = None
    priority: int | None = None
    reason: str | None = None
    now: datetime | None = None


@dataclass(frozen=True, slots=True)
class CompleteDispatchTaskInput:
    task_id: str
    now: datetime | None = None


@dataclass(frozen=True, slots=True)
class CancelDispatchTaskInput:
    task_id: str
    reason: str | None = None
    now: datetime | None = None


@dataclass(frozen=True, slots=True)
class FailDispatchTaskInput:
    task_id: str
    message: str
    code: str = "dispatch_failed"
    details: dict[str, object] = field(default_factory=dict)
    now: datetime | None = None


@dataclass(frozen=True, slots=True)
class RecoverAbandonedDispatchTasksInput:
    owner_kind: str | None = None
    reason: str = "Dispatch worker lease expired before completion."
    now: datetime | None = None


class DispatchUnitOfWork(Protocol):
    dispatch_tasks: DispatchTaskRepository

    def __enter__(self) -> "DispatchUnitOfWork":
        ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> None:
        ...

    def collect(self, aggregate: AggregateRoot[Any]) -> None:
        ...

    def commit(self) -> None:
        ...

    def rollback(self) -> None:
        ...


class DispatchApplicationService:
    def __init__(self, uow_factory: Callable[[], DispatchUnitOfWork]) -> None:
        self.uow_factory = uow_factory

    def create_task(self, data: CreateDispatchTaskInput) -> DispatchTask:
        task = DispatchTask.create(
            task_id=data.task_id or uuid4().hex,
            owner_kind=data.owner_kind,
            owner_id=data.owner_id,
            lane_key=data.lane_key,
            policy=data.policy,
            priority=data.priority,
            payload_ref=data.payload_ref,
            metadata=data.metadata,
        )
        with self.uow_factory() as uow:
            uow.dispatch_tasks.add(task)
            uow.collect(task)
            uow.commit()
            return task

    def enqueue_task(self, data: EnqueueDispatchTaskInput) -> DispatchTask:
        with self.uow_factory() as uow:
            task = self._get_task(uow, data.task_id)
            task.enqueue(
                lane_key=data.lane_key,
                policy=data.policy,
                priority=data.priority,
                queued_at=data.now,
            )
            uow.dispatch_tasks.add(task)
            uow.collect(task)
            uow.commit()
            return task

    def claim_next_queued_task(
        self,
        *,
        owner_kind: str | None = None,
        worker_id: str,
        claim_token: str | None = None,
        lease_seconds: int | None = None,
    ) -> DispatchTask | None:
        resolved_claim_token = claim_token or uuid4().hex
        with self.uow_factory() as uow:
            task = uow.dispatch_tasks.claim_next_queued(
                owner_kind=owner_kind,
                worker_id=worker_id,
                claim_token=resolved_claim_token,
                lease_seconds=lease_seconds,
            )
            if task is None:
                return None
            task.claim(
                worker_id=worker_id,
                claim_token=resolved_claim_token,
                lease_seconds=lease_seconds,
                claimed_at=task.claimed_at,
            )
            uow.dispatch_tasks.add(task)
            uow.collect(task)
            uow.commit()
            return task

    def wait_task(self, data: WaitDispatchTaskInput) -> DispatchTask:
        with self.uow_factory() as uow:
            task = self._get_task(uow, data.task_id)
            task.wait(reason=data.reason, now=data.now)
            uow.dispatch_tasks.add(task)
            uow.collect(task)
            uow.commit()
            return task

    def heartbeat_task(self, data: HeartbeatDispatchTaskInput) -> DispatchTask:
        with self.uow_factory() as uow:
            task = self._get_task(uow, data.task_id)
            task.heartbeat(
                worker_id=data.worker_id,
                lease_seconds=data.lease_seconds,
                claim_token=data.claim_token,
                now=data.now,
            )
            uow.dispatch_tasks.add(task)
            uow.collect(task)
            uow.commit()
            return task

    def requeue_task(self, data: RequeueDispatchTaskInput) -> DispatchTask:
        with self.uow_factory() as uow:
            task = self._get_task(uow, data.task_id)
            task.requeue(
                policy=data.policy,
                priority=data.priority,
                reason=data.reason,
                now=data.now,
            )
            uow.dispatch_tasks.add(task)
            uow.collect(task)
            uow.commit()
            return task

    def recover_abandoned_tasks(
        self,
        data: RecoverAbandonedDispatchTasksInput,
    ) -> list[DispatchTask]:
        with self.uow_factory() as uow:
            tasks = uow.dispatch_tasks.recover_abandoned(
                owner_kind=data.owner_kind,
                now=data.now,
            )
            if not tasks:
                return []
            task_ids = [task.id for task in tasks]
            for task in tasks:
                task.recover_abandoned(reason=data.reason, now=data.now)
                uow.dispatch_tasks.add(task)
                uow.collect(task)
            uow.commit()
        with self.uow_factory() as uow:
            latest_tasks = [
                task
                for task_id in task_ids
                for task in [uow.dispatch_tasks.get(task_id)]
                if task is not None
            ]
        return latest_tasks

    def complete_task(self, data: CompleteDispatchTaskInput) -> DispatchTask:
        with self.uow_factory() as uow:
            task = self._get_task(uow, data.task_id)
            task.complete(now=data.now)
            uow.dispatch_tasks.add(task)
            uow.collect(task)
            uow.commit()
            return task

    def cancel_task(self, data: CancelDispatchTaskInput) -> DispatchTask:
        with self.uow_factory() as uow:
            task = self._get_task(uow, data.task_id)
            task.cancel(reason=data.reason, now=data.now)
            uow.dispatch_tasks.add(task)
            uow.collect(task)
            uow.commit()
            return task

    def fail_task(self, data: FailDispatchTaskInput) -> DispatchTask:
        with self.uow_factory() as uow:
            task = self._get_task(uow, data.task_id)
            task.fail(
                message=data.message,
                code=data.code,
                details=data.details,
                now=data.now,
            )
            uow.dispatch_tasks.add(task)
            uow.collect(task)
            uow.commit()
            return task

    def get_task(self, task_id: str) -> DispatchTask:
        with self.uow_factory() as uow:
            return self._get_task(uow, task_id)

    def list_tasks(
        self,
        *,
        status: DispatchTaskStatus | None = None,
        owner_kind: str | None = None,
        lane_key: str | None = None,
    ) -> list[DispatchTask]:
        with self.uow_factory() as uow:
            return uow.dispatch_tasks.list(
                status=status,
                owner_kind=owner_kind,
                lane_key=lane_key,
            )

    @staticmethod
    def _get_task(uow: DispatchUnitOfWork, task_id: str) -> DispatchTask:
        task = uow.dispatch_tasks.get(task_id)
        if task is None:
            raise DispatchTaskNotFoundError(
                f"Dispatch task '{task_id}' was not found.",
            )
        return task
