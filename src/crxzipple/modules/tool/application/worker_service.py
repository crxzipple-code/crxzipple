from __future__ import annotations

import asyncio
from collections import Counter
from collections.abc import Mapping
from datetime import datetime, timezone
from threading import Event as ThreadEvent
from typing import Any

from crxzipple.core.logger import get_logger
from crxzipple.modules.tool.application.worker_assignment_selection import (
    select_runnable_assignment_run_ids,
)
from crxzipple.modules.tool.application.catalog_service import ToolCatalogService
from crxzipple.modules.tool.application.concurrency import ToolRunConcurrencyPolicy
from crxzipple.modules.tool.application.dispatch_events import ToolRuntimeEventService
from crxzipple.modules.tool.application.worker_capabilities import (
    build_worker_capabilities_payload,
)
from crxzipple.modules.tool.application.worker_completion import (
    apply_run_completion as _apply_run_completion,
    apply_run_failure as _apply_run_failure,
)
from crxzipple.modules.tool.application.ports import ToolEventWaitPort
from crxzipple.modules.tool.application.provider_backend_service import (
    PROVIDER_BACKEND_METADATA_KEY,
)
from crxzipple.modules.tool.application.service_support import (
    PreparedToolRunCompletion,
    PreparedToolRunExecution,
    ToolServiceBase,
    ToolServiceDependencies,
    build_tool_from_function,
)
from crxzipple.modules.tool.application.worker_errors import (
    exception_message as _exception_message,
    exception_run_error as _exception_run_error,
)
from crxzipple.modules.tool.application.worker_execution_context import (
    execution_context_with_provider_backend as _execution_context_with_provider_backend,
    execution_context_with_tool_run_id as _execution_context_with_tool_run_id,
)
from crxzipple.modules.tool.application.worker_recovery import (
    apply_recovered_dispatch_task as _apply_recovered_dispatch_task,
)
from crxzipple.modules.tool.application.worker_registration import (
    mark_worker_stale_in_uow,
    prune_expired_workers_in_uow,
    register_or_refresh_worker,
)
from crxzipple.modules.tool.application.worker_runtime_execution import (
    execute_tool_runtime_for_worker,
)
from crxzipple.modules.tool.application.worker_processing_heartbeat import (
    heartbeat_while_processing,
)
from crxzipple.modules.tool.application.worker_tracking import (
    complete_background_tracking as _complete_background_tracking,
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
from crxzipple.modules.tool.domain.exceptions import (
    ToolNotFoundError,
    ToolRunNotFoundError,
    ToolValidationError,
)
from crxzipple.modules.tool.domain.value_objects import (
    ToolExecutionContext,
    ToolExecutionTarget,
    ToolFunctionStatus,
    ToolMode,
    ToolRunAssignmentStatus,
    ToolRunError,
    ToolRunResult,
    ToolRunStatus,
    ToolSourceStatus,
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
        resolved_capabilities_payload = self._worker_capabilities_payload(
            capabilities_payload,
        )
        with self.uow_factory() as uow:
            worker = register_or_refresh_worker(
                uow,
                worker_id=worker_id,
                lease_seconds=self.worker_lease_seconds,
                max_in_flight=max_in_flight,
                capabilities_payload=resolved_capabilities_payload,
            )
            uow.commit()
            return worker

    def mark_worker_stale(self, *, worker_id: str):
        with self.uow_factory() as uow:
            worker = mark_worker_stale_in_uow(uow, worker_id=worker_id)
            if worker is None:
                return None
            uow.commit()
            return worker

    def list_workers(self) -> list[ToolWorkerRegistration]:
        with self.uow_factory() as uow:
            return uow.tool_workers.list()

    def prune_expired_workers(self, *, retention_seconds: int) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        with self.uow_factory() as uow:
            result = prune_expired_workers_in_uow(
                uow,
                retention_seconds=retention_seconds,
                now=now,
            )
            uow.commit()
        return {
            "pruned_count": result.pruned_count,
            "worker_ids": result.pruned_worker_ids,
            "cutoff": result.cutoff,
        }

    def list_assignments(self) -> list[ToolRunAssignment]:
        with self.uow_factory() as uow:
            return uow.tool_run_assignments.list()

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
            self._run_until_stopped_async(
                worker_id=worker_id,
                poll_interval_seconds=poll_interval_seconds,
                max_runs=max_runs,
                max_idle_cycles=max_idle_cycles,
                stop_event=stopper,
                events_service=events_service,
                runtime_event_service=runtime_event_service,
                max_in_flight=max_in_flight,
            ),
        )

    async def _run_until_stopped_async(
        self,
        *,
        worker_id: str,
        poll_interval_seconds: float,
        max_runs: int | None,
        max_idle_cycles: int | None,
        stop_event: ThreadEvent,
        events_service: ToolEventWaitPort | None,
        runtime_event_service: ToolRuntimeEventService | None,
        max_in_flight: int,
    ) -> int:
        processed_runs = 0
        idle_cycles = 0
        inflight_tasks: dict[str, asyncio.Task[ToolRun]] = {}

        logger.info(
            "tool worker started",
            extra={
                "poll_interval_seconds": poll_interval_seconds,
                "max_runs": max_runs,
                "max_idle_cycles": max_idle_cycles,
                "worker_id": worker_id,
                "max_in_flight": max_in_flight,
            },
        )

        heartbeat_task = asyncio.create_task(
            self._heartbeat_inflight_loop(
                worker_id=worker_id,
                stop_event=stop_event,
                inflight_tasks=inflight_tasks,
            ),
        )

        try:
            await asyncio.to_thread(
                self.register_worker,
                worker_id=worker_id,
                max_in_flight=max_in_flight,
            )
            while True:
                if runtime_event_service is not None:
                    await asyncio.to_thread(
                        runtime_event_service.process_available_events,
                    )
                await asyncio.to_thread(
                    self.register_worker,
                    worker_id=worker_id,
                    max_in_flight=max_in_flight,
                )

                processed_runs += await self._reap_inflight_tasks(inflight_tasks)

                if max_runs is not None and processed_runs >= max_runs and not inflight_tasks:
                    break
                if stop_event.is_set() and not inflight_tasks:
                    break

                launches_allowed = max(0, max_in_flight - len(inflight_tasks))
                if max_runs is not None:
                    launches_allowed = min(
                        launches_allowed,
                        max(0, max_runs - processed_runs - len(inflight_tasks)),
                    )
                launched = 0
                if not stop_event.is_set() and launches_allowed > 0:
                    launched = await self._launch_assignments(
                        worker_id=worker_id,
                        inflight_tasks=inflight_tasks,
                        max_new_assignments=launches_allowed,
                    )
                    if launched:
                        idle_cycles = 0

                if inflight_tasks:
                    idle_cycles = 0
                    done, _ = await asyncio.wait(
                        tuple(inflight_tasks.values()),
                        timeout=poll_interval_seconds,
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                    if done:
                        processed_runs += await self._reap_inflight_tasks(inflight_tasks)
                    continue

                if launched:
                    continue

                idle_cycles += 1
                if max_idle_cycles is not None and idle_cycles >= max_idle_cycles:
                    break
                await asyncio.to_thread(
                    self._wait_for_worker_wakeup,
                    stop_event=stop_event,
                    timeout_seconds=poll_interval_seconds,
                    events_service=events_service,
                    runtime_event_service=runtime_event_service,
                )
        finally:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass
            if inflight_tasks:
                await asyncio.wait(tuple(inflight_tasks.values()))
                await self._reap_inflight_tasks(inflight_tasks)
            await asyncio.to_thread(self.mark_worker_stale, worker_id=worker_id)

        return processed_runs

    async def _launch_assignments(
        self,
        *,
        worker_id: str,
        inflight_tasks: dict[str, asyncio.Task[ToolRun]],
        max_new_assignments: int,
    ) -> int:
        if max_new_assignments <= 0:
            return 0
        run_ids = await asyncio.to_thread(
            self._select_runnable_run_ids,
            worker_id,
            tuple(inflight_tasks.keys()),
            max_new_assignments,
        )
        for run_id in run_ids:
            inflight_tasks[run_id] = asyncio.create_task(
                self._perform_assigned_run(run_id),
                name=f"tool-run-{run_id}",
            )
        return len(run_ids)

    async def _reap_inflight_tasks(
        self,
        inflight_tasks: dict[str, asyncio.Task[ToolRun]],
    ) -> int:
        completed = 0
        for run_id, task in list(inflight_tasks.items()):
            if not task.done():
                continue
            try:
                await task
            except Exception:
                logger.exception(
                    "tool worker task failed during reap",
                    extra={"run_id": run_id},
                )
            finally:
                inflight_tasks.pop(run_id, None)
            completed += 1
        return completed

    async def _perform_assigned_run(self, run_id: str) -> ToolRun:
        try:
            return await self._perform_run(
                run_id,
                manage_heartbeat=False,
            )
        except Exception as exc:
            logger.exception(
                "tool worker failed while executing assigned run",
                extra={"run_id": run_id},
            )
            return await asyncio.to_thread(
                self._fail_run,
                run_id,
                _exception_message(exc),
            )

    async def _heartbeat_inflight_loop(
        self,
        *,
        worker_id: str,
        stop_event: ThreadEvent,
        inflight_tasks: dict[str, asyncio.Task[ToolRun]],
    ) -> None:
        if self.worker_heartbeat_seconds <= 0:
            return
        while not stop_event.is_set():
            await asyncio.sleep(self.worker_heartbeat_seconds)
            run_ids = tuple(inflight_tasks.keys())
            if not run_ids:
                continue
            results = await asyncio.gather(
                *(
                    asyncio.to_thread(
                        self.heartbeat_run,
                        run_id,
                        worker_id=worker_id,
                    )
                    for run_id in run_ids
                ),
                return_exceptions=True,
            )
            for run_id, result in zip(run_ids, results, strict=False):
                if isinstance(result, Exception):
                    logger.error(
                        "failed to heartbeat inflight tool run",
                        extra={"run_id": run_id, "worker_id": worker_id},
                        exc_info=(type(result), result, result.__traceback__),
                    )

    def _select_runnable_run_ids(
        self,
        worker_id: str,
        exclude_run_ids: tuple[str, ...],
        limit: int,
    ) -> tuple[str, ...]:
        excluded = set(exclude_run_ids)
        with self.uow_factory() as uow:
            assignments = [
                assignment
                for assignment in uow.tool_run_assignments.list_for_worker(worker_id)
                if assignment.status in {
                    ToolRunAssignmentStatus.ASSIGNED,
                    ToolRunAssignmentStatus.RUNNING,
                }
                and assignment.run_id not in excluded
            ]
            excluded_runs = uow.tool_runs.get_many(tuple(excluded))
            active_counts: Counter[str] = Counter()
            for run in excluded_runs.values():
                if run.is_terminal():
                    continue
                tool = self._resolve_run_tool_for_concurrency(uow, run)
                if tool is None:
                    continue
                self.concurrency_policy.reserve(
                    run=run,
                    tool=tool,
                    active_counts=active_counts,
                )
            runs_by_id = uow.tool_runs.get_many(
                tuple(assignment.run_id for assignment in assignments),
            )
        return select_runnable_assignment_run_ids(
            assignments,
            runs_by_id=runs_by_id,
            active_counts=active_counts,
            limit=limit,
            concurrency_policy=self.concurrency_policy,
            resolve_tool_for_run=lambda run: self._resolve_run_tool_for_concurrency(
                uow,
                run,
            ),
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
        with self.uow_factory() as uow:
            run = uow.tool_runs.get(run_id)
            if run is None:
                raise ToolRunNotFoundError(f"Tool run '{run_id}' was not found.")
            if run.is_terminal():
                return run
            if run.worker_id != worker_id:
                logger.warning(
                    "skipping heartbeat for tool run owned by another worker",
                    extra={
                        "run_id": run.id,
                        "expected_worker_id": worker_id,
                        "actual_worker_id": run.worker_id,
                    },
                )
                return run
            run.heartbeat(lease_seconds=self.worker_lease_seconds)
            assignment = uow.tool_run_assignments.get_latest_for_run_and_worker(
                run.id,
                worker_id,
            )
            if assignment is not None:
                assignment.heartbeat(lease_seconds=self.worker_lease_seconds)
                uow.tool_run_assignments.add(assignment)
                uow.collect(assignment)
            worker = uow.tool_workers.get(worker_id)
            if worker is not None:
                worker.refresh(
                    lease_seconds=self.worker_lease_seconds,
                    capabilities_payload=self._worker_capabilities_payload(
                        worker.capabilities_payload,
                    ),
                )
                uow.tool_workers.add(worker)
                uow.collect(worker)
            self.dispatch_port.heartbeat(
                uow.dispatch_tasks,
                uow,
                run,
                worker_id=worker_id,
                lease_seconds=self.worker_lease_seconds,
            )
            uow.tool_runs.add(run)
            uow.collect(run)
            uow.commit()
            return run

    def cancel_tool_run(self, run_id: str) -> ToolRun:
        with self.uow_factory() as uow:
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
                    self.dispatch_port.cancel(uow.dispatch_tasks, uow, run)
                    self._complete_background_tracking(
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
        with self.uow_factory() as uow:
            run = uow.tool_runs.get(run_id)
            if run is None:
                raise ToolRunNotFoundError(f"Tool run '{run_id}' was not found.")

            if run.is_terminal():
                return run

            if run.status is ToolRunStatus.CANCEL_REQUESTED:
                run.cancel()
                if run.target.mode is ToolMode.BACKGROUND:
                    self._complete_background_tracking(
                        uow,
                        run,
                        terminal_kind="cancelled",
                    )
                uow.tool_runs.add(run)
                uow.collect(run)
                uow.commit()
                return run

            tool = self._resolve_run_catalog_tool(uow, run)
            if tool is None:
                tool = self.catalog_service.resolve_tool(run.tool_id)
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

            arguments = dict(run.input_payload)
            resolved_execution_context = (
                execution_context
                if execution_context is not None
                else run.invocation_context
            )
            resolved_execution_context = _execution_context_with_tool_run_id(
                resolved_execution_context,
                run.id,
            )
            provider_backend_payload = run.metadata.get(
                PROVIDER_BACKEND_METADATA_KEY,
            )
            resolved_execution_context = _execution_context_with_provider_backend(
                resolved_execution_context,
                (
                    provider_backend_payload
                    if isinstance(provider_backend_payload, Mapping)
                    else None
                ),
            )
            return PreparedToolRunExecution(
                tool=tool,
                arguments=arguments,
                run_id=run.id,
                target=run.target,
                worker_id=run.worker_id,
                execution_context=resolved_execution_context,
            )

    def _resolve_run_tool_for_concurrency(self, uow, run: ToolRun) -> Tool | None:
        if run.function_id is not None:
            function = uow.tool_functions.get(run.function_id)
            if function is not None:
                return build_tool_from_function(function)
        return self.catalog_service.resolve_tool(run.tool_id)

    def _resolve_run_catalog_tool(self, uow, run: ToolRun) -> Tool | None:
        if run.function_id is None:
            return None
        function = uow.tool_functions.get(run.function_id)
        if function is None:
            raise ToolValidationError(
                f"Tool run '{run.id}' references missing function '{run.function_id}'.",
            )
        source = uow.tool_sources.get(function.source_id)
        if source is None:
            raise ToolValidationError(
                f"Tool run '{run.id}' references missing source '{function.source_id}'.",
            )
        if source.status is not ToolSourceStatus.ACTIVE:
            raise ToolValidationError(
                f"Tool source '{source.source_id}' is {source.status.value}.",
            )
        if function.status is not ToolFunctionStatus.ACTIVE:
            raise ToolValidationError(
                f"Tool function '{function.function_id}' is {function.status.value}.",
            )
        if not function.enabled:
            raise ToolValidationError(
                f"Tool function '{function.function_id}' is disabled.",
            )
        return build_tool_from_function(function)

    def _complete_run_results(
        self,
        completions: tuple[PreparedToolRunCompletion, ...],
    ) -> tuple[ToolRun, ...]:
        with self.uow_factory() as uow:
            with self.metrics.timed(
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
                _apply_run_completion(
                    uow,
                    run,
                    completion,
                    dispatch_port=self.dispatch_port,
                    complete_background_tracking=self._complete_background_tracking,
                )
                uow.tool_runs.add(run)
                uow.collect(run)
                completed_runs.append(run)
            with self.metrics.timed(
                "tool.service.persistence_seconds",
                labels={"operation": "complete_runs", "phase": "commit"},
            ):
                uow.commit()
            return tuple(completed_runs)

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
        with self.uow_factory() as uow:
            run = uow.tool_runs.get(tool_run_id)
            if run is None:
                return None
            _apply_recovered_dispatch_task(
                uow,
                run,
                reason=reason,
                dispatch_port=self.dispatch_port,
                complete_background_tracking=self._complete_background_tracking,
            )
            uow.tool_runs.add(run)
            uow.collect(run)
            uow.commit()
            return run

    def _fail_run(self, run_id: str, message: str) -> ToolRun:
        with self.uow_factory() as uow:
            failed_run = uow.tool_runs.get(run_id)
            if failed_run is None:
                raise ToolRunNotFoundError(
                    f"Tool run '{run_id}' was not found after execution failure.",
                )
            self._apply_run_failure(uow, failed_run, message)
            uow.tool_runs.add(failed_run)
            uow.collect(failed_run)
            uow.commit()
            return failed_run

    def _apply_run_failure(
        self,
        uow,
        failed_run: ToolRun,
        message: str | ToolRunError,
    ) -> None:
        _apply_run_failure(
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
