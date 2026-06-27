from __future__ import annotations

import asyncio
from threading import Event as ThreadEvent
from typing import Any

from crxzipple.core.logger import get_logger
from crxzipple.modules.tool.application.catalog_service import ToolCatalogService
from crxzipple.modules.tool.application.concurrency import ToolRunConcurrencyPolicy
from crxzipple.modules.tool.application.dispatch_events import ToolRuntimeEventService
from crxzipple.modules.tool.application.worker_capabilities import (
    build_worker_capabilities_payload,
)
from crxzipple.modules.tool.application.worker_admin import (
    list_assignments as list_worker_assignments,
    list_workers as list_registered_workers,
    mark_worker_stale as mark_registered_worker_stale,
    prune_expired_workers as prune_expired_worker_registrations,
    register_worker as register_worker_record,
)
from crxzipple.modules.tool.application.ports import ToolEventWaitPort
from crxzipple.modules.tool.application.service_support import (
    PreparedToolRunCompletion,
    PreparedToolRunExecution,
    ToolServiceBase,
    ToolServiceDependencies,
)
from crxzipple.modules.tool.application.worker_errors import (
    exception_run_error as _exception_run_error,
)
from crxzipple.modules.tool.application.worker_inflight import (
    heartbeat_inflight_loop,
    launch_assignments,
    perform_assigned_run,
    reap_inflight_tasks,
    select_runnable_run_ids,
)
from crxzipple.modules.tool.application.worker_run_control import (
    cancel_tool_run as cancel_run_in_uow,
    handle_recovered_dispatch_task as handle_recovered_dispatch_task_in_uow,
)
from crxzipple.modules.tool.application.worker_run_resolution import (
    resolve_run_catalog_tool,
    resolve_run_tool_for_concurrency,
)
from crxzipple.modules.tool.application.worker_runtime_execution import (
    execute_tool_runtime_for_worker,
)
from crxzipple.modules.tool.application.worker_run_persistence import (
    apply_run_failure_to_uow,
    complete_run_results,
    fail_run,
    prepare_run_execution,
)
from crxzipple.modules.tool.application.worker_run_heartbeat import (
    heartbeat_run_in_uow,
)
from crxzipple.modules.tool.application.worker_processing_heartbeat import (
    heartbeat_while_processing,
)
from crxzipple.modules.tool.application.worker_tracking import (
    complete_background_tracking as _complete_background_tracking,
)
from crxzipple.modules.tool.application.worker_run_loop import (
    run_worker_until_stopped_async,
)
from crxzipple.modules.tool.application.worker_wakeup import (
    wait_for_worker_wakeup,
)
from crxzipple.modules.tool.domain.entities import (
    Tool,
    ToolRun,
    ToolRunAssignment,
    ToolWorkerRegistration,
)
from crxzipple.modules.tool.domain.value_objects import (
    ToolExecutionContext,
    ToolExecutionTarget,
    ToolRunError,
    ToolRunResult,
)

logger = get_logger(__name__)

