from __future__ import annotations

import asyncio
from uuid import uuid4

from crxzipple.modules.tool.application.service_support import (
    ExecuteToolInput,
    PreparedToolRunExecution,
    PreparedToolRunRequest,
    ToolExecutionTarget,
    ToolMode,
    ToolServiceBase,
    ToolServiceDependencies,
    build_tool_from_function,
)
from crxzipple.modules.tool.application.provider_backend_service import (
    PROVIDER_BACKEND_METADATA_KEY,
    ToolProviderBackendResolver,
    provider_backend_execution_context_payload,
)
from crxzipple.modules.tool.application.worker_service import ToolWorkerService
from crxzipple.modules.tool.domain.entities import ToolRun
from crxzipple.modules.tool.domain.exceptions import (
    ToolExecutionNotAllowedError,
    ToolExecutionNotSupportedError,
    ToolNotFoundError,
    ToolRunNotFoundError,
    ToolValidationError,
)
from crxzipple.modules.tool.domain.value_objects import (
    ToolExecutionContext,
    ToolFunctionStatus,
    ToolSourceStatus,
)


class ToolSubmissionService(ToolServiceBase):
    def __init__(
        self,
        deps: ToolServiceDependencies,
        *,
        worker_service: ToolWorkerService,
    ) -> None:
        super().__init__(deps)
        self.worker_service = worker_service
        self.provider_backend_resolver = ToolProviderBackendResolver()

    def get_tool_run(self, run_id: str) -> ToolRun:
        with self.uow_factory() as uow:
            run = uow.tool_runs.get(run_id)
            if run is None:
                raise ToolRunNotFoundError(f"Tool run '{run_id}' was not found.")
            return run

    def list_tool_runs(self, *, tool_id: str | None = None) -> list[ToolRun]:
        with self.uow_factory() as uow:
            if tool_id is None:
                return uow.tool_runs.list()
            return uow.tool_runs.list_for_tool(tool_id)

    def list_tool_runs_for_orchestration_runs(
        self,
        run_ids: tuple[str, ...],
    ) -> list[ToolRun]:
        with self.uow_factory() as uow:
            return uow.tool_runs.list_for_orchestration_runs(run_ids)

    async def execute(self, data: ExecuteToolInput) -> ToolRun:
        return (await self.execute_many((data,)))[0]

    async def execute_many(
        self,
        items: tuple[ExecuteToolInput, ...],
    ) -> tuple[ToolRun, ...]:
        if not items:
            return ()
        with self.metrics.timed(
            "tool.service.phase_seconds",
            labels={"phase": "prepare_requests"},
        ):
            prepared_requests = await asyncio.to_thread(
                self._prepare_run_requests,
                items,
            )
        with self.metrics.timed(
            "tool.service.phase_seconds",
            labels={"phase": "create_runs"},
        ):
            created_runs = await asyncio.to_thread(
                self._create_runs,
                prepared_requests,
            )

        results: list[ToolRun | None] = [None for _ in created_runs]
        inline_executions: list[tuple[int, PreparedToolRunExecution]] = []
        unsupported_executions: list[tuple[int, ToolRun]] = []
        for index, (prepared, run) in enumerate(zip(prepared_requests, created_runs)):
            if prepared.target.mode is ToolMode.INLINE:
                inline_executions.append(
                    (
                        index,
                        PreparedToolRunExecution(
                            tool=prepared.tool,
                            arguments=dict(prepared.data.arguments),
                            run_id=run.id,
                            target=prepared.target,
                            worker_id=run.worker_id,
                            execution_context=_execution_context_with_provider_backend(
                                _execution_context_with_tool_run_id(
                                    prepared.data.execution_context,
                                    run.id,
                                ),
                                prepared.provider_backend_payload,
                            ),
                        ),
                    ),
                )
                continue
            if prepared.target.mode is ToolMode.BACKGROUND:
                results[index] = run
                continue
            unsupported_executions.append((index, run))

        if inline_executions:
            with self.metrics.timed(
                "tool.service.phase_seconds",
                labels={"phase": "inline_runtime"},
            ):
                completed_runs = await self.worker_service.execute_prepared_runs(
                    tuple(prepared for _, prepared in inline_executions),
                )
            for (index, _), completed_run in zip(
                inline_executions,
                completed_runs,
            ):
                results[index] = completed_run

        if unsupported_executions:
            with self.metrics.timed(
                "tool.service.phase_seconds",
                labels={"phase": "unsupported_fail"},
            ):
                failed_runs = await self.worker_service.fail_runs(
                    tuple(run.id for _, run in unsupported_executions),
                    message=(
                        "Only local async execution is implemented for inline/background "
                        "modes in the current skeleton."
                    ),
                )
            for (index, _), failed_run in zip(
                unsupported_executions,
                failed_runs,
            ):
                results[index] = failed_run

        completed_results: list[ToolRun] = []
        for run in results:
            if run is None:
                raise RuntimeError("Tool batch execution did not produce all results.")
            completed_results.append(run)
        return tuple(completed_results)

    def _prepare_run_requests(
        self,
        items: tuple[ExecuteToolInput, ...],
    ) -> tuple[PreparedToolRunRequest, ...]:
        return tuple(self._prepare_run_request(data) for data in items)

    def _prepare_run_request(
        self,
        data: ExecuteToolInput,
    ) -> PreparedToolRunRequest:
        target = ToolExecutionTarget(
            mode=data.mode,
            strategy=data.strategy,
            environment=data.environment,
        )
        source_revision = None
        with self.uow_factory() as uow:
            function = uow.tool_functions.get(data.tool_id)
            if function is None:
                raise ToolNotFoundError(f"Tool '{data.tool_id}' was not found.")
            self._ensure_function_executable(uow, function, tool_id=data.tool_id)
            source = uow.tool_sources.get(function.source_id)
            source_revision = source.revision if source is not None else None
            provider_backend = self.provider_backend_resolver.resolve_for_function(
                function=function,
                repository=uow.tool_provider_backends,
            )
            provider_backend_payload = (
                provider_backend.to_payload()
                if provider_backend is not None
                else None
            )
            tool = build_tool_from_function(function)
        if not tool.enabled:
            raise ToolExecutionNotAllowedError(
                f"Tool '{tool.id}' is disabled and cannot be executed.",
                code="tool_disabled",
                detail={
                    "tool_id": getattr(tool, "id", data.tool_id),
                    "category": "catalog",
                    "enabled": False,
                },
            )
        if not tool.supports(target):
            raise ToolExecutionNotSupportedError(
                f"Tool '{tool.id}' does not support {target.mode.value}/{target.strategy.value}/{target.environment.value}.",
            )
        self._ensure_tool_access_ready(tool, data=data)
        self._ensure_tool_runtime_ready(tool, data=data)
        return PreparedToolRunRequest(
            data=data,
            target=target,
            tool=tool,
            function=function,
            source_revision=source_revision,
            provider_backend_payload=provider_backend_payload,
        )

    def _ensure_function_executable(
        self,
        uow,
        function,
        *,
        tool_id: str,
    ) -> None:
        source = uow.tool_sources.get(function.source_id)
        if source is None:
            raise ToolExecutionNotAllowedError(
                f"Tool '{tool_id}' source '{function.source_id}' is not available.",
                code="tool_source_not_available",
                detail={
                    "tool_id": tool_id,
                    "function_id": function.function_id,
                    "source_id": function.source_id,
                    "category": "catalog",
                },
            )
        if source.status is not ToolSourceStatus.ACTIVE:
            raise ToolExecutionNotAllowedError(
                f"Tool '{tool_id}' source '{source.source_id}' is {source.status.value}.",
                code="tool_source_not_executable",
                detail={
                    "tool_id": tool_id,
                    "function_id": function.function_id,
                    "source_id": source.source_id,
                    "category": "catalog",
                    "source_status": source.status.value,
                },
            )
        if function.status is not ToolFunctionStatus.ACTIVE:
            raise ToolExecutionNotAllowedError(
                f"Tool '{tool_id}' catalog function is {function.status.value}.",
                code="tool_function_not_executable",
                detail={
                    "tool_id": tool_id,
                    "function_id": function.function_id,
                    "source_id": function.source_id,
                    "category": "catalog",
                    "function_status": function.status.value,
                    "enabled": function.enabled,
                },
            )
        if not function.enabled:
            raise ToolExecutionNotAllowedError(
                f"Tool '{tool_id}' catalog function is disabled.",
                code="tool_function_disabled",
                detail={
                    "tool_id": tool_id,
                    "function_id": function.function_id,
                    "source_id": function.source_id,
                    "category": "catalog",
                    "function_status": function.status.value,
                    "enabled": False,
                },
            )

    def _ensure_tool_access_ready(self, tool: object, *, data: ExecuteToolInput) -> None:
        access_readiness = self.access_readiness
        if access_readiness is None:
            return
        readiness = access_readiness.check_tool_access(tool)
        if readiness.ready:
            return
        blocking_checks = tuple(check for check in readiness.checks if not check.ready)
        requirement_summary = ", ".join(
            dict.fromkeys(
                check.binding_id or check.requirement
                for check in blocking_checks
                if (check.binding_id or check.requirement)
            ),
        )
        message = (
            f"Tool '{getattr(tool, 'id', data.tool_id)}' requires access setup"
            f" ({readiness.status}): {readiness.reason}"
            + (f" Required: {requirement_summary}." if requirement_summary else ".")
        )
        raise ToolExecutionNotAllowedError(
            message,
            code="access_not_ready",
            detail={
                "tool_id": getattr(tool, "id", data.tool_id),
                "category": "access",
                "readiness": _readiness_payload(readiness),
            },
        )

    def _ensure_tool_runtime_ready(self, tool: object, *, data: ExecuteToolInput) -> None:
        runtime_readiness = self.runtime_readiness
        if runtime_readiness is None:
            return
        execution_context = data.execution_context
        workspace_dir = (
            execution_context.get_str("workspace_dir")
            if execution_context is not None
            else None
        )
        readiness = runtime_readiness.check_tool_runtime(
            tool,
            workspace_dir=workspace_dir,
        )
        if readiness.ready:
            return
        blocking_checks = tuple(check for check in readiness.checks if not check.ready)
        requirement_summary = ", ".join(
            dict.fromkeys(
                check.requirement
                for check in blocking_checks
                if check.requirement
            ),
        )
        message = (
            f"Tool '{getattr(tool, 'id', data.tool_id)}' requires runtime setup"
            f" ({readiness.status}): {readiness.reason}"
            + (f" Required: {requirement_summary}." if requirement_summary else ".")
        )
        raise ToolExecutionNotAllowedError(
            message,
            code="tool_runtime_not_ready",
            detail={
                "tool_id": getattr(tool, "id", data.tool_id),
                "category": "runtime",
                "readiness": _readiness_payload(readiness),
            },
        )

    def _create_runs(
        self,
        prepared_requests: tuple[PreparedToolRunRequest, ...],
    ) -> tuple[ToolRun, ...]:
        with self.uow_factory() as uow:
            runs: list[ToolRun] = []
            for prepared in prepared_requests:
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
                execution_context = _execution_context_with_tool_run_id(
                    data.execution_context,
                    run_id,
                )
                invocation_context_payload = provider_backend_execution_context_payload(
                    (
                        execution_context.to_payload()
                        if execution_context is not None
                        else None
                    ),
                    prepared.provider_backend_payload,
                )
                run = ToolRun.create(
                    run_id=run_id,
                    tool_id=tool.id,
                    call_id=_tool_call_id(data),
                    tool_surface_id=_tool_surface_id(data),
                    function_id=function.function_id if function is not None else None,
                    function_revision=function.revision if function is not None else None,
                    source_id=function.source_id if function is not None else None,
                    source_revision=prepared.source_revision,
                    schema_hash=function.schema_hash if function is not None else None,
                    input_payload=dict(data.arguments),
                    metadata=metadata,
                    invocation_context_payload=invocation_context_payload,
                    target=target,
                    max_attempts=self.default_max_attempts,
                )
                if target.mode is ToolMode.BACKGROUND:
                    run.queue()
                    self.dispatch_port.enqueue(uow.dispatch_tasks, uow, run)
                elif target.mode is ToolMode.INLINE:
                    run.start()
                else:
                    raise ToolValidationError(
                        f"Unsupported tool mode '{target.mode.value}' for run creation.",
                    )
                uow.collect(run)
                runs.append(run)
            uow.tool_runs.add_many_new(tuple(runs))
            with self.metrics.timed(
                "tool.service.persistence_seconds",
                labels={"operation": "create_runs", "phase": "commit"},
            ):
                uow.commit()
            return tuple(runs)


