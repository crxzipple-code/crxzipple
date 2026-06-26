from __future__ import annotations

import asyncio
from collections.abc import Callable
from logging import Logger
from threading import Event as ThreadEvent
from typing import Any

from crxzipple.modules.tool.application.dispatch_events import ToolRuntimeEventService
from crxzipple.modules.tool.application.ports import ToolEventWaitPort
from crxzipple.modules.tool.domain.entities import ToolRun


async def run_worker_until_stopped_async(
    *,
    worker_id: str,
    poll_interval_seconds: float,
    max_runs: int | None,
    max_idle_cycles: int | None,
    stop_event: ThreadEvent,
    events_service: ToolEventWaitPort | None,
    runtime_event_service: ToolRuntimeEventService | None,
    max_in_flight: int,
    register_worker: Callable[..., Any],
    mark_worker_stale: Callable[..., Any],
    launch_assignments: Callable[..., Any],
    reap_inflight_tasks: Callable[..., Any],
    heartbeat_inflight_loop: Callable[..., Any],
    wait_for_worker_wakeup: Callable[..., Any],
    logger: Logger,
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
        heartbeat_inflight_loop(
            worker_id=worker_id,
            stop_event=stop_event,
            inflight_tasks=inflight_tasks,
        ),
    )

    try:
        await asyncio.to_thread(
            register_worker,
            worker_id=worker_id,
            max_in_flight=max_in_flight,
        )
        while True:
            if runtime_event_service is not None:
                await asyncio.to_thread(runtime_event_service.process_available_events)
            await asyncio.to_thread(
                register_worker,
                worker_id=worker_id,
                max_in_flight=max_in_flight,
            )

            processed_runs += await reap_inflight_tasks(inflight_tasks)

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
                launched = await launch_assignments(
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
                    processed_runs += await reap_inflight_tasks(inflight_tasks)
                continue

            if launched:
                continue

            idle_cycles += 1
            if max_idle_cycles is not None and idle_cycles >= max_idle_cycles:
                break
            await asyncio.to_thread(
                wait_for_worker_wakeup,
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
            await reap_inflight_tasks(inflight_tasks)
        await asyncio.to_thread(mark_worker_stale, worker_id=worker_id)

    return processed_runs
