from __future__ import annotations

from collections.abc import Callable

from crxzipple.modules.tool.application.worker_errors import retry_exhausted_reason
from crxzipple.modules.tool.domain.entities import ToolRun
from crxzipple.modules.tool.domain.value_objects import ToolRunStatus

CompleteBackgroundTracking = Callable[..., None]


def apply_recovered_dispatch_task(
    uow,
    run: ToolRun,
    *,
    reason: str,
    dispatch_port,
    complete_background_tracking: CompleteBackgroundTracking,
) -> ToolRun:
    if run.is_terminal() or run.status is ToolRunStatus.QUEUED:
        return run
    if run.status is ToolRunStatus.CANCEL_REQUESTED:
        run.cancel()
        dispatch_port.cancel(uow.dispatch_tasks, uow, run)
        complete_background_tracking(
            uow,
            run,
            terminal_kind="cancelled",
            reason=reason,
        )
    elif run.can_retry():
        complete_background_tracking(
            uow,
            run,
            terminal_kind="expired",
            reason=reason,
        )
        run.requeue(reason)
    else:
        run.fail(retry_exhausted_reason(reason))
        dispatch_port.fail(uow.dispatch_tasks, uow, run)
        complete_background_tracking(
            uow,
            run,
            terminal_kind="expired",
            reason=reason,
        )
    return run


__all__ = ["apply_recovered_dispatch_task"]