def _readiness_payload(readiness: object) -> dict[str, object]:
    to_payload = getattr(readiness, "to_payload", None)
    if callable(to_payload):
        payload = to_payload()
        if isinstance(payload, dict):
            return dict(payload)
    return {
        "ready": bool(getattr(readiness, "ready", False)),
        "status": str(getattr(readiness, "status", "unknown")),
        "reason": str(getattr(readiness, "reason", "")),
        "setup_available": False,
        "checks": [],
    }


def _tool_call_id(data: ExecuteToolInput) -> str | None:
    explicit = _optional_text(data.call_id)
    if explicit is not None:
        return explicit
    return _metadata_text(data.metadata, "tool_call_id")


def _tool_surface_id(data: ExecuteToolInput) -> str | None:
    explicit = _optional_text(data.tool_surface_id)
    if explicit is not None:
        return explicit
    direct = _metadata_text(data.metadata, "tool_surface_id")
    if direct is not None:
        return direct
    plan = data.metadata.get("tool_execution_plan")
    if isinstance(plan, dict):
        return _metadata_text(plan, "tool_surface_id")
    return None


def _metadata_text(metadata: dict[str, object], key: str) -> str | None:
    return _optional_text(metadata.get(key))


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _execution_context_with_provider_backend(
    execution_context: ToolExecutionContext | None,
    provider_backend_payload: dict[str, object] | None,
) -> ToolExecutionContext | None:
    payload = provider_backend_execution_context_payload(
        (
            execution_context.to_payload()
            if execution_context is not None
            else None
        ),
        provider_backend_payload,
    )
    if payload is None:
        return execution_context
    return ToolExecutionContext(attrs=payload)


def _execution_context_with_tool_run_id(
    execution_context: ToolExecutionContext | None,
    run_id: str,
) -> ToolExecutionContext:
    payload = execution_context.to_payload() if execution_context is not None else {}
    payload["tool_run_id"] = run_id
    return ToolExecutionContext(attrs=payload)
