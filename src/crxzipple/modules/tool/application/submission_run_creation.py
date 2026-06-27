from __future__ import annotations

from uuid import uuid4

from crxzipple.modules.tool.application.provider_backend_service import (
    PROVIDER_BACKEND_METADATA_KEY,
    provider_backend_execution_context_payload,
)
from crxzipple.modules.tool.application.service_support import PreparedToolRunRequest
from crxzipple.modules.tool.application.submission_context import (
    execution_context_with_tool_run_id,
    tool_call_id,
    tool_surface_id,
)
from crxzipple.modules.tool.domain.entities import ToolRun
from crxzipple.modules.tool.domain.exceptions import ToolValidationError
from crxzipple.modules.tool.domain.value_objects import ToolMode


def create_tool_runs(
    prepared_requests: tuple[PreparedToolRunRequest, ...],
    *,
    uow_factory,
    dispatch_port,
    default_max_attempts: int,
    metrics,
) -> tuple[ToolRun, ...]:
    with uow_factory() as uow:
        runs: list[ToolRun] = []
        for prepared in prepared_requests:
            run = _create_tool_run(
                prepared,
                dispatch_tasks=uow.dispatch_tasks,
                dispatch_port=dispatch_port,
                default_max_attempts=default_max_attempts,
                uow=uow,
            )
            uow.collect(run)
            runs.append(run)
        uow.tool_runs.add_many_new(tuple(runs))
        with metrics.timed(
            "tool.service.persistence_seconds",
            labels={"operation": "create_runs", "phase": "commit"},
        ):
            uow.commit()
        return tuple(runs)


def _create_tool_run(
    prepared: PreparedToolRunRequest,
    *,
    dispatch_tasks,
    dispatch_port,
    default_max_attempts: int,
    uow,
) -> ToolRun:
    data = prepared.data
    target = prepared.target
    tool = prepared.tool
    function = prepared.function
    metadata = dict(data.metadata)
    if prepared.provider_backend_payload is not None:
        metadata[PROVIDER_BACKEND_METADATA_KEY] = dict(
            prepared.provider_backend_payload,
        )
    run_id = data.run_id or uuid4().hex
    execution_context = execution_context_with_tool_run_id(
        data.execution_context,
        run_id,
    )
    invocation_context_payload = provider_backend_execution_context_payload(
        execution_context.to_payload(),
        prepared.provider_backend_payload,
    )
    run = ToolRun.create(
        run_id=run_id,
        tool_id=tool.id,
        call_id=tool_call_id(data),
        tool_surface_id=tool_surface_id(data),
        function_id=function.function_id if function is not None else None,
        function_revision=function.revision if function is not None else None,
        source_id=function.source_id if function is not None else None,
        source_revision=prepared.source_revision,
        schema_hash=function.schema_hash if function is not None else None,
        input_payload=dict(data.arguments),
        metadata=metadata,
        invocation_context_payload=invocation_context_payload,
        target=target,
        max_attempts=default_max_attempts,
    )
    if target.mode is ToolMode.BACKGROUND:
        run.queue()
        dispatch_port.enqueue(dispatch_tasks, uow, run)
    elif target.mode is ToolMode.INLINE:
        run.start()
    else:
        raise ToolValidationError(
            f"Unsupported tool mode '{target.mode.value}' for run creation.",
        )
    return run
