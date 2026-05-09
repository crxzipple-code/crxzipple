from __future__ import annotations

from collections.abc import Callable
from threading import Event
from typing import Protocol

from crxzipple.core.logger import get_logger
from crxzipple.modules.daemon.application import DaemonManager
from crxzipple.modules.events import EventsApplicationService
from crxzipple.modules.orchestration.application import (
    OrchestrationExecutorService,
    OrchestrationSchedulerService,
)
from crxzipple.modules.tool.application import ToolRuntimeEventService

logger = get_logger(__name__)


class ToolQueuedRunWorkerPort(Protocol):
    def run_until_stopped(
        self,
        *,
        worker_id: str,
        poll_interval_seconds: float,
        max_runs: int | None = None,
        max_idle_cycles: int | None = None,
        stop_event: Event | None = None,
        events_service: EventsApplicationService | None = None,
        runtime_event_service: ToolRuntimeEventService | None = None,
        max_in_flight: int = 1,
    ) -> int:
        ...


class ToolSchedulerRuntimePort(Protocol):
    def run_until_stopped(
        self,
        *,
        poll_interval_seconds: float,
        max_runs: int | None = None,
        max_idle_cycles: int | None = None,
        stop_event: Event | None = None,
        events_service: EventsApplicationService | None = None,
    ) -> int:
        ...


def _wait_for_event_topic_wakeup(
    *,
    fetch_next,
    events_service: EventsApplicationService | None,
    wakeup_topic: str | None,
    stopper: Event,
    timeout_seconds: float,
):
    if events_service is None or not wakeup_topic:
        stopper.wait(timeout_seconds)
        return None
    cursor = events_service.snapshot_event_topic(wakeup_topic)
    candidate = fetch_next()
    if candidate is not None or stopper.is_set():
        return candidate
    events_service.wait_for_event_topic(
        wakeup_topic,
        after_cursor=cursor,
        timeout_seconds=timeout_seconds,
        stop_event=stopper,
    )
    return None


def run_orchestration_executor_loop(
    executor_service: OrchestrationExecutorService,
    *,
    worker_id: str,
    poll_interval_seconds: float,
    max_runs: int | None = None,
    max_idle_cycles: int | None = None,
    stop_event: Event | None = None,
    events_service: EventsApplicationService | None = None,
) -> int:
    """Thin process-host adapter for the executor service-owned runtime loop."""
    del events_service
    return executor_service.run_until_stopped(
        worker_id=worker_id,
        poll_interval_seconds=poll_interval_seconds,
        max_runs=max_runs,
        max_idle_cycles=max_idle_cycles,
        stop_event=stop_event,
    )


def run_orchestration_scheduler_loop(
    scheduler_service: OrchestrationSchedulerService,
    *,
    worker_id: str,
    poll_interval_seconds: float,
    max_runs: int | None = None,
    max_idle_cycles: int | None = None,
    stop_event: Event | None = None,
    events_service: EventsApplicationService | None = None,
) -> int:
    """Thin process-host adapter for the scheduler service-owned runtime loop."""
    del events_service
    return scheduler_service.run_until_stopped(
        worker_id=worker_id,
        poll_interval_seconds=poll_interval_seconds,
        max_runs=max_runs,
        max_idle_cycles=max_idle_cycles,
        stop_event=stop_event,
    )


def run_tool_worker_loop(
    tool_worker_service: ToolQueuedRunWorkerPort,
    *,
    worker_id: str,
    poll_interval_seconds: float,
    max_runs: int | None = None,
    max_idle_cycles: int | None = None,
    stop_event: Event | None = None,
    events_service: EventsApplicationService | None = None,
    runtime_event_service: ToolRuntimeEventService | None = None,
    max_in_flight: int = 1,
) -> int:
    return tool_worker_service.run_until_stopped(
        worker_id=worker_id,
        poll_interval_seconds=poll_interval_seconds,
        max_runs=max_runs,
        max_idle_cycles=max_idle_cycles,
        stop_event=stop_event,
        events_service=events_service,
        runtime_event_service=runtime_event_service,
        max_in_flight=max_in_flight,
    )


def run_tool_scheduler_loop(
    scheduler_service: ToolSchedulerRuntimePort,
    *,
    poll_interval_seconds: float,
    max_runs: int | None = None,
    max_idle_cycles: int | None = None,
    stop_event: Event | None = None,
    events_service: EventsApplicationService | None = None,
) -> int:
    return scheduler_service.run_until_stopped(
        poll_interval_seconds=poll_interval_seconds,
        max_runs=max_runs,
        max_idle_cycles=max_idle_cycles,
        stop_event=stop_event,
        events_service=events_service,
    )


def run_daemon_supervisor_loop(
    daemon_manager: DaemonManager,
    *,
    poll_interval_seconds: float,
    service_set_keys: tuple[str, ...] = (),
    service_keys: tuple[str, ...] = (),
    service_roles: tuple[str, ...] = (),
    service_groups: tuple[str, ...] = (),
    include_eager: bool = True,
    max_cycles: int | None = None,
    stop_event: Event | None = None,
    before_cycle: Callable[[], object] | None = None,
) -> int:
    completed_cycles = 0
    stopper = stop_event or Event()

    logger.info(
        "daemon supervisor started",
        extra={
            "poll_interval_seconds": poll_interval_seconds,
            "service_set_keys": list(service_set_keys),
            "service_keys": list(service_keys),
            "service_roles": list(service_roles),
            "service_groups": list(service_groups),
            "include_eager": include_eager,
            "max_cycles": max_cycles,
        },
    )

    while not stopper.is_set():
        if before_cycle is not None:
            before_cycle()
        instances = []
        selected_service_keys = daemon_manager.resolve_reconcile_service_keys(
            service_set_keys=service_set_keys,
            service_keys=service_keys,
            service_roles=service_roles,
            service_groups=service_groups,
            include_eager=include_eager,
        )
        for service_key in selected_service_keys:
            instances.extend(daemon_manager.reconcile_service(service_key))
        completed_cycles += 1
        logger.info(
            "daemon supervisor reconciled eager services",
            extra={
                "completed_cycles": completed_cycles,
                "instance_count": len(instances),
                "service_set_keys": list(service_set_keys),
                "service_keys": list(selected_service_keys),
                "service_roles": list(service_roles),
                "service_groups": list(service_groups),
                "include_eager": include_eager,
            },
        )
        if max_cycles is not None and completed_cycles >= max_cycles:
            logger.info(
                "daemon supervisor exiting after cycle limit",
                extra={"completed_cycles": completed_cycles},
            )
            break
        stopper.wait(poll_interval_seconds)

    return completed_cycles
