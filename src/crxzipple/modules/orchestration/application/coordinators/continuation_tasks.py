from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Callable, Protocol

from crxzipple.modules.dispatch.domain import (
    DispatchErrorPayload,
    DispatchPolicy,
    DispatchTask,
    DispatchTaskRepository,
    DispatchTaskStatus,
)
from crxzipple.modules.orchestration.application.dispatch_owner_kinds import (
    ORCHESTRATION_CONTINUATION_DISPATCH_OWNER_KIND,
)
from crxzipple.shared.domain.aggregates import AggregateRoot

_CONTINUATION_TASK_KIND = "orchestration_continuation"
_DEFAULT_CONTINUATION_LEASE_SECONDS = 300


class OrchestrationContinuationKind(StrEnum):
    TOOL_TERMINAL = "tool_terminal"
    SESSIONS_SPAWN_FOLLOWUP = "sessions_spawn_followup"


class OrchestrationContinuationStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class OrchestrationContinuationTask:
    id: str
    continuation_kind: OrchestrationContinuationKind
    payload: dict[str, object]
    status: OrchestrationContinuationStatus
    worker_id: str | None
    error: DispatchErrorPayload | None
    created_at: datetime
    updated_at: datetime
    claimed_at: datetime | None = None
    completed_at: datetime | None = None


class ContinuationCoordinatorUnitOfWork(Protocol):
    dispatch_tasks: DispatchTaskRepository

    def __enter__(self) -> "ContinuationCoordinatorUnitOfWork":
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


@dataclass(slots=True)
class RunContinuationCoordinator:
    uow_factory: Callable[[], ContinuationCoordinatorUnitOfWork]
    lease_seconds: int = _DEFAULT_CONTINUATION_LEASE_SECONDS

    def queue_tool_terminal_continuation(
        self,
        *,
        tool_run_id: str,
    ) -> OrchestrationContinuationTask:
        normalized_tool_run_id = tool_run_id.strip()
        task_id = f"tool-terminal:{normalized_tool_run_id}"
        return self._queue_continuation(
            task_id=task_id,
            continuation_kind=OrchestrationContinuationKind.TOOL_TERMINAL,
            payload={"tool_run_id": normalized_tool_run_id},
            payload_ref=normalized_tool_run_id,
        )

    def queue_sessions_spawn_followup_continuation(
        self,
        *,
        child_run_id: str,
    ) -> OrchestrationContinuationTask:
        normalized_child_run_id = child_run_id.strip()
        task_id = f"sessions-spawn-followup:{normalized_child_run_id}"
        return self._queue_continuation(
            task_id=task_id,
            continuation_kind=OrchestrationContinuationKind.SESSIONS_SPAWN_FOLLOWUP,
            payload={"child_run_id": normalized_child_run_id},
            payload_ref=normalized_child_run_id,
        )

    def claim_next_continuation(
        self,
        *,
        worker_id: str,
    ) -> OrchestrationContinuationTask | None:
        with self.uow_factory() as uow:
            recovered = uow.dispatch_tasks.recover_abandoned(
                owner_kind=ORCHESTRATION_CONTINUATION_DISPATCH_OWNER_KIND,
            )
            for task in recovered:
                task.recover_abandoned(
                    reason="Orchestration continuation lease expired before processing.",
                )
                uow.dispatch_tasks.add(task)
                uow.collect(task)
            task = uow.dispatch_tasks.claim_next_queued(
                owner_kind=ORCHESTRATION_CONTINUATION_DISPATCH_OWNER_KIND,
                worker_id=worker_id,
                claim_token=_claim_token(worker_id),
                lease_seconds=self.lease_seconds,
            )
            if task is None:
                if recovered:
                    uow.commit()
                return None
            task.claim(
                worker_id=worker_id,
                claim_token=_claim_token(worker_id),
                lease_seconds=self.lease_seconds,
                claimed_at=task.claimed_at,
            )
            uow.dispatch_tasks.add(task)
            uow.collect(task)
            uow.commit()
            return continuation_task_from_dispatch_task(task)

    def complete_continuation(
        self,
        task_id: str,
    ) -> OrchestrationContinuationTask | None:
        with self.uow_factory() as uow:
            task = uow.dispatch_tasks.get(task_id)
            if task is None or not is_orchestration_continuation_task(task):
                return None
            task.complete()
            uow.dispatch_tasks.add(task)
            uow.collect(task)
            uow.commit()
            return continuation_task_from_dispatch_task(task)

    def fail_continuation(
        self,
        task_id: str,
        *,
        message: str,
        code: str = "orchestration_continuation_failed",
        details: dict[str, object] | None = None,
    ) -> OrchestrationContinuationTask | None:
        with self.uow_factory() as uow:
            task = uow.dispatch_tasks.get(task_id)
            if task is None or not is_orchestration_continuation_task(task):
                return None
            task.fail(
                message=message,
                code=code,
                details=details or {},
            )
            uow.dispatch_tasks.add(task)
            uow.collect(task)
            uow.commit()
            return continuation_task_from_dispatch_task(task)

    def _queue_continuation(
        self,
        *,
        task_id: str,
        continuation_kind: OrchestrationContinuationKind,
        payload: dict[str, object],
        payload_ref: str | None = None,
    ) -> OrchestrationContinuationTask:
        try:
            return self._queue_continuation_once(
                task_id=task_id,
                continuation_kind=continuation_kind,
                payload=payload,
                payload_ref=payload_ref,
            )
        except Exception:
            existing = self._get_equivalent_continuation_task(
                task_id=task_id,
                continuation_kind=continuation_kind,
                payload=payload,
            )
            if existing is not None:
                return _continuation_from_dispatch_task(existing)
            raise

    def _queue_continuation_once(
        self,
        *,
        task_id: str,
        continuation_kind: OrchestrationContinuationKind,
        payload: dict[str, object],
        payload_ref: str | None = None,
    ) -> OrchestrationContinuationTask:
        with self.uow_factory() as uow:
            existing = uow.dispatch_tasks.get(task_id)
            if existing is not None and is_orchestration_continuation_task(existing):
                return _continuation_from_dispatch_task(existing)
            task = DispatchTask.create(
                task_id=task_id,
                owner_kind=ORCHESTRATION_CONTINUATION_DISPATCH_OWNER_KIND,
                owner_id=task_id,
                policy=DispatchPolicy.RESUME_FIRST,
                priority=0,
                payload_ref=payload_ref,
                metadata={
                    "task_kind": _CONTINUATION_TASK_KIND,
                    "continuation_kind": continuation_kind.value,
                    "continuation_payload": dict(payload),
                },
            )
            task.enqueue(policy=DispatchPolicy.RESUME_FIRST, priority=0)
            uow.dispatch_tasks.add(task)
            uow.collect(task)
            uow.commit()
            return _continuation_from_dispatch_task(task)

    def _get_equivalent_continuation_task(
        self,
        *,
        task_id: str,
        continuation_kind: OrchestrationContinuationKind,
        payload: dict[str, object],
    ) -> DispatchTask | None:
        with self.uow_factory() as uow:
            existing = uow.dispatch_tasks.get(task_id)
        if existing is None or not is_orchestration_continuation_task(existing):
            return None
        if existing.metadata.get("continuation_kind") != continuation_kind.value:
            return None
        if existing.metadata.get("continuation_payload") != payload:
            return None
        return existing


