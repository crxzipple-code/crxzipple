from __future__ import annotations

from crxzipple.modules.dispatch.domain import DispatchTask, DispatchTaskStatus
from crxzipple.modules.orchestration.domain import OrchestrationIngressRequest
from crxzipple.modules.orchestration.domain.value_objects import OrchestrationIngressStatus


def pending_ingress_requests(
    requests: list[OrchestrationIngressRequest],
    *,
    dispatch_task_by_request_id: dict[str, DispatchTask] | None = None,
) -> list[OrchestrationIngressRequest]:
    dispatch_task_by_request_id = dispatch_task_by_request_id or {}
    result: list[OrchestrationIngressRequest] = []
    for request in requests:
        dispatch_task = dispatch_task_by_request_id.get(request.id)
        if dispatch_task is not None:
            if is_active_dispatch_status(dispatch_task.status):
                result.append(request)
            continue
        if request.status in {
            OrchestrationIngressStatus.QUEUED,
            OrchestrationIngressStatus.PROCESSING,
        }:
            result.append(request)
    return result


def is_active_dispatch_status(status: DispatchTaskStatus) -> bool:
    return status in {
        DispatchTaskStatus.CREATED,
        DispatchTaskStatus.QUEUED,
        DispatchTaskStatus.WAITING,
        DispatchTaskStatus.CLAIMED,
    }
