from __future__ import annotations

from crxzipple.interfaces.runtime_container import AppKey


def assign_next_background_tool_run(
    container,
    *,
    worker_id: str,
    max_in_flight: int = 1,
):
    tool_worker_service = container.require(AppKey.TOOL_WORKER_SERVICE)
    tool_worker_service.register_worker(
        worker_id=worker_id,
        max_in_flight=max_in_flight,
    )
    return container.require(AppKey.TOOL_SCHEDULER_SERVICE).assign_next_available(
        worker_id=worker_id,
    )


def process_next_background_tool_run(
    container,
    *,
    worker_id: str,
    max_in_flight: int = 1,
):
    assigned = assign_next_background_tool_run(
        container,
        worker_id=worker_id,
        max_in_flight=max_in_flight,
    )
    if assigned is None:
        return None
    return container.require(AppKey.TOOL_WORKER_SERVICE).process_next_assigned_run(
        worker_id=worker_id,
    )


__all__ = [
    "assign_next_background_tool_run",
    "process_next_background_tool_run",
]
