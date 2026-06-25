from __future__ import annotations

from crxzipple.modules.dispatch.domain import DispatchTask
from crxzipple.modules.operations.application.read_models.orchestration_ingress_row_values import (
    display,
)
from crxzipple.modules.orchestration.domain import (
    OrchestrationIngressRequest,
    OrchestrationRun,
)


def ingress_source(
    request: OrchestrationIngressRequest,
    run: OrchestrationRun | None,
) -> str:
    if run is not None:
        return run.inbound_instruction.source
    route_context = request.route_context_payload
    for key in ("surface", "channel", "source"):
        value = route_context.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return request.kind.value


def ingress_target_lane(
    request: OrchestrationIngressRequest,
    run: OrchestrationRun | None,
) -> str:
    if run is not None:
        return display(run.lane_key)
    bound_target = request.bound_session_target
    if bound_target is not None and bound_target.lane_key:
        return bound_target.lane_key
    value = request.route_context_payload.get("main_key")
    return display(value)


def ingress_priority(
    request: OrchestrationIngressRequest,
    run: OrchestrationRun | None,
    *,
    dispatch_task: DispatchTask | None = None,
) -> str:
    if dispatch_task is not None:
        return f"P{dispatch_task.priority}"
    if request.priority is not None:
        return f"P{request.priority}"
    if run is not None:
        return f"P{run.priority}"
    return "-"
