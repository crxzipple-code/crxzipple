from __future__ import annotations

from collections.abc import Callable
from typing import Any

from crxzipple.core.logger import get_logger
from crxzipple.modules.tool.application.service_support import ToolUnitOfWork
from crxzipple.modules.tool.domain.entities import ToolRun
from crxzipple.modules.tool.domain.exceptions import ToolRunNotFoundError

logger = get_logger(__name__)

ToolUnitOfWorkFactory = Callable[[], ToolUnitOfWork]


def heartbeat_run_in_uow(
    *,
    uow_factory: ToolUnitOfWorkFactory,
    dispatch_port: Any,
    run_id: str,
    worker_id: str,
    lease_seconds: int,
    capabilities_payload_resolver: Callable[[dict[str, Any] | None], dict[str, Any]],
) -> ToolRun:
    with uow_factory() as uow:
        run = uow.tool_runs.get(run_id)
        if run is None:
            raise ToolRunNotFoundError(f"Tool run '{run_id}' was not found.")
        if run.is_terminal():
            return run
        if run.worker_id != worker_id:
            logger.warning(
                "skipping heartbeat for tool run owned by another worker",
                extra={
                    "run_id": run.id,
                    "expected_worker_id": worker_id,
                    "actual_worker_id": run.worker_id,
                },
            )
            return run
        run.heartbeat(lease_seconds=lease_seconds)
        assignment = uow.tool_run_assignments.get_latest_for_run_and_worker(
            run.id,
            worker_id,
        )
        if assignment is not None:
            assignment.heartbeat(lease_seconds=lease_seconds)
            uow.tool_run_assignments.add(assignment)
            uow.collect(assignment)
        worker = uow.tool_workers.get(worker_id)
        if worker is not None:
            worker.refresh(
                lease_seconds=lease_seconds,
                capabilities_payload=capabilities_payload_resolver(
                    worker.capabilities_payload,
                ),
            )
            uow.tool_workers.add(worker)
            uow.collect(worker)
        dispatch_port.heartbeat(
            uow.dispatch_tasks,
            uow,
            run,
            worker_id=worker_id,
            lease_seconds=lease_seconds,
        )
        uow.tool_runs.add(run)
        uow.collect(run)
        uow.commit()
        return run


__all__ = ["heartbeat_run_in_uow"]
