from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from crxzipple.modules.tool.application.catalog_service import ToolCatalogService
from crxzipple.modules.tool.application.provider_backend_service import (
    PROVIDER_BACKEND_METADATA_KEY,
)
from crxzipple.modules.tool.application.service_support import (
    PreparedToolRunCompletion,
    PreparedToolRunExecution,
    ToolUnitOfWork,
)
from crxzipple.modules.tool.application.worker_completion import (
    apply_run_completion,
    apply_run_failure,
)
from crxzipple.modules.tool.application.worker_execution_context import (
    execution_context_with_provider_backend,
    execution_context_with_tool_run_id,
)
from crxzipple.modules.tool.application.worker_run_resolution import (
    resolve_run_catalog_tool,
)
from crxzipple.modules.tool.domain.entities import ToolRun
from crxzipple.modules.tool.domain.exceptions import (
    ToolNotFoundError,
    ToolRunNotFoundError,
)
from crxzipple.modules.tool.domain.value_objects import (
    ToolExecutionContext,
    ToolMode,
    ToolRunError,
    ToolRunStatus,
)
from crxzipple.shared.runtime_metrics import RuntimeMetricsRegistry

CompleteBackgroundTracking = Callable[..., None]
ToolUnitOfWorkFactory = Callable[[], ToolUnitOfWork]


def prepare_run_execution(
    *,
    uow_factory: ToolUnitOfWorkFactory,
    catalog_service: ToolCatalogService,
    complete_background_tracking: CompleteBackgroundTracking,
    run_id: str,
    execution_context: ToolExecutionContext | None,
) -> PreparedToolRunExecution | ToolRun:
    with uow_factory() as uow:
        run = uow.tool_runs.get(run_id)
        if run is None:
            raise ToolRunNotFoundError(f"Tool run '{run_id}' was not found.")

        if run.is_terminal():
            return run

        if run.status is ToolRunStatus.CANCEL_REQUESTED:
            run.cancel()
            if run.target.mode is ToolMode.BACKGROUND:
                complete_background_tracking(
                    uow,
                    run,
                    terminal_kind="cancelled",
                )
            uow.tool_runs.add(run)
            uow.collect(run)
            uow.commit()
            return run

        tool = resolve_run_catalog_tool(uow, run)
        if tool is None:
            tool = catalog_service.resolve_tool(run.tool_id)
        if tool is None:
            raise ToolNotFoundError(f"Tool '{run.tool_id}' was not found.")

        if run.status in {
            ToolRunStatus.CREATED,
            ToolRunStatus.QUEUED,
            ToolRunStatus.DISPATCHING,
        }:
            run.start()
            if run.target.mode is ToolMode.BACKGROUND and run.worker_id is not None:
                assignment = uow.tool_run_assignments.get_latest_for_run_and_worker(
                    run.id,
                    run.worker_id,
                )
                if assignment is not None:
                    assignment.start()
                    uow.tool_run_assignments.add(assignment)
                    uow.collect(assignment)
            uow.tool_runs.add(run)
            uow.collect(run)
            uow.commit()

        resolved_execution_context = (
            execution_context if execution_context is not None else run.invocation_context
        )
        resolved_execution_context = execution_context_with_tool_run_id(
            resolved_execution_context,
            run.id,
        )
        provider_backend_payload = run.metadata.get(PROVIDER_BACKEND_METADATA_KEY)
        resolved_execution_context = execution_context_with_provider_backend(
            resolved_execution_context,
            (
                provider_backend_payload
                if isinstance(provider_backend_payload, Mapping)
                else None
            ),
        )
        return PreparedToolRunExecution(
            tool=tool,
            arguments=dict(run.input_payload),
            run_id=run.id,
            target=run.target,
            worker_id=run.worker_id,
            execution_context=resolved_execution_context,
        )


def complete_run_results(
    *,
    uow_factory: ToolUnitOfWorkFactory,
    metrics: RuntimeMetricsRegistry,
    dispatch_port: Any,
    complete_background_tracking: CompleteBackgroundTracking,
    completions: tuple[PreparedToolRunCompletion, ...],
) -> tuple[ToolRun, ...]:
    with uow_factory() as uow:
        with metrics.timed(
            "tool.service.persistence_seconds",
            labels={"operation": "complete_runs", "phase": "load"},
        ):
            runs_by_id = uow.tool_runs.get_many(
                tuple(completion.run_id for completion in completions),
            )
        completed_runs: list[ToolRun] = []
        for completion in completions:
            run = runs_by_id.get(completion.run_id)
            if run is None:
                raise ToolRunNotFoundError(
                    f"Tool run '{completion.run_id}' was not found after execution.",
                )
            apply_run_completion(
                uow,
                run,
                completion,
                dispatch_port=dispatch_port,
                complete_background_tracking=complete_background_tracking,
            )
            uow.tool_runs.add(run)
            uow.collect(run)
            completed_runs.append(run)
        with metrics.timed(
            "tool.service.persistence_seconds",
            labels={"operation": "complete_runs", "phase": "commit"},
        ):
            uow.commit()
        return tuple(completed_runs)


def fail_run(
    *,
    uow_factory: ToolUnitOfWorkFactory,
    dispatch_port: Any,
    complete_background_tracking: CompleteBackgroundTracking,
    run_id: str,
    message: str | ToolRunError,
) -> ToolRun:
    with uow_factory() as uow:
        failed_run = uow.tool_runs.get(run_id)
        if failed_run is None:
            raise ToolRunNotFoundError(
                f"Tool run '{run_id}' was not found after execution failure.",
            )
        apply_run_failure_to_uow(
            uow,
            failed_run,
            message,
            dispatch_port=dispatch_port,
            complete_background_tracking=complete_background_tracking,
        )
        uow.tool_runs.add(failed_run)
        uow.collect(failed_run)
        uow.commit()
        return failed_run


def apply_run_failure_to_uow(
    uow: ToolUnitOfWork,
    failed_run: ToolRun,
    message: str | ToolRunError,
    *,
    dispatch_port: Any,
    complete_background_tracking: CompleteBackgroundTracking,
) -> None:
    apply_run_failure(
        uow,
        failed_run,
        message,
        dispatch_port=dispatch_port,
        complete_background_tracking=complete_background_tracking,
    )


__all__ = [
    "apply_run_failure_to_uow",
    "complete_run_results",
    "fail_run",
    "prepare_run_execution",
]
