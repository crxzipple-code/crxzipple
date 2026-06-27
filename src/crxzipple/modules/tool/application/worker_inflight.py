from __future__ import annotations

import asyncio
from collections import Counter
from threading import Event as ThreadEvent
from typing import Any, Awaitable, Callable

from crxzipple.modules.tool.application.concurrency import ToolRunConcurrencyPolicy
from crxzipple.modules.tool.application.worker_assignment_selection import (
    select_runnable_assignment_run_ids,
)
from crxzipple.modules.tool.application.worker_errors import (
    exception_message,
)
from crxzipple.modules.tool.domain.entities import Tool, ToolRun
from crxzipple.modules.tool.domain.value_objects import ToolRunAssignmentStatus


async def launch_assignments(
    *,
    worker_id: str,
    inflight_tasks: dict[str, asyncio.Task[ToolRun]],
    max_new_assignments: int,
    select_runnable_run_ids: Callable[[str, tuple[str, ...], int], tuple[str, ...]],
    perform_assigned_run: Callable[[str], Awaitable[ToolRun]],
) -> int:
    if max_new_assignments <= 0:
        return 0
    run_ids = await asyncio.to_thread(
        select_runnable_run_ids,
        worker_id,
        tuple(inflight_tasks.keys()),
        max_new_assignments,
    )
    launched = 0
    for run_id in run_ids:
        if launched >= max_new_assignments:
            break
        if run_id in inflight_tasks:
            continue
        inflight_tasks[run_id] = asyncio.create_task(
            perform_assigned_run(run_id),
            name=f"tool-run-{run_id}",
        )
        launched += 1
    return launched


async def reap_inflight_tasks(
    inflight_tasks: dict[str, asyncio.Task[ToolRun]],
    *,
    logger: Any,
) -> int:
    completed = 0
    for run_id, task in list(inflight_tasks.items()):
        if not task.done():
            continue
        try:
            await task
        except asyncio.CancelledError:
            logger.warning(
                "tool worker task was cancelled during reap",
                extra={"run_id": run_id},
            )
        except Exception:
            logger.exception(
                "tool worker task failed during reap",
                extra={"run_id": run_id},
            )
        finally:
            inflight_tasks.pop(run_id, None)
        completed += 1
    return completed


async def perform_assigned_run(
    *,
    run_id: str,
    perform_run: Callable[[str], Awaitable[ToolRun]],
    fail_run: Callable[[str, str], ToolRun],
    logger: Any,
) -> ToolRun:
    try:
        return await perform_run(run_id)
    except Exception as exc:
        logger.exception(
            "tool worker failed while executing assigned run",
            extra={"run_id": run_id},
        )
        return await asyncio.to_thread(
            fail_run,
            run_id,
            exception_message(exc),
        )


async def heartbeat_inflight_loop(
    *,
    worker_id: str,
    stop_event: ThreadEvent,
    inflight_tasks: dict[str, asyncio.Task[ToolRun]],
    worker_heartbeat_seconds: float,
    heartbeat_run: Callable[[str, str], ToolRun],
    logger: Any,
) -> None:
    if worker_heartbeat_seconds <= 0:
        return
    while not stop_event.is_set():
        await asyncio.sleep(worker_heartbeat_seconds)
        run_ids = tuple(inflight_tasks.keys())
        if not run_ids:
            continue
        results = await asyncio.gather(
            *(
                asyncio.to_thread(
                    heartbeat_run,
                    run_id,
                    worker_id,
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


def select_runnable_run_ids(
    *,
    uow_factory: Callable[[], Any],
    concurrency_policy: ToolRunConcurrencyPolicy,
    resolve_tool_for_run: Callable[[Any, ToolRun], Tool | None],
    worker_id: str,
    exclude_run_ids: tuple[str, ...],
    limit: int,
) -> tuple[str, ...]:
    excluded = set(exclude_run_ids)
    with uow_factory() as uow:
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
            tool = resolve_tool_for_run(uow, run)
            if tool is None:
                continue
            concurrency_policy.reserve(
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
            concurrency_policy=concurrency_policy,
            resolve_tool_for_run=lambda run: resolve_tool_for_run(uow, run),
        )
