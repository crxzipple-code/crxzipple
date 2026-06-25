from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
import logging
import threading

from crxzipple.modules.tool.domain.entities import ToolRun
from crxzipple.modules.tool.domain.value_objects import ToolRunStatus


@contextmanager
def heartbeat_while_processing(
    *,
    run_id: str,
    worker_id: str,
    heartbeat_seconds: float,
    heartbeat_run: Callable[[str, str], ToolRun],
    logger: logging.Logger,
) -> Iterator[None]:
    if heartbeat_seconds <= 0:
        yield
        return
    stop_event = threading.Event()

    def _run_heartbeat_loop() -> None:
        while not stop_event.wait(heartbeat_seconds):
            try:
                run = heartbeat_run(run_id, worker_id)
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
        heartbeat_thread.join(timeout=max(heartbeat_seconds * 2, 0.2))


__all__ = ["heartbeat_while_processing"]
