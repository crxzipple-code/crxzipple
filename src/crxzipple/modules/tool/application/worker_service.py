from __future__ import annotations

import asyncio
from collections import Counter
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
import json
import threading
from contextlib import contextmanager
from threading import Event as ThreadEvent
from typing import Any

from crxzipple.core.logger import get_logger
from crxzipple.modules.events.domain import EventTopicWatch
from crxzipple.modules.tool.application.catalog_service import ToolCatalogService
from crxzipple.modules.tool.application.concurrency import ToolRunConcurrencyPolicy
from crxzipple.modules.tool.application.dispatch_events import ToolRuntimeEventService
from crxzipple.modules.tool.application.ports import ToolEventWaitPort
from crxzipple.modules.tool.application.provider_backend_service import (
    PROVIDER_BACKEND_METADATA_KEY,
    provider_backend_execution_context_payload,
)
from crxzipple.modules.tool.application.result_envelope import (
    TOOL_RESULT_ENVELOPE_METADATA_KEY,
    TOOL_RESULT_RAW_OUTPUT_BLOCKS_METADATA_KEY,
    ToolResultEnvelope,
)
from crxzipple.modules.tool.application.service_support import (
    DISPATCH_LEASE_EXHAUSTED_REASON,
    DISPATCH_LEASE_EXPIRED_REASON,
    PreparedToolRunCompletion,
    PreparedToolRunExecution,
    ToolServiceBase,
    ToolServiceDependencies,
    build_tool_from_function,
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
from crxzipple.shared.content_blocks import (
    FILE_BLOCK_TYPE,
    IMAGE_BLOCK_TYPE,
    TEXT_BLOCK_TYPE,
    file_ref_content_block,
    image_ref_content_block,
    text_content_block,
)
from crxzipple.shared.domain.events import Event, named_event_topic

logger = get_logger(__name__)

_LARGE_TEXT_RESULT_ARTIFACT_THRESHOLD_CHARS = 20_000
_LARGE_TEXT_RESULT_PREVIEW_CHARS = 1_600


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
            worker = uow.tool_workers.get(worker_id)
            if worker is None:
                from crxzipple.modules.tool.domain.entities import ToolWorkerRegistration

                worker = ToolWorkerRegistration.create(
                    worker_id=worker_id,
                    lease_seconds=self.worker_lease_seconds,
                    max_in_flight=max_in_flight,
                    capabilities_payload=resolved_capabilities_payload,
                )
                uow.tool_workers.add_new(worker)
            else:
                worker.refresh(
                    lease_seconds=self.worker_lease_seconds,
                    max_in_flight=max_in_flight,
                    capabilities_payload=resolved_capabilities_payload,
                )
                self._reconcile_worker_assignments(uow, worker)
                uow.tool_workers.add(worker)
            uow.collect(worker)
            uow.commit()
            return worker

    def mark_worker_stale(self, *, worker_id: str):
        with self.uow_factory() as uow:
            worker = uow.tool_workers.get(worker_id)
            if worker is None:
                return None
            worker.mark_stale()
            uow.tool_workers.add(worker)
            uow.collect(worker)
            uow.commit()
            return worker

    def list_workers(self) -> list[ToolWorkerRegistration]:
        with self.uow_factory() as uow:
            return uow.tool_workers.list()

    def prune_expired_workers(self, *, retention_seconds: int) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=max(int(retention_seconds), 0))
        pruned_worker_ids: list[str] = []
        with self.uow_factory() as uow:
            for worker in uow.tool_workers.list():
                if worker.lease_expires_at is None:
                    continue
                if worker.lease_expires_at > cutoff:
                    continue
                if any(
                    not assignment.is_terminal()
                    for assignment in uow.tool_run_assignments.list_for_worker(worker.id)
                ):
                    continue
                worker.record_event(
                    Event(
                        name="tool.worker.pruned",
                        payload={
                            "worker_id": worker.id,
                            "status": worker.status.value,
                            "last_heartbeat": worker.heartbeat_at.isoformat(),
                            "lease_expires_at": worker.lease_expires_at.isoformat(),
                            "retention_seconds": max(int(retention_seconds), 0),
                        },
                    ),
                )
                uow.collect(worker)
                uow.tool_workers.delete(worker.id)
                pruned_worker_ids.append(worker.id)
            uow.commit()
        return {
            "pruned_count": len(pruned_worker_ids),
            "worker_ids": tuple(pruned_worker_ids),
            "cutoff": cutoff,
        }

    def list_assignments(self) -> list[ToolRunAssignment]:
        with self.uow_factory() as uow:
            return uow.tool_run_assignments.list()

    def _reconcile_worker_assignments(self, uow, worker) -> None:
        active_count = 0
        for assignment in uow.tool_run_assignments.list_for_worker(worker.id):
            if assignment.is_terminal():
                continue
            run = uow.tool_runs.get(assignment.run_id)
            if (
                run is None
                or run.is_terminal()
                or run.worker_id != worker.id
            ):
                assignment.expire(
                    reason="Worker registration reconciled stale assignment.",
                )
                uow.tool_run_assignments.add(assignment)
                uow.collect(assignment)
                continue
            active_count += 1
        worker.sync_current_in_flight(active_count)

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
                self._exception_message(exc),
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
        assignments.sort(key=lambda assignment: assignment.assigned_at)
        selected: list[str] = []
        for assignment in assignments:
            run = runs_by_id.get(assignment.run_id)
            if run is None or run.is_terminal():
                continue
            tool = self._resolve_run_tool_for_concurrency(uow, run)
            if tool is None:
                continue
            if not self.concurrency_policy.can_start(
                run=run,
                tool=tool,
                active_counts=active_counts,
            ):
                continue
            self.concurrency_policy.reserve(
                run=run,
                tool=tool,
                active_counts=active_counts,
            )
            selected.append(assignment.run_id)
            if len(selected) >= limit:
                break
        return tuple(selected)

    def _wait_for_worker_wakeup(
        self,
        *,
        stop_event: ThreadEvent,
        timeout_seconds: float,
        events_service: ToolEventWaitPort | None,
        runtime_event_service: ToolRuntimeEventService | None,
    ) -> None:
        if events_service is None:
            stop_event.wait(timeout_seconds)
            return
        watches = [
            EventTopicWatch(
                topic=named_event_topic("tool.assignment.created"),
                after_cursor=events_service.snapshot_event_topic(
                    named_event_topic("tool.assignment.created"),
                ),
            ),
        ]
        if runtime_event_service is not None:
            watches.extend(runtime_event_service.build_wait_watches())
        events_service.wait_for_event_topics(
            tuple(watches),
            timeout_seconds=timeout_seconds,
            stop_event=stop_event,
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
                error_message=self._exception_run_error(exc),
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
                if completion.error_message is not None:
                    self._apply_run_failure(
                        uow,
                        run,
                        completion.error_message,
                    )
                else:
                    output = completion.output
                    if output is None:
                        raise ToolValidationError(
                            f"Tool run '{completion.run_id}' completed without output or error.",
                        )
                    if run.status is ToolRunStatus.CANCEL_REQUESTED:
                        run.cancel()
                        if run.target.mode is ToolMode.BACKGROUND:
                            self.dispatch_port.cancel(uow.dispatch_tasks, uow, run)
                            self._complete_background_tracking(
                                uow,
                                run,
                                terminal_kind="cancelled",
                            )
                    else:
                        run.succeed(output)
                        if run.target.mode is ToolMode.BACKGROUND:
                            self.dispatch_port.complete(uow.dispatch_tasks, uow, run)
                            self._complete_background_tracking(
                                uow,
                                run,
                                terminal_kind="succeeded",
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
        if target.mode is not ToolMode.BACKGROUND or worker_id is None:
            result = await self.runtime_gateway.execute(
                tool,
                target,
                arguments,
                execution_context=execution_context,
            )
        else:
            if manage_heartbeat:
                with self._heartbeat_while_processing(run_id=run_id, worker_id=worker_id):
                    result = await self.runtime_gateway.execute(
                        tool,
                        target,
                        arguments,
                        execution_context=execution_context,
                    )
            else:
                result = await self.runtime_gateway.execute(
                    tool,
                    target,
                    arguments,
                    execution_context=execution_context,
                )
        if not isinstance(result, ToolRunResult):
            raise ToolValidationError(
                f"Tool runtime '{tool.resolved_runtime_key()}' must return ToolRunResult.",
            )
        result = self._externalize_inline_attachments(
            result,
            run_id=run_id,
            tool=tool,
        )
        self._validate_result_details(result)
        return result

    def _externalize_inline_attachments(
        self,
        result: ToolRunResult,
        *,
        run_id: str,
        tool: Tool,
    ) -> ToolRunResult:
        if self.artifact_service is None:
            return result
        transformed_blocks: list[dict[str, Any]] = []
        metadata = dict(result.metadata)
        large_text_artifacts: list[dict[str, Any]] = []
        raw_output_artifacts = self._externalize_raw_output_blocks(
            metadata.pop(TOOL_RESULT_RAW_OUTPUT_BLOCKS_METADATA_KEY, None),
            run_id=run_id,
            tool=tool,
        )
        artifact_ids: list[str] = [
            str(item).strip()
            for item in metadata.get("artifact_ids", ())
            if str(item).strip()
        ] if isinstance(metadata.get("artifact_ids"), list) else []
        artifact_ids.extend(
            str(item["artifact_id"])
            for item in raw_output_artifacts
            if str(item.get("artifact_id") or "").strip()
        )
        changed = False
        for index, block in enumerate(result.blocks):
            block_type = str(block.get("type") or "").strip()
            if block_type == TEXT_BLOCK_TYPE:
                externalized = self._externalize_large_text_block(
                    block,
                    run_id=run_id,
                    tool=tool,
                    block_index=index,
                )
                if externalized is not None:
                    transformed_blocks.append(externalized["block"])
                    artifact = externalized["artifact"]
                    artifact_ids.append(str(artifact["artifact_id"]))
                    large_text_artifacts.append(artifact)
                    changed = True
                    continue
            if block_type == IMAGE_BLOCK_TYPE:
                transformed_blocks.append(self._externalize_image_block(block))
                changed = True
                continue
            if block_type == FILE_BLOCK_TYPE:
                transformed_blocks.append(self._externalize_file_block(block))
                changed = True
                continue
            transformed_blocks.append(dict(block))
        if raw_output_artifacts:
            changed = True
        if not changed:
            return result
        if artifact_ids:
            metadata["artifact_ids"] = list(dict.fromkeys(artifact_ids))
        if large_text_artifacts:
            metadata["large_text_artifact_ids"] = [
                item["artifact_id"] for item in large_text_artifacts
            ]
            metadata["externalized_text_blocks"] = large_text_artifacts
        if raw_output_artifacts:
            metadata["raw_output_artifact_ids"] = [
                item["artifact_id"] for item in raw_output_artifacts
            ]
            metadata["externalized_raw_output_blocks"] = raw_output_artifacts
        if large_text_artifacts or raw_output_artifacts:
            artifact_envelope = _artifact_result_envelope(
                large_text_artifacts=large_text_artifacts,
                raw_output_artifacts=raw_output_artifacts,
            ).to_payload()
            metadata[TOOL_RESULT_ENVELOPE_METADATA_KEY] = (
                _merge_tool_result_envelopes(
                    metadata.get(TOOL_RESULT_ENVELOPE_METADATA_KEY),
                    artifact_envelope,
                )
            )
        return ToolRunResult(
            content=transformed_blocks,
            details=result.details,
            metadata=metadata,
        )

    def _externalize_raw_output_blocks(
        self,
        raw_blocks: Any,
        *,
        run_id: str,
        tool: Tool,
    ) -> list[dict[str, Any]]:
        if not isinstance(raw_blocks, list):
            return []
        artifacts: list[dict[str, Any]] = []
        for index, item in enumerate(raw_blocks):
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            if not isinstance(text, str) or not text:
                continue
            stream_name = str(item.get("name") or f"raw-{index + 1}").strip()
            encoded = text.encode("utf-8")
            artifact_name = _raw_output_artifact_name(
                tool=tool,
                stream_name=stream_name,
                block_index=index,
            )
            artifact = self.artifact_service.create_artifact(
                data=encoded,
                mime_type=str(item.get("mime_type") or "text/plain"),
                name=artifact_name,
                metadata={
                    "source": "tool.raw_output",
                    "tool_id": tool.id,
                    "tool_name": tool.name,
                    "tool_run_id": run_id,
                    "raw_output_name": stream_name,
                    "raw_output_block_index": index,
                    "original_text_chars": len(text),
                    "original_text_bytes": len(encoded),
                },
            )
            artifacts.append(
                {
                    "artifact_id": artifact.id,
                    "mime_type": artifact.mime_type,
                    "name": artifact.name,
                    "size_bytes": artifact.size_bytes,
                    "raw_output_name": stream_name,
                    "original_text_chars": len(text),
                    "omitted_chars": len(text),
                    "content_block_index": None,
                },
            )
        return artifacts

    def _externalize_large_text_block(
        self,
        block: dict[str, Any],
        *,
        run_id: str,
        tool: Tool,
        block_index: int,
    ) -> dict[str, Any] | None:
        text = block.get("text")
        if not isinstance(text, str):
            return None
        if len(text) <= _LARGE_TEXT_RESULT_ARTIFACT_THRESHOLD_CHARS:
            return None
        encoded = text.encode("utf-8")
        name = _large_text_artifact_name(tool=tool, block_index=block_index)
        artifact = self.artifact_service.create_artifact(
            data=encoded,
            mime_type="text/plain",
            name=name,
            metadata={
                "source": "tool.large_text_result",
                "tool_id": tool.id,
                "tool_name": tool.name,
                "tool_run_id": run_id,
                "content_block_index": block_index,
                "original_text_chars": len(text),
                "original_text_bytes": len(encoded),
            },
        )
        preview = text[:_LARGE_TEXT_RESULT_PREVIEW_CHARS].rstrip()
        omitted_chars = max(len(text) - len(preview), 0)
        summary = (
            "[large tool result externalized]\n"
            f"artifact_id: {artifact.id}\n"
            f"name: {artifact.name or name}\n"
            f"mime_type: {artifact.mime_type}\n"
            f"original_chars: {len(text)}\n"
            f"omitted_chars: {omitted_chars}\n"
            "Use the artifact owner read hint if the full result is needed."
        )
        if preview:
            summary = f"{summary}\n\npreview:\n{preview}"
        return {
            "block": text_content_block(summary),
            "artifact": {
                "artifact_id": artifact.id,
                "mime_type": artifact.mime_type,
                "name": artifact.name,
                "size_bytes": artifact.size_bytes,
                "original_text_chars": len(text),
                "omitted_chars": omitted_chars,
                "content_block_index": block_index,
            },
        }

    def _externalize_image_block(self, block: dict[str, Any]) -> dict[str, Any]:
        from crxzipple.modules.tool.application.service_support import (
            decode_tool_attachment_bytes,
        )

        data = block.get("data")
        mime_type = block.get("mime_type")
        if not isinstance(data, str) or not isinstance(mime_type, str):
            return dict(block)
        decoded = decode_tool_attachment_bytes(data)
        if decoded is None:
            return dict(block)
        name = block.get("name")
        artifact = self.artifact_service.create_artifact(
            data=decoded,
            mime_type=mime_type,
            name=name if isinstance(name, str) and name.strip() else None,
            metadata={"source": "tool.inline_image"},
        )
        return image_ref_content_block(
            artifact_id=artifact.id,
            mime_type=artifact.mime_type,
            name=artifact.name,
        )

    def _externalize_file_block(self, block: dict[str, Any]) -> dict[str, Any]:
        from crxzipple.modules.tool.application.service_support import (
            decode_tool_attachment_bytes,
        )

        data = block.get("data")
        mime_type = block.get("mime_type")
        if not isinstance(data, str) or not isinstance(mime_type, str):
            return dict(block)
        decoded = decode_tool_attachment_bytes(data)
        if decoded is None:
            return dict(block)
        name = block.get("name")
        artifact = self.artifact_service.create_artifact(
            data=decoded,
            mime_type=mime_type,
            name=name if isinstance(name, str) and name.strip() else None,
            metadata={"source": "tool.inline_file"},
        )
        return file_ref_content_block(
            artifact_id=artifact.id,
            mime_type=artifact.mime_type,
            name=artifact.name,
        )

    def _validate_result_details(self, result: ToolRunResult) -> None:
        if result.details is None:
            return
        try:
            serialized = json.dumps(
                result.details,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
        except TypeError as exc:
            raise ToolValidationError(
                "Tool run result details must be JSON-serializable.",
            ) from exc
        if len(serialized) > self.details_max_chars:
            raise ToolValidationError(
                "Tool run result details exceed the allowed size budget "
                f"({self.details_max_chars} chars).",
            )

    @contextmanager
    def _heartbeat_while_processing(
        self,
        *,
        run_id: str,
        worker_id: str,
    ) -> Any:
        if self.worker_heartbeat_seconds <= 0:
            yield
            return
        stop_event = threading.Event()

        def _run_heartbeat_loop() -> None:
            while not stop_event.wait(self.worker_heartbeat_seconds):
                try:
                    run = self.heartbeat_run(run_id, worker_id=worker_id)
                except Exception:
                    logger.exception(
                        "failed to heartbeat tool run while processing",
                        extra={"run_id": run_id, "worker_id": worker_id},
                    )
                    return
                if run.status not in {
                    ToolRunStatus.DISPATCHING,
                    ToolRunStatus.RUNNING,
                    ToolRunStatus.CANCEL_REQUESTED,
                }:
                    return

        heartbeat_thread = threading.Thread(
            target=_run_heartbeat_loop,
            name=f"tool-heartbeat-{run_id[:8]}",
            daemon=True,
        )
        heartbeat_thread.start()
        try:
            yield
        finally:
            stop_event.set()
            heartbeat_thread.join(timeout=max(self.worker_heartbeat_seconds * 2, 0.2))

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
            if run.is_terminal() or run.status is ToolRunStatus.QUEUED:
                return run
            if run.status is ToolRunStatus.CANCEL_REQUESTED:
                run.cancel()
                self.dispatch_port.cancel(uow.dispatch_tasks, uow, run)
                self._complete_background_tracking(
                    uow,
                    run,
                    terminal_kind="cancelled",
                    reason=reason,
                )
            elif run.can_retry():
                self._complete_background_tracking(
                    uow,
                    run,
                    terminal_kind="expired",
                    reason=reason,
                )
                run.requeue(reason)
            else:
                run.fail(self._retry_exhausted_reason(reason))
                self.dispatch_port.fail(uow.dispatch_tasks, uow, run)
                self._complete_background_tracking(
                    uow,
                    run,
                    terminal_kind="expired",
                    reason=reason,
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
        run_error = self._coerce_run_error(message)
        failure_message = run_error.message
        if failed_run.status is ToolRunStatus.CANCEL_REQUESTED:
            failed_run.cancel()
            self.dispatch_port.cancel(uow.dispatch_tasks, uow, failed_run)
            self._complete_background_tracking(
                uow,
                failed_run,
                terminal_kind="cancelled",
                reason=failure_message,
            )
        elif failed_run.target.mode is ToolMode.BACKGROUND and failed_run.can_retry():
            self._complete_background_tracking(
                uow,
                failed_run,
                terminal_kind="failed",
                reason=failure_message,
            )
            failed_run.requeue(run_error)
            self.dispatch_port.requeue(
                uow.dispatch_tasks,
                uow,
                failed_run,
                reason=failure_message,
            )
        else:
            failed_run.fail(run_error)
            if failed_run.target.mode is ToolMode.BACKGROUND:
                self.dispatch_port.fail(uow.dispatch_tasks, uow, failed_run)
                self._complete_background_tracking(
                    uow,
                    failed_run,
                    terminal_kind="failed",
                    reason=failure_message,
                )

    @staticmethod
    def _retry_exhausted_reason(reason: str) -> str:
        normalized = ToolWorkerService._failure_message(reason)
        if normalized == DISPATCH_LEASE_EXPIRED_REASON:
            return DISPATCH_LEASE_EXHAUSTED_REASON
        return f"{normalized} (retry budget exhausted)"

    @staticmethod
    def _exception_message(exc: Exception) -> str:
        message = str(exc).strip()
        if message:
            return message
        return f"{exc.__class__.__name__} raised without an error message."

    @classmethod
    def _exception_run_error(cls, exc: Exception) -> ToolRunError:
        payload = _exception_payload(exc)
        if payload is not None:
            message = cls._failure_message(payload.get("message"))
            code = str(payload.get("code") or "execution_failed").strip() or "execution_failed"
            details = {
                str(key): _safe_error_detail(value)
                for key, value in payload.items()
                if key not in {"message", "code"}
            }
            return ToolRunError(message=message, code=code, details=details)
        return ToolRunError(message=cls._exception_message(exc))

    @classmethod
    def _coerce_run_error(cls, message: str | ToolRunError) -> ToolRunError:
        if isinstance(message, ToolRunError):
            return message
        return ToolRunError(message=cls._failure_message(message))

    @staticmethod
    def _failure_message(message: object) -> str:
        normalized = str(message).strip()
        return normalized or "Tool run failed without an error message."

    def _complete_background_tracking(
        self,
        uow,
        run: ToolRun,
        *,
        terminal_kind: str,
        reason: str | None = None,
    ) -> None:
        if run.target.mode is not ToolMode.BACKGROUND or run.worker_id is None:
            return
        assignment = uow.tool_run_assignments.get_latest_for_run_and_worker(
            run.id,
            run.worker_id,
        )
        if assignment is not None and not assignment.is_terminal():
            if terminal_kind == "succeeded":
                assignment.succeed()
            elif terminal_kind == "cancelled":
                assignment.cancel(reason=reason)
            elif terminal_kind == "expired":
                assignment.expire(reason=reason or "assignment expired")
            else:
                assignment.fail(reason or "tool run failed")
            uow.tool_run_assignments.add(assignment)
            uow.collect(assignment)
        worker = uow.tool_workers.get(run.worker_id)
        if worker is not None:
            worker.refresh(
                lease_seconds=self.worker_lease_seconds,
                capabilities_payload=self._worker_capabilities_payload(
                    worker.capabilities_payload,
                ),
            )
            worker.release_slot()
            uow.tool_workers.add(worker)
            uow.collect(worker)

    def _worker_capabilities_payload(
        self,
        capabilities_payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        payload = dict(capabilities_payload or {})
        payload["runtime_metrics"] = self.metrics.snapshot(
            prefixes=("tool.remote_provider_limiter.",),
        )
        runtime_registry_snapshot = self._runtime_registry_snapshot()
        if runtime_registry_snapshot:
            payload["runtime_registry"] = runtime_registry_snapshot
        payload["concurrency_policy"] = {
            "default_max_in_flight": self.concurrency_policy.default_max_in_flight,
            "image_max_in_flight": self.concurrency_policy.image_max_in_flight,
            "shared_state_max_in_flight": self.concurrency_policy.shared_state_max_in_flight,
        }
        return payload

    def _runtime_registry_snapshot(self) -> dict[str, Any]:
        snapshot = getattr(self.deps.runtime_registry, "snapshot", None)
        if callable(snapshot):
            try:
                payload = snapshot()
            except Exception:
                return {}
            return dict(payload) if isinstance(payload, dict) else {}
        registrations = getattr(self.deps.runtime_registry, "registrations", None)
        if not callable(registrations):
            return {}
        try:
            values = registrations()
        except Exception:
            return {}
        entries: list[dict[str, object]] = []
        for item in values:
            runtime_key = getattr(item, "runtime_key", None)
            if not isinstance(runtime_key, str) or not runtime_key.strip():
                continue
            entries.append(
                {
                    "runtime_key": runtime_key.strip(),
                    "concurrency_key": getattr(item, "concurrency_key", None),
                    "max_concurrency": getattr(item, "max_concurrency", None),
                },
            )
        return {"registrations": entries} if entries else {}


def _large_text_artifact_name(*, tool: Tool, block_index: int) -> str:
    base = tool.id or tool.name or "tool-result"
    normalized = "".join(
        char if char.isalnum() or char in {"-", "_", "."} else "-"
        for char in base.strip()
    ).strip("-.")
    return f"{(normalized or 'tool-result')[:96]}-result-{block_index + 1}.txt"


def _raw_output_artifact_name(
    *,
    tool: Tool,
    stream_name: str,
    block_index: int,
) -> str:
    base = tool.id or tool.name or "tool-result"
    suffix = stream_name or f"raw-{block_index + 1}"
    normalized_base = "".join(
        char if char.isalnum() or char in {"-", "_", "."} else "-"
        for char in base.strip()
    ).strip("-.")
    normalized_suffix = "".join(
        char if char.isalnum() or char in {"-", "_", "."} else "-"
        for char in suffix.strip()
    ).strip("-.")
    return (
        f"{(normalized_base or 'tool-result')[:80]}"
        f"-{(normalized_suffix or 'raw')[:32]}-{block_index + 1}.txt"
    )


def _artifact_result_envelope(
    *,
    large_text_artifacts: list[dict[str, Any]],
    raw_output_artifacts: list[dict[str, Any]],
) -> ToolResultEnvelope:
    artifacts = [*large_text_artifacts, *raw_output_artifacts]
    evidence_refs = tuple(
        str(item["artifact_id"])
        for item in artifacts
        if str(item.get("artifact_id") or "").strip()
    )
    omitted_chars = sum(
        int(item.get("omitted_chars") or 0)
        for item in artifacts
    )
    original_chars = sum(
        int(item.get("original_text_chars") or 0)
        for item in artifacts
    )
    return ToolResultEnvelope(
        status="ok",
        summary=_artifact_result_summary(
            large_text_artifacts=large_text_artifacts,
            raw_output_artifacts=raw_output_artifacts,
        ),
        output_payload={
            "externalized": True,
            "artifact_count": len(evidence_refs),
        },
        artifact_refs=tuple(
            {
                "kind": "artifact",
                "artifact_id": item.get("artifact_id"),
                "mime_type": item.get("mime_type"),
                "name": item.get("name"),
            }
            for item in artifacts
        ),
        key_facts={
            "externalized_text_block_count": len(large_text_artifacts),
            "externalized_raw_output_block_count": len(raw_output_artifacts),
            "artifact_count": len(evidence_refs),
            "original_text_chars": original_chars,
        },
        evidence_refs=evidence_refs,
        read_handles=tuple(
            {
                "kind": "artifact",
                "artifact_id": item.get("artifact_id"),
                "mime_type": item.get("mime_type"),
                "name": item.get("name"),
            }
            for item in artifacts
        ),
        omitted_count=len(artifacts),
        omitted_chars=omitted_chars,
        truncated=True,
        provider_replay_payload={
            "summary": _artifact_result_summary(
                large_text_artifacts=large_text_artifacts,
                raw_output_artifacts=raw_output_artifacts,
            ),
            "artifact_refs": list(evidence_refs),
            "read_handles": [
                {"kind": "artifact", "artifact_id": artifact_id}
                for artifact_id in evidence_refs
            ],
        },
        user_summary_payload={
            "summary": _artifact_result_summary(
                large_text_artifacts=large_text_artifacts,
                raw_output_artifacts=raw_output_artifacts,
            ),
            "artifact_count": len(evidence_refs),
        },
        trace_payload={
            "externalized_text_artifacts": large_text_artifacts,
            "externalized_raw_output_artifacts": raw_output_artifacts,
        },
    )


def _merge_tool_result_envelopes(
    existing: Any,
    artifact_envelope: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(existing, Mapping) or not existing:
        return dict(artifact_envelope)
    merged = dict(existing)
    artifact_payload = dict(artifact_envelope)
    for key in (
        "artifact_refs",
        "evidence_refs",
        "warnings",
    ):
        merged[key] = _merged_json_list(merged.get(key), artifact_payload.get(key))
    artifact_read_handles = _json_list(artifact_payload.get("read_handles"))
    if artifact_read_handles:
        merged["read_handles"] = artifact_read_handles
    else:
        merged["read_handles"] = _merged_json_list(
            merged.get("read_handles"),
            artifact_payload.get("read_handles"),
        )
    for key in ("output_payload", "key_facts", "trace_payload"):
        merged[key] = _merged_json_mapping(
            merged.get(key),
            artifact_payload.get(key),
        )
    merged["provider_replay_payload"] = _merged_provider_replay_payload(
        merged.get("provider_replay_payload"),
        artifact_payload.get("provider_replay_payload"),
    )
    merged["user_summary_payload"] = _merged_json_mapping(
        merged.get("user_summary_payload"),
        artifact_payload.get("user_summary_payload"),
    )
    merged["omitted_count"] = int(merged.get("omitted_count") or 0) + int(
        artifact_payload.get("omitted_count") or 0,
    )
    merged["omitted_chars"] = int(merged.get("omitted_chars") or 0) + int(
        artifact_payload.get("omitted_chars") or 0,
    )
    merged["truncated"] = bool(merged.get("truncated")) or bool(
        artifact_payload.get("truncated"),
    )
    artifact_summary = artifact_payload.get("summary")
    if isinstance(artifact_summary, str) and artifact_summary.strip():
        warnings = _merged_json_list(
            merged.get("warnings"),
            [artifact_summary.strip()],
        )
        if warnings:
            merged["warnings"] = warnings
    return {
        key: value
        for key, value in merged.items()
        if value not in (None, {}, [], ())
    }


def _merged_json_mapping(first: Any, second: Any) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    if isinstance(first, Mapping):
        merged.update(dict(first))
    if isinstance(second, Mapping):
        merged.update(dict(second))
    return merged


def _merged_provider_replay_payload(first: Any, second: Any) -> dict[str, Any]:
    merged = _merged_json_mapping(first, second)
    if isinstance(first, Mapping) and "summary" in first:
        merged["summary"] = first["summary"]
    read_handles = _merged_json_list(
        first.get("read_handles") if isinstance(first, Mapping) else None,
        second.get("read_handles") if isinstance(second, Mapping) else None,
    )
    second_read_handles = (
        _json_list(second.get("read_handles")) if isinstance(second, Mapping) else []
    )
    if second_read_handles:
        read_handles = second_read_handles
    if read_handles:
        merged["read_handles"] = read_handles
    artifact_refs = _merged_json_list(
        first.get("artifact_refs") if isinstance(first, Mapping) else None,
        second.get("artifact_refs") if isinstance(second, Mapping) else None,
    )
    if artifact_refs:
        merged["artifact_refs"] = artifact_refs
    return merged


def _merged_json_list(first: Any, second: Any) -> list[Any]:
    merged: list[Any] = []
    seen: set[str] = set()
    for value in (*_json_list(first), *_json_list(second)):
        marker = json.dumps(value, ensure_ascii=True, sort_keys=True)
        if marker in seen:
            continue
        seen.add(marker)
        merged.append(value)
    return merged


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return list(value)
    return []


def _artifact_result_summary(
    *,
    large_text_artifacts: list[dict[str, Any]],
    raw_output_artifacts: list[dict[str, Any]],
) -> str:
    if large_text_artifacts and raw_output_artifacts:
        return "Tool result text and raw output were externalized to artifact refs."
    if raw_output_artifacts:
        return "Tool raw output was externalized to artifact refs."
    return "Large text tool result was externalized to artifact refs."


def _execution_context_with_provider_backend(
    execution_context: ToolExecutionContext | None,
    provider_backend_payload: Mapping[str, Any] | None,
) -> ToolExecutionContext | None:
    payload = provider_backend_execution_context_payload(
        execution_context.to_payload() if execution_context is not None else None,
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


def _exception_payload(exc: Exception) -> dict[str, Any] | None:
    to_payload = getattr(exc, "to_payload", None)
    if not callable(to_payload):
        return None
    try:
        payload = to_payload()
    except Exception:  # noqa: BLE001
        return None
    return dict(payload) if isinstance(payload, Mapping) else None


def _safe_error_detail(value: Any) -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, Mapping):
        return {str(key): _safe_error_detail(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_safe_error_detail(item) for item in value]
    return str(value)