class ToolWorkerService(ToolServiceBase):
    def __init__(
        self,
        deps: ToolServiceDependencies,
        *,
        catalog_service: ToolCatalogService,
        concurrency_policy: ToolRunConcurrencyPolicy,
    ) -> None:
        super().__init__(deps)
        self.catalog_service = catalog_service
        self.concurrency_policy = concurrency_policy

    def register_worker(
        self,
        *,
        worker_id: str,
        max_in_flight: int = 1,
        capabilities_payload: dict[str, Any] | None = None,
    ):
        return register_worker_record(
            uow_factory=self.uow_factory,
            worker_id=worker_id,
            lease_seconds=self.worker_lease_seconds,
            max_in_flight=max_in_flight,
            capabilities_payload=capabilities_payload,
            capabilities_payload_resolver=self._worker_capabilities_payload,
        )

    def mark_worker_stale(self, *, worker_id: str):
        return mark_registered_worker_stale(
            uow_factory=self.uow_factory,
            worker_id=worker_id,
        )

    def list_workers(self) -> list[ToolWorkerRegistration]:
        return list_registered_workers(uow_factory=self.uow_factory)

    def prune_expired_workers(self, *, retention_seconds: int) -> dict[str, Any]:
        return prune_expired_worker_registrations(
            uow_factory=self.uow_factory,
            retention_seconds=retention_seconds,
        )

    def list_assignments(self) -> list[ToolRunAssignment]:
        return list_worker_assignments(uow_factory=self.uow_factory)

    def process_next_assigned_run(self, *, worker_id: str) -> ToolRun | None:
        with self.uow_factory() as uow:
            assignment = uow.tool_run_assignments.get_next_for_worker(worker_id)
            if assignment is None:
                return None
        return self._execute_background_run_sync(assignment.run_id)

    def run_until_stopped(
        self,
        *,
        worker_id: str,
        poll_interval_seconds: float,
        max_runs: int | None = None,
        max_idle_cycles: int | None = None,
        stop_event: ThreadEvent | None = None,
        events_service: ToolEventWaitPort | None = None,
        runtime_event_service: ToolRuntimeEventService | None = None,
        max_in_flight: int = 1,
    ) -> int:
        stopper = stop_event or ThreadEvent()
        return asyncio.run(
            run_worker_until_stopped_async(
                worker_id=worker_id,
                poll_interval_seconds=poll_interval_seconds,
                max_runs=max_runs,
                max_idle_cycles=max_idle_cycles,
                stop_event=stopper,
                events_service=events_service,
                runtime_event_service=runtime_event_service,
                max_in_flight=max_in_flight,
                register_worker=self.register_worker,
                mark_worker_stale=self.mark_worker_stale,
                launch_assignments=self._launch_assignments,
                reap_inflight_tasks=self._reap_inflight_tasks,
                heartbeat_inflight_loop=self._heartbeat_inflight_loop,
                wait_for_worker_wakeup=self._wait_for_worker_wakeup,
                logger=logger,
            ),
        )

    async def _launch_assignments(
        self,
        *,
        worker_id: str,
        inflight_tasks: dict[str, asyncio.Task[ToolRun]],
        max_new_assignments: int,
    ) -> int:
        return await launch_assignments(
            worker_id=worker_id,
            inflight_tasks=inflight_tasks,
            max_new_assignments=max_new_assignments,
            select_runnable_run_ids=self._select_runnable_run_ids,
            perform_assigned_run=self._perform_assigned_run,
        )

    async def _reap_inflight_tasks(
        self,
        inflight_tasks: dict[str, asyncio.Task[ToolRun]],
    ) -> int:
        return await reap_inflight_tasks(inflight_tasks, logger=logger)

    async def _perform_assigned_run(self, run_id: str) -> ToolRun:
        return await perform_assigned_run(
            run_id=run_id,
            perform_run=lambda current_run_id: self._perform_run(
                current_run_id,
                manage_heartbeat=False,
            ),
            fail_run=self._fail_run,
            logger=logger,
        )

    async def _heartbeat_inflight_loop(
        self,
        *,
        worker_id: str,
        stop_event: ThreadEvent,
        inflight_tasks: dict[str, asyncio.Task[ToolRun]],
    ) -> None:
        await heartbeat_inflight_loop(
            worker_id=worker_id,
            stop_event=stop_event,
            inflight_tasks=inflight_tasks,
            worker_heartbeat_seconds=self.worker_heartbeat_seconds,
            heartbeat_run=lambda current_run_id, current_worker_id: self.heartbeat_run(
                current_run_id,
                worker_id=current_worker_id,
            ),
            logger=logger,
        )

    def _select_runnable_run_ids(
        self,
        worker_id: str,
        exclude_run_ids: tuple[str, ...],
        limit: int,
    ) -> tuple[str, ...]:
        return select_runnable_run_ids(
            uow_factory=self.uow_factory,
            concurrency_policy=self.concurrency_policy,
            resolve_tool_for_run=self._resolve_run_tool_for_concurrency,
            worker_id=worker_id,
            exclude_run_ids=exclude_run_ids,
            limit=limit,
        )

    def _wait_for_worker_wakeup(
        self,
        *,
        stop_event: ThreadEvent,
        timeout_seconds: float,
        events_service: ToolEventWaitPort | None,
        runtime_event_service: ToolRuntimeEventService | None,
    ) -> None:
        wait_for_worker_wakeup(
            stop_event=stop_event,
            timeout_seconds=timeout_seconds,
            events_service=events_service,
            runtime_event_service=runtime_event_service,
        )

    def heartbeat_run(self, run_id: str, *, worker_id: str) -> ToolRun:
        return heartbeat_run_in_uow(
            uow_factory=self.uow_factory,
            dispatch_port=self.dispatch_port,
            run_id=run_id,
            worker_id=worker_id,
            lease_seconds=self.worker_lease_seconds,
            capabilities_payload_resolver=self._worker_capabilities_payload,
        )

    def cancel_tool_run(self, run_id: str) -> ToolRun:
        return cancel_run_in_uow(
            uow_factory=self.uow_factory,
            dispatch_port=self.dispatch_port,
            complete_background_tracking=self._complete_background_tracking,
            run_id=run_id,
        )

    async def execute_prepared_runs(
        self,
        prepared_runs: tuple[PreparedToolRunExecution, ...],
    ) -> tuple[ToolRun, ...]:
        if not prepared_runs:
            return ()
        completions = await asyncio.gather(
            *(self._execute_prepared_runtime(prepared) for prepared in prepared_runs),
        )
        return await asyncio.to_thread(
            self._complete_run_results,
            tuple(completions),
        )

    async def fail_runs(
        self,
        run_ids: tuple[str, ...],
        *,
        message: str,
    ) -> tuple[ToolRun, ...]:
        if not run_ids:
            return ()
        return tuple(
            await asyncio.gather(
                *(asyncio.to_thread(self._fail_run, run_id, message) for run_id in run_ids),
            ),
        )

    def _execute_background_run_sync(self, run_id: str) -> ToolRun:
        return asyncio.run(self._perform_run(run_id))

    async def _perform_run(
        self,
        run_id: str,
        *,
        execution_context: ToolExecutionContext | None = None,
        manage_heartbeat: bool = True,
    ) -> ToolRun:
        prepared = await asyncio.to_thread(
            self._prepare_run_execution,
            run_id,
            execution_context,
        )
        if isinstance(prepared, ToolRun):
            return prepared
        return await self._perform_prepared_run(
            prepared,
            manage_heartbeat=manage_heartbeat,
        )

    async def _perform_prepared_run(
        self,
        prepared: PreparedToolRunExecution,
        *,
        manage_heartbeat: bool = True,
    ) -> ToolRun:
        completion = await self._execute_prepared_runtime(
            prepared,
            manage_heartbeat=manage_heartbeat,
        )
        return (
            await asyncio.to_thread(
                self._complete_run_results,
                (completion,),
            )
        )[0]

    async def _execute_prepared_runtime(
        self,
        prepared: PreparedToolRunExecution,
        *,
        manage_heartbeat: bool = True,
    ) -> PreparedToolRunCompletion:
        try:
            output = await self._execute_with_heartbeat(
                prepared.tool,
                prepared.arguments,
                run_id=prepared.run_id,
                target=prepared.target,
                worker_id=prepared.worker_id,
                execution_context=prepared.execution_context,
                manage_heartbeat=manage_heartbeat,
            )
        except Exception as exc:
            return PreparedToolRunCompletion(
                run_id=prepared.run_id,
                error_message=_exception_run_error(exc),
            )
        return PreparedToolRunCompletion(
            run_id=prepared.run_id,
            output=output,
        )

    def _prepare_run_execution(
        self,
        run_id: str,
        execution_context: ToolExecutionContext | None,
    ) -> PreparedToolRunExecution | ToolRun:
        return prepare_run_execution(
            uow_factory=self.uow_factory,
            catalog_service=self.catalog_service,
            complete_background_tracking=self._complete_background_tracking,
            run_id=run_id,
            execution_context=execution_context,
        )

    def _resolve_run_tool_for_concurrency(self, uow, run: ToolRun) -> Tool | None:
        return resolve_run_tool_for_concurrency(
            uow,
            run,
            catalog_service=self.catalog_service,
        )

    def _resolve_run_catalog_tool(self, uow, run: ToolRun) -> Tool | None:
        return resolve_run_catalog_tool(uow, run)

    def _complete_run_results(
        self,
        completions: tuple[PreparedToolRunCompletion, ...],
    ) -> tuple[ToolRun, ...]:
        return complete_run_results(
            uow_factory=self.uow_factory,
            metrics=self.metrics,
            dispatch_port=self.dispatch_port,
            complete_background_tracking=self._complete_background_tracking,
            completions=completions,
        )

    async def _execute_with_heartbeat(
        self,
        tool: Tool,
        arguments: dict[str, Any],
        *,
        run_id: str,
        target: ToolExecutionTarget,
        worker_id: str | None,
        execution_context: ToolExecutionContext | None,
        manage_heartbeat: bool = True,
    ) -> ToolRunResult:
        return await execute_tool_runtime_for_worker(
            runtime_gateway=self.runtime_gateway,
            tool=tool,
            arguments=arguments,
            run_id=run_id,
            target=target,
            worker_id=worker_id,
            execution_context=execution_context,
            manage_heartbeat=manage_heartbeat,
            heartbeat_context_factory=self._heartbeat_while_processing,
            artifact_service=self.artifact_service,
            details_max_chars=self.details_max_chars,
        )

    def _heartbeat_while_processing(
        self,
        *,
        run_id: str,
        worker_id: str,
    ) -> Any:
        return heartbeat_while_processing(
            run_id=run_id,
            worker_id=worker_id,
            heartbeat_seconds=self.worker_heartbeat_seconds,
            heartbeat_run=lambda current_run_id, current_worker_id: self.heartbeat_run(
                current_run_id,
                worker_id=current_worker_id,
            ),
            logger=logger,
        )

    def handle_recovered_dispatch_task(
        self,
        *,
        tool_run_id: str,
        reason: str,
    ) -> ToolRun | None:
        return handle_recovered_dispatch_task_in_uow(
            uow_factory=self.uow_factory,
            dispatch_port=self.dispatch_port,
            complete_background_tracking=self._complete_background_tracking,
            tool_run_id=tool_run_id,
            reason=reason,
        )

    def _fail_run(self, run_id: str, message: str) -> ToolRun:
        return fail_run(
            uow_factory=self.uow_factory,
            dispatch_port=self.dispatch_port,
            complete_background_tracking=self._complete_background_tracking,
            run_id=run_id,
            message=message,
        )

    def _apply_run_failure(
        self,
        uow,
        failed_run: ToolRun,
        message: str | ToolRunError,
    ) -> None:
        apply_run_failure_to_uow(
            uow,
            failed_run,
            message,
            dispatch_port=self.dispatch_port,
            complete_background_tracking=self._complete_background_tracking,
        )

    def _complete_background_tracking(
        self,
        uow,
        run: ToolRun,
        *,
        terminal_kind: str,
        reason: str | None = None,
    ) -> None:
        _complete_background_tracking(
            uow=uow,
            run=run,
            terminal_kind=terminal_kind,
            worker_lease_seconds=self.worker_lease_seconds,
            capabilities_payload_resolver=self._worker_capabilities_payload,
            reason=reason,
        )

    def _worker_capabilities_payload(
        self,
        capabilities_payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        return build_worker_capabilities_payload(
            capabilities_payload,
            metrics=self.metrics,
            runtime_registry=self.deps.runtime_registry,
            concurrency_policy=self.concurrency_policy,
        )
