from __future__ import annotations

import asyncio
from uuid import uuid4

from crxzipple.modules.tool.application.catalog_service import ToolCatalogService
from crxzipple.modules.tool.application.service_support import (
    ExecuteToolInput,
    PreparedToolRunExecution,
    PreparedToolRunRequest,
    ToolExecutionTarget,
    ToolMode,
    ToolServiceBase,
    ToolServiceDependencies,
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


class ToolSubmissionService(ToolServiceBase):
    def __init__(
        self,
        deps: ToolServiceDependencies,
        *,
        catalog_service: ToolCatalogService,
        worker_service: ToolWorkerService,
    ) -> None:
        super().__init__(deps)
        self.catalog_service = catalog_service
        self.worker_service = worker_service

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
                            execution_context=prepared.data.execution_context,
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
        resolved_tools = self.catalog_service.resolved_tool_map()
        return tuple(
            self._prepare_run_request(data, resolved_tools=resolved_tools)
            for data in items
        )

    def _prepare_run_request(
        self,
        data: ExecuteToolInput,
        *,
        resolved_tools: dict[str, object] | None = None,
    ) -> PreparedToolRunRequest:
        target = ToolExecutionTarget(
            mode=data.mode,
            strategy=data.strategy,
            environment=data.environment,
        )
        if resolved_tools is None:
            tool = self.catalog_service.get_tool(data.tool_id)
        else:
            tool = resolved_tools.get(data.tool_id)
            if tool is None:
                raise ToolNotFoundError(f"Tool '{data.tool_id}' was not found.")
        if not tool.enabled:
            raise ToolExecutionNotAllowedError(
                f"Tool '{tool.id}' is disabled and cannot be executed.",
            )
        if not tool.supports(target):
            raise ToolExecutionNotSupportedError(
                f"Tool '{tool.id}' does not support {target.mode.value}/{target.strategy.value}/{target.environment.value}.",
            )
        return PreparedToolRunRequest(
            data=data,
            target=target,
            tool=tool,
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
                run = ToolRun.create(
                    run_id=data.run_id or uuid4().hex,
                    tool_id=tool.id,
                    input_payload=dict(data.arguments),
                    invocation_context_payload=(
                        data.execution_context.to_payload()
                        if data.execution_context is not None
                        else None
                    ),
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
