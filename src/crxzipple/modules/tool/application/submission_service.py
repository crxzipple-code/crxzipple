from __future__ import annotations

import asyncio

from crxzipple.modules.tool.application.service_support import (
    ExecuteToolInput,
    PreparedToolRunExecution,
    PreparedToolRunRequest,
    ToolMode,
    ToolServiceBase,
    ToolServiceDependencies,
)
from crxzipple.modules.tool.application.provider_backend_service import (
    ToolProviderBackendResolver,
)
from crxzipple.modules.tool.application.submission_context import (
    execution_context_with_provider_backend,
    execution_context_with_tool_run_id,
)
from crxzipple.modules.tool.application.submission_preparation import (
    prepare_run_request,
)
from crxzipple.modules.tool.application.submission_run_creation import (
    create_tool_runs,
)
from crxzipple.modules.tool.application.worker_service import ToolWorkerService
from crxzipple.modules.tool.domain.entities import ToolRun
from crxzipple.modules.tool.domain.exceptions import (
    ToolRunNotFoundError,
    ToolValidationError,
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

    def list_tool_runs(
        self,
        *,
        tool_id: str | None = None,
        limit: int | None = None,
    ) -> list[ToolRun]:
        normalized_limit = _normalized_run_list_limit(limit)
        with self.uow_factory() as uow:
            if tool_id is None:
                return uow.tool_runs.list(limit=normalized_limit)
            return uow.tool_runs.list_for_tool(tool_id, limit=normalized_limit)

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
                            execution_context=execution_context_with_provider_backend(
                                execution_context_with_tool_run_id(
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
        return prepare_run_request(
            data=data,
            uow_factory=self.uow_factory,
            provider_backend_resolver=self.provider_backend_resolver,
            access_readiness=self.access_readiness,
            runtime_readiness=self.runtime_readiness,
        )

    def _create_runs(
        self,
        prepared_requests: tuple[PreparedToolRunRequest, ...],
    ) -> tuple[ToolRun, ...]:
        return create_tool_runs(
            prepared_requests,
            uow_factory=self.uow_factory,
            dispatch_port=self.dispatch_port,
            default_max_attempts=self.default_max_attempts,
            metrics=self.metrics,
        )


def _normalized_run_list_limit(limit: int | None) -> int | None:
    if limit is None:
        return None
    normalized = int(limit)
    if normalized <= 0:
        raise ToolValidationError("Tool run list limit must be greater than zero.")
    return normalized
