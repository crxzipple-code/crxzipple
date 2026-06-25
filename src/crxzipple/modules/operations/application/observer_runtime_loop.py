from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from threading import Event as StopEvent

from crxzipple.core.logger import get_logger

logger = get_logger(__name__)


def run_observer_until_stopped(
    *,
    runtime_name: str,
    worker_id: str,
    poll_interval_seconds: float,
    process_available_events: Callable[..., int],
    record_heartbeat: Callable[..., None],
    run_maintenance: Callable[[], None],
    wait_for_events: Callable[..., None],
    max_events: int | None = None,
    max_idle_cycles: int | None = None,
    limit_per_subscription: int = 100,
    stop_event: StopEvent | None = None,
) -> int:
    processed_events = 0
    idle_cycles = 0
    stopper = stop_event or StopEvent()
    started_at = datetime.now(timezone.utc)
    final_status = "stopped"

    logger.info(
        "operations observer runtime started",
        extra={
            "runtime_name": runtime_name,
            "poll_interval_seconds": poll_interval_seconds,
            "max_events": max_events,
            "max_idle_cycles": max_idle_cycles,
            "worker_id": worker_id,
        },
    )
    record_heartbeat(
        worker_id=worker_id,
        status="running",
        started_at=started_at,
        processed_events=processed_events,
        idle_cycles=idle_cycles,
        poll_interval_seconds=poll_interval_seconds,
        limit_per_subscription=limit_per_subscription,
    )

    try:
        while not stopper.is_set():
            processed = process_available_events(
                limit_per_subscription=limit_per_subscription,
                event_driven=True,
            )
            if processed <= 0:
                idle_cycles += 1
                record_heartbeat(
                    worker_id=worker_id,
                    status="idle",
                    started_at=started_at,
                    processed_events=processed_events,
                    idle_cycles=idle_cycles,
                    poll_interval_seconds=poll_interval_seconds,
                    limit_per_subscription=limit_per_subscription,
                )
                run_maintenance()
                if max_idle_cycles is not None and idle_cycles >= max_idle_cycles:
                    break
                wait_for_events(
                    timeout_seconds=poll_interval_seconds,
                    stop_event=stopper,
                )
                continue

            idle_cycles = 0
            processed_events += processed
            record_heartbeat(
                worker_id=worker_id,
                status="running",
                started_at=started_at,
                processed_events=processed_events,
                idle_cycles=idle_cycles,
                poll_interval_seconds=poll_interval_seconds,
                limit_per_subscription=limit_per_subscription,
            )
            run_maintenance()
            if max_events is not None and processed_events >= max_events:
                break
    except Exception:
        final_status = "failed"
        raise
    finally:
        record_heartbeat(
            worker_id=worker_id,
            status=final_status,
            started_at=started_at,
            processed_events=processed_events,
            idle_cycles=idle_cycles,
            poll_interval_seconds=poll_interval_seconds,
            limit_per_subscription=limit_per_subscription,
        )

    logger.info(
        "operations observer runtime stopped",
        extra={
            "runtime_name": runtime_name,
            "processed_events": processed_events,
            "worker_id": worker_id,
        },
    )
    return processed_events
