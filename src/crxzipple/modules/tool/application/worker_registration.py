from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from crxzipple.modules.tool.domain.entities import ToolWorkerRegistration
from crxzipple.shared.domain.events import Event


@dataclass(frozen=True, slots=True)
class WorkerPruneResult:
    pruned_worker_ids: tuple[str, ...]
    cutoff: datetime

    @property
    def pruned_count(self) -> int:
        return len(self.pruned_worker_ids)


def register_or_refresh_worker(
    uow,
    *,
    worker_id: str,
    lease_seconds: int,
    max_in_flight: int,
    capabilities_payload: dict[str, Any],
) -> ToolWorkerRegistration:
    worker = uow.tool_workers.get(worker_id)
    if worker is None:
        worker = ToolWorkerRegistration.create(
            worker_id=worker_id,
            lease_seconds=lease_seconds,
            max_in_flight=max_in_flight,
            capabilities_payload=capabilities_payload,
        )
        uow.tool_workers.add_new(worker)
    else:
        worker.refresh(
            lease_seconds=lease_seconds,
            max_in_flight=max_in_flight,
            capabilities_payload=capabilities_payload,
        )
        reconcile_worker_assignments(uow, worker)
        uow.tool_workers.add(worker)
    uow.collect(worker)
    return worker


def mark_worker_stale_in_uow(uow, *, worker_id: str) -> ToolWorkerRegistration | None:
    worker = uow.tool_workers.get(worker_id)
    if worker is None:
        return None
    worker.mark_stale()
    uow.tool_workers.add(worker)
    uow.collect(worker)
    return worker


def prune_expired_workers_in_uow(
    uow,
    *,
    retention_seconds: int,
    now: datetime,
) -> WorkerPruneResult:
    cutoff = now - timedelta(seconds=max(int(retention_seconds), 0))
    pruned_worker_ids: list[str] = []
    for worker in uow.tool_workers.list():
        if worker.lease_expires_at is None:
            continue
        if worker.lease_expires_at > cutoff:
            continue
        if any(
            not assignment.is_terminal()
            for assignment in uow.tool_run_assignments.list_for_worker(worker.id)
        ):
            continue
        worker.record_event(
            Event(
                name="tool.worker.pruned",
                payload={
                    "worker_id": worker.id,
                    "status": worker.status.value,
                    "last_heartbeat": worker.heartbeat_at.isoformat(),
                    "lease_expires_at": worker.lease_expires_at.isoformat(),
                    "retention_seconds": max(int(retention_seconds), 0),
                },
            ),
        )
        uow.collect(worker)
        uow.tool_workers.delete(worker.id)
        pruned_worker_ids.append(worker.id)
    return WorkerPruneResult(
        pruned_worker_ids=tuple(pruned_worker_ids),
        cutoff=cutoff,
    )


def reconcile_worker_assignments(uow, worker: ToolWorkerRegistration) -> None:
    active_count = 0
    for assignment in uow.tool_run_assignments.list_for_worker(worker.id):
        if assignment.is_terminal():
            continue
        run = uow.tool_runs.get(assignment.run_id)
        if (
            run is None
            or run.is_terminal()
            or run.worker_id != worker.id
        ):
            assignment.expire(
                reason="Worker registration reconciled stale assignment.",
            )
            uow.tool_run_assignments.add(assignment)
            uow.collect(assignment)
            continue
        active_count += 1
    worker.sync_current_in_flight(active_count)


__all__ = [
    "WorkerPruneResult",
    "mark_worker_stale_in_uow",
    "prune_expired_workers_in_uow",
    "reconcile_worker_assignments",
    "register_or_refresh_worker",
]
