from __future__ import annotations

from typing import Any

from crxzipple.modules.dispatch.domain import DispatchTask, DispatchTaskStatus
from crxzipple.modules.orchestration.application.coordinators.continuation_tasks import (
    OrchestrationContinuationTask,
)
from crxzipple.modules.orchestration.domain import (
    OrchestrationIngressRequest,
    OrchestrationRun,
)
from crxzipple.modules.orchestration.domain.value_objects import (
    OrchestrationRunStatus,
)
from crxzipple.modules.operations.application.observation_models import OperationsObservedEvent


def list_ingress_requests(query: Any | None) -> list[OrchestrationIngressRequest]:
    if query is None:
        return []
    return query.list_ingress_requests(status=None)


def list_continuation_tasks(query: Any | None) -> list[OrchestrationContinuationTask]:
    if query is None:
        return []
    return query.list_continuation_tasks(status=None)


def list_dispatch_tasks(query: Any | None) -> list[DispatchTask]:
    if query is None:
        return []
    return query.list_dispatch_tasks(status=None)


def dispatch_tasks_by_owner(
    tasks: list[DispatchTask],
    *,
    owner_kind: str,
) -> dict[str, DispatchTask]:
    result: dict[str, DispatchTask] = {}
    for task in tasks:
        if task.owner_kind != owner_kind:
            continue
        previous = result.get(task.owner_id)
        if previous is None or task.updated_at > previous.updated_at:
            result[task.owner_id] = task
    return result


def dispatch_tasks_by_payload_ref(
    tasks: list[DispatchTask],
    *,
    owner_kind: str,
) -> dict[str, DispatchTask]:
    result: dict[str, DispatchTask] = {}
    for task in tasks:
        if task.owner_kind != owner_kind:
            continue
        if task.payload_ref is None or not task.payload_ref.strip():
            continue
        payload_ref = task.payload_ref.strip()
        previous = result.get(payload_ref)
        if previous is None or task.updated_at > previous.updated_at:
            result[payload_ref] = task
    return result


def run_is_dispatch_queued(
    run: OrchestrationRun,
    dispatch_task: DispatchTask | None,
) -> bool:
    if dispatch_task is not None:
        return dispatch_task.status in {
            DispatchTaskStatus.QUEUED,
            DispatchTaskStatus.WAITING,
        }
    return run.status is OrchestrationRunStatus.QUEUED


def recent_operations_events(
    *,
    observation: Any | None,
    module: str,
    limit: int,
) -> tuple[OperationsObservedEvent, ...]:
    if observation is None:
        return ()
    try:
        module_observation = observation.get_module_observation(module)
    except Exception:
        return ()
    if module_observation is None:
        return ()
    recent_events = getattr(module_observation, "recent_events", ())
    return tuple(
        event
        for event in tuple(recent_events)[: max(int(limit), 1)]
        if isinstance(event, OperationsObservedEvent)
    )


def module_observation(
    observation: Any | None,
    *,
    module: str,
) -> Any | None:
    if observation is None:
        return None
    try:
        return observation.get_module_observation(module)
    except Exception:
        return None
