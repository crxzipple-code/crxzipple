from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from crxzipple.modules.tool.application.worker_registration import (
    mark_worker_stale_in_uow,
    prune_expired_workers_in_uow,
    register_or_refresh_worker,
)
from crxzipple.modules.tool.domain.entities import (
    ToolRunAssignment,
    ToolWorkerRegistration,
)


def register_worker(
    *,
    uow_factory: Callable[[], Any],
    worker_id: str,
    lease_seconds: int,
    max_in_flight: int,
    capabilities_payload: dict[str, Any] | None,
    capabilities_payload_resolver: Callable[[dict[str, Any] | None], dict[str, Any]],
) -> ToolWorkerRegistration:
    resolved_capabilities_payload = capabilities_payload_resolver(capabilities_payload)
    with uow_factory() as uow:
        worker = register_or_refresh_worker(
            uow,
            worker_id=worker_id,
            lease_seconds=lease_seconds,
            max_in_flight=max_in_flight,
            capabilities_payload=resolved_capabilities_payload,
        )
        uow.commit()
        return worker


def mark_worker_stale(
    *,
    uow_factory: Callable[[], Any],
    worker_id: str,
) -> ToolWorkerRegistration | None:
    with uow_factory() as uow:
        worker = mark_worker_stale_in_uow(uow, worker_id=worker_id)
        if worker is None:
            return None
        uow.commit()
        return worker


def list_workers(*, uow_factory: Callable[[], Any]) -> list[ToolWorkerRegistration]:
    with uow_factory() as uow:
        return uow.tool_workers.list()


def prune_expired_workers(
    *,
    uow_factory: Callable[[], Any],
    retention_seconds: int,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    with uow_factory() as uow:
        result = prune_expired_workers_in_uow(
            uow,
            retention_seconds=retention_seconds,
            now=now,
        )
        uow.commit()
    return {
        "pruned_count": result.pruned_count,
        "worker_ids": result.pruned_worker_ids,
        "cutoff": result.cutoff,
    }


def list_assignments(*, uow_factory: Callable[[], Any]) -> list[ToolRunAssignment]:
    with uow_factory() as uow:
        return uow.tool_run_assignments.list()
