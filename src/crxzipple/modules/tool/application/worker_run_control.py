from __future__ import annotations

from collections.abc import Callable
from typing import Any

from crxzipple.modules.tool.application.worker_recovery import (
    apply_recovered_dispatch_task,
)
from crxzipple.modules.tool.domain.entities import ToolRun
from crxzipple.modules.tool.domain.exceptions import ToolRunNotFoundError
from crxzipple.modules.tool.domain.value_objects import (
    ToolMode,
    ToolRunStatus,
)


def cancel_tool_run(
    *,
    uow_factory: Callable[[], Any],
    dispatch_port: Any,
    complete_background_tracking: Callable[..., None],
    run_id: str,
) -> ToolRun:
    with uow_factory() as uow:
        run = uow.tool_runs.get(run_id)
        if run is None:
            raise ToolRunNotFoundError(f"Tool run '{run_id}' was not found.")
        if run.is_terminal():
            return run

        if run.status in {
            ToolRunStatus.CREATED,
            ToolRunStatus.QUEUED,
            ToolRunStatus.DISPATCHING,
        }:
            run.request_cancel()
            run.cancel()
            if run.target.mode is ToolMode.BACKGROUND:
                dispatch_port.cancel(uow.dispatch_tasks, uow, run)
                complete_background_tracking(
                    uow,
                    run,
                    terminal_kind="cancelled",
                )
        elif run.status is ToolRunStatus.RUNNING:
            run.request_cancel()

        uow.tool_runs.add(run)
        uow.collect(run)
        uow.commit()
        return run


def handle_recovered_dispatch_task(
    *,
    uow_factory: Callable[[], Any],
    dispatch_port: Any,
    complete_background_tracking: Callable[..., None],
    tool_run_id: str,
    reason: str,
) -> ToolRun | None:
    with uow_factory() as uow:
        run = uow.tool_runs.get(tool_run_id)
        if run is None:
            return None
        apply_recovered_dispatch_task(
            uow,
            run,
            reason=reason,
            dispatch_port=dispatch_port,
            complete_background_tracking=complete_background_tracking,
        )
        uow.tool_runs.add(run)
        uow.collect(run)
        uow.commit()
        return run
