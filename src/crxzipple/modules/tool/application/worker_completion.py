from __future__ import annotations

from collections.abc import Callable

from crxzipple.modules.tool.application.service_support import (
    PreparedToolRunCompletion,
)
from crxzipple.modules.tool.application.worker_errors import (
    coerce_run_error,
)
from crxzipple.modules.tool.domain.entities import ToolRun
from crxzipple.modules.tool.domain.exceptions import ToolValidationError
from crxzipple.modules.tool.domain.value_objects import (
    ToolMode,
    ToolRunError,
    ToolRunStatus,
)

CompleteBackgroundTracking = Callable[..., None]


def apply_run_completion(
    uow,
    run: ToolRun,
    completion: PreparedToolRunCompletion,
    *,
    dispatch_port,
    complete_background_tracking: CompleteBackgroundTracking,
) -> None:
    if completion.error_message is not None:
        apply_run_failure(
            uow,
            run,
            completion.error_message,
            dispatch_port=dispatch_port,
            complete_background_tracking=complete_background_tracking,
        )
        return

    output = completion.output
    if output is None:
        raise ToolValidationError(
            f"Tool run '{completion.run_id}' completed without output or error.",
        )
    if run.status is ToolRunStatus.CANCEL_REQUESTED:
        run.cancel()
        if run.target.mode is ToolMode.BACKGROUND:
            dispatch_port.cancel(uow.dispatch_tasks, uow, run)
            complete_background_tracking(
                uow,
                run,
                terminal_kind="cancelled",
            )
        return

    run.succeed(output)
    if run.target.mode is ToolMode.BACKGROUND:
        dispatch_port.complete(uow.dispatch_tasks, uow, run)
        complete_background_tracking(
            uow,
            run,
            terminal_kind="succeeded",
        )


def apply_run_failure(
    uow,
    failed_run: ToolRun,
    message: str | ToolRunError,
    *,
    dispatch_port,
    complete_background_tracking: CompleteBackgroundTracking,
) -> None:
    run_error = coerce_run_error(message)
    failure_message = run_error.message
    if failed_run.status is ToolRunStatus.CANCEL_REQUESTED:
        failed_run.cancel()
        dispatch_port.cancel(uow.dispatch_tasks, uow, failed_run)
        complete_background_tracking(
            uow,
            failed_run,
            terminal_kind="cancelled",
            reason=failure_message,
        )
    elif failed_run.target.mode is ToolMode.BACKGROUND and failed_run.can_retry():
        complete_background_tracking(
            uow,
            failed_run,
            terminal_kind="failed",
            reason=failure_message,
        )
        failed_run.requeue(run_error)
        dispatch_port.requeue(
            uow.dispatch_tasks,
            uow,
            failed_run,
            reason=failure_message,
        )
    else:
        failed_run.fail(run_error)
        if failed_run.target.mode is ToolMode.BACKGROUND:
            dispatch_port.fail(uow.dispatch_tasks, uow, failed_run)
            complete_background_tracking(
                uow,
                failed_run,
                terminal_kind="failed",
                reason=failure_message,
            )


__all__ = [
    "apply_run_completion",
    "apply_run_failure",
]
