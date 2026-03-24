from __future__ import annotations

from threading import Event
import time

from crxzipple.core.logger import get_logger
from crxzipple.modules.orchestration.application import OrchestrationApplicationService
from crxzipple.modules.tool.application import ToolApplicationService

logger = get_logger(__name__)


def run_orchestration_worker_loop(
    orchestration_service: OrchestrationApplicationService,
    *,
    worker_id: str,
    poll_interval_seconds: float,
    max_runs: int | None = None,
    max_idle_cycles: int | None = None,
    stop_event: Event | None = None,
) -> int:
    processed_runs = 0
    idle_cycles = 0
    stopper = stop_event or Event()

    logger.info(
        "orchestration worker started",
        extra={
            "poll_interval_seconds": poll_interval_seconds,
            "max_runs": max_runs,
            "max_idle_cycles": max_idle_cycles,
            "worker_id": worker_id,
        },
    )

    while not stopper.is_set():
        run = orchestration_service.process_next_queued_run(worker_id=worker_id)
        if run is None:
            idle_cycles += 1
            if max_idle_cycles is not None and idle_cycles >= max_idle_cycles:
                logger.info(
                    "orchestration worker exiting after idle limit",
                    extra={
                        "idle_cycles": idle_cycles,
                        "worker_id": worker_id,
                    },
                )
                break
            stopper.wait(poll_interval_seconds)
            continue

        idle_cycles = 0
        processed_runs += 1
        logger.info(
            "orchestration worker processed queued run",
            extra={
                "run_id": run.id,
                "processed_runs": processed_runs,
                "worker_id": worker_id,
            },
        )
        if max_runs is not None and processed_runs >= max_runs:
            logger.info(
                "orchestration worker exiting after processed run limit",
                extra={
                    "processed_runs": processed_runs,
                    "worker_id": worker_id,
                },
            )
            break

    return processed_runs


def run_tool_worker_loop(
    tool_service: ToolApplicationService,
    *,
    worker_id: str,
    poll_interval_seconds: float,
    max_runs: int | None = None,
    max_idle_cycles: int | None = None,
    stop_event: Event | None = None,
) -> int:
    processed_runs = 0
    idle_cycles = 0
    stopper = stop_event or Event()

    logger.info(
        "tool worker started",
        extra={
            "poll_interval_seconds": poll_interval_seconds,
            "max_runs": max_runs,
            "max_idle_cycles": max_idle_cycles,
            "worker_id": worker_id,
        },
    )

    while not stopper.is_set():
        tool_run = tool_service.process_next_queued_run(worker_id=worker_id)
        if tool_run is None:
            idle_cycles += 1
            if max_idle_cycles is not None and idle_cycles >= max_idle_cycles:
                logger.info(
                    "tool worker exiting after idle limit",
                    extra={
                        "idle_cycles": idle_cycles,
                        "worker_id": worker_id,
                    },
                )
                break
            stopper.wait(poll_interval_seconds)
            continue

        idle_cycles = 0
        processed_runs += 1
        logger.info(
            "tool worker processed queued run",
            extra={
                "run_id": tool_run.id,
                "processed_runs": processed_runs,
                "worker_id": worker_id,
            },
        )
        if max_runs is not None and processed_runs >= max_runs:
            logger.info(
                "tool worker exiting after processed run limit",
                extra={
                    "processed_runs": processed_runs,
                    "worker_id": worker_id,
                },
            )
            break

    return processed_runs
