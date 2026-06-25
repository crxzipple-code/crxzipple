from __future__ import annotations

from collections.abc import Callable
from typing import Any

from crxzipple.modules.tool.domain.entities import ToolRun
from crxzipple.modules.tool.domain.value_objects import ToolMode


def complete_background_tracking(
    *,
    uow,
    run: ToolRun,
    terminal_kind: str,
    worker_lease_seconds: int,
    capabilities_payload_resolver: Callable[[dict[str, Any] | None], dict[str, Any]],
    reason: str | None = None,
) -> None:
    if run.target.mode is not ToolMode.BACKGROUND or run.worker_id is None:
        return
    assignment = uow.tool_run_assignments.get_latest_for_run_and_worker(
        run.id,
        run.worker_id,
    )
    if assignment is not None and not assignment.is_terminal():
        if terminal_kind == "succeeded":
            assignment.succeed()
        elif terminal_kind == "cancelled":
            assignment.cancel(reason=reason)
        elif terminal_kind == "expired":
            assignment.expire(reason=reason or "assignment expired")
        else:
            assignment.fail(reason or "tool run failed")
        uow.tool_run_assignments.add(assignment)
        uow.collect(assignment)
    worker = uow.tool_workers.get(run.worker_id)
    if worker is not None:
        worker.refresh(
            lease_seconds=worker_lease_seconds,
            capabilities_payload=capabilities_payload_resolver(
                worker.capabilities_payload,
            ),
        )
        worker.release_slot()
        uow.tool_workers.add(worker)
        uow.collect(worker)


__all__ = ["complete_background_tracking"]