def continuation_dispatch_owner_kind() -> str:
    return ORCHESTRATION_CONTINUATION_DISPATCH_OWNER_KIND


def continuation_task_from_dispatch_task(
    task: DispatchTask,
) -> OrchestrationContinuationTask | None:
    if not is_orchestration_continuation_task(task):
        return None
    return _continuation_from_dispatch_task(task)


def is_orchestration_continuation_task(task: DispatchTask) -> bool:
    return (
        task.owner_kind == ORCHESTRATION_CONTINUATION_DISPATCH_OWNER_KIND
        and task.metadata.get("task_kind") == _CONTINUATION_TASK_KIND
    )


def _continuation_from_dispatch_task(
    task: DispatchTask,
) -> OrchestrationContinuationTask:
    continuation_kind = OrchestrationContinuationKind(
        str(task.metadata.get("continuation_kind", "")),
    )
    payload = task.metadata.get("continuation_payload")
    return OrchestrationContinuationTask(
        id=task.id,
        continuation_kind=continuation_kind,
        payload=dict(payload) if isinstance(payload, dict) else {},
        status=_continuation_status_from_dispatch_status(task.status),
        worker_id=task.claimed_by,
        error=task.error,
        created_at=task.created_at,
        updated_at=task.updated_at,
        claimed_at=task.claimed_at,
        completed_at=task.completed_at,
    )


def _continuation_status_from_dispatch_status(
    status: DispatchTaskStatus,
) -> OrchestrationContinuationStatus:
    if status is DispatchTaskStatus.CLAIMED:
        return OrchestrationContinuationStatus.PROCESSING
    if status is DispatchTaskStatus.COMPLETED:
        return OrchestrationContinuationStatus.COMPLETED
    if status in {DispatchTaskStatus.FAILED, DispatchTaskStatus.CANCELLED}:
        return OrchestrationContinuationStatus.FAILED
    return OrchestrationContinuationStatus.QUEUED


def _claim_token(worker_id: str) -> str:
    return f"orchestration-continuation:{worker_id.strip()}"
