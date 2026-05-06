from __future__ import annotations


def assign_next_background_tool_run(
    container,
    *,
    worker_id: str,
    max_in_flight: int = 1,
):
    container.tool_worker_service.register_worker(
        worker_id=worker_id,
        max_in_flight=max_in_flight,
    )
    return container.tool_scheduler_service.assign_next_available(worker_id=worker_id)


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
    return container.tool_worker_service.process_next_assigned_run(worker_id=worker_id)


__all__ = [
    "assign_next_background_tool_run",
    "process_next_background_tool_run",
]
