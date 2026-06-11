from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from crxzipple.core.logger import get_logger
from crxzipple.modules.orchestration.application.cancellation import (
    fail_run_record,
)
from crxzipple.modules.orchestration.application.lane import (
    session_lane_key,
)
from crxzipple.modules.orchestration.domain import (
    OrchestrationBoundSessionTarget,
    OrchestrationIngressRequest,
    OrchestrationIngressRequestKind,
    OrchestrationRun,
)
from crxzipple.modules.orchestration.domain.exceptions import (
    OrchestrationValidationError,
)
from crxzipple.modules.session.domain import (
    DirectSessionScope,
    SessionResetPolicy,
    SessionRouteContext,
)

if TYPE_CHECKING:
    from crxzipple.modules.orchestration.application.commands import (
        FailAssignmentInput,
    )
    from crxzipple.modules.orchestration.application.coordinators import (
        RunIngressCoordinator,
    )
    from crxzipple.modules.orchestration.application.ports import OrchestrationDispatchPort
    from crxzipple.modules.orchestration.application.ports.runtime import (
        OrchestrationSchedulerIntakePort,
    )

logger = get_logger(__name__)

IngressFailureHandler = Callable[
    [OrchestrationIngressRequest, str, Exception],
    None,
]


def process_ingress_request(
    request: OrchestrationIngressRequest | None,
    *,
    worker_id: str,
    ingress_coordinator: "RunIngressCoordinator",
    intake_port: "OrchestrationSchedulerIntakePort",
    fail_run: IngressFailureHandler | None = None,
    on_run_enqueued: Callable[[OrchestrationRun], None] | None = None,
) -> OrchestrationRun | None:
    if request is None:
        return None
    try:
        run = prepare_and_enqueue_ingress_request(request, intake_port=intake_port)
        ingress_coordinator.complete_request(request.id)
        if on_run_enqueued is not None:
            try:
                on_run_enqueued(run)
            except Exception:
                logger.exception(
                    "orchestration scheduler run-enqueued callback failed",
                    extra={
                        "request_kind": request.kind.value,
                        "request_id": request.id,
                        "run_id": run.id,
                    },
                )
        return run
    except Exception as exc:
        ingress_coordinator.fail_request(
            request.id,
            message=str(exc) or type(exc).__name__,
            code=_exception_code(exc, default="ingress_prepare_failed"),
            details={
                "run_id": request.run_id,
                "request_kind": request.kind.value,
                **_exception_details(exc),
            },
        )
        if fail_run is not None:
            try:
                fail_run(request, worker_id, exc)
            except Exception:
                logger.exception(
                    "failed to mark ingress-backed run as failed",
                    extra={
                        "request_kind": request.kind.value,
                        "request_id": request.id,
                        "run_id": request.run_id,
                    },
                )
        raise


def prepare_and_enqueue_ingress_request(
    request: OrchestrationIngressRequest,
    *,
    intake_port: "OrchestrationSchedulerIntakePort",
) -> OrchestrationRun:
    if request.kind is OrchestrationIngressRequestKind.ROUTED_TURN:
        prepared = intake_port.prepare_session_run(
            prepare_input_from_ingress_request(request),
        )
        return intake_port.enqueue(
            enqueue_input_from_ingress_request(request, run_id=prepared.id),
        )
    if request.kind is OrchestrationIngressRequestKind.BOUND_TURN:
        bound_target = ingress_bound_target(request)
        routed = intake_port.route(
            route_bound_request_input(
                request=request,
                bound_target=bound_target,
            ),
        )
        bound = intake_port.bind_session(
            bind_bound_request_input(
                run_id=routed.id,
                active_session_id=bound_target.active_session_id,
            ),
        )
        return intake_port.enqueue(
            enqueue_bound_request_input(
                request=request,
                bound_target=bound_target,
                run_id=bound.id,
            ),
        )
    raise OrchestrationValidationError(
        f"Unsupported orchestration ingress request kind '{request.kind.value}'.",
    )


def fail_assignment_input_from_ingress_error(
    request: OrchestrationIngressRequest,
    *,
    worker_id: str,
    exc: Exception,
) -> "FailAssignmentInput":
    from crxzipple.modules.orchestration.application.commands import (
        FailAssignmentInput,
    )

    return FailAssignmentInput(
        run_id=request.run_id,
        worker_id=worker_id,
        message=str(exc) or type(exc).__name__,
        code=_exception_code(exc, default="ingress_prepare_failed"),
        details={
            "request_id": request.id,
            **_exception_details(exc),
        },
    )


def fail_ingress_backed_run_record(
    *,
    uow_factory,
    dispatch_port: "OrchestrationDispatchPort",
    request: OrchestrationIngressRequest,
    worker_id: str,
    exc: Exception,
) -> OrchestrationRun | None:
    return fail_run_record(
        uow_factory,
        dispatch_port,
        request.run_id,
        worker_id=worker_id,
        message=str(exc) or type(exc).__name__,
        code=_exception_code(exc, default="ingress_prepare_failed"),
        details={
            "request_id": request.id,
            **_exception_details(exc),
        },
    )


def prepare_input_from_ingress_request(request: OrchestrationIngressRequest):
    from crxzipple.modules.orchestration.application.intake_commands import (
        PrepareSessionRunInput,
    )

    if request.kind is not OrchestrationIngressRequestKind.ROUTED_TURN:
        raise OrchestrationValidationError(
            f"Request '{request.id}' is not a routed-turn ingress request.",
        )
    return PrepareSessionRunInput(
        run_id=request.run_id,
        context=ingress_route_context(request),
        requested_llm_id=request.requested_llm_id,
        ensure=request.ensure_session,
        touch_activity=request.touch_activity,
        reset_policy=ingress_reset_policy(request),
        priority=request.priority,
        metadata=dict(request.prepare_metadata),
    )


def enqueue_input_from_ingress_request(
    request: OrchestrationIngressRequest,
    *,
    run_id: str,
):
    from crxzipple.modules.orchestration.application.intake_commands import (
        EnqueueOrchestrationRunInput,
    )

    return EnqueueOrchestrationRunInput(
        run_id=run_id,
        queue_policy=request.queue_policy,
        priority=request.priority,
    )


def route_bound_request_input(
    *,
    request: OrchestrationIngressRequest,
    bound_target: OrchestrationBoundSessionTarget,
):
    from crxzipple.modules.orchestration.application.intake_commands import (
        RouteOrchestrationRunInput,
    )

    return RouteOrchestrationRunInput(
        run_id=request.run_id,
        agent_id=bound_target.agent_id,
        session_key=bound_target.session_key,
        lane_key=bound_lane_key(
            session_key=bound_target.session_key,
            lane_key=bound_target.lane_key,
        ),
        priority=request.priority,
        metadata=bound_request_metadata(
            request=request,
            session_key=bound_target.session_key,
        ),
    )


def bind_bound_request_input(
    *,
    run_id: str,
    active_session_id: str,
):
    from crxzipple.modules.orchestration.application.intake_commands import (
        BindSessionInput,
    )

    return BindSessionInput(
        run_id=run_id,
        active_session_id=active_session_id,
    )


def enqueue_bound_request_input(
    *,
    request: OrchestrationIngressRequest,
    bound_target: OrchestrationBoundSessionTarget,
    run_id: str,
):
    from crxzipple.modules.orchestration.application.intake_commands import (
        EnqueueOrchestrationRunInput,
    )

    return EnqueueOrchestrationRunInput(
        run_id=run_id,
        lane_key=bound_lane_key(
            session_key=bound_target.session_key,
            lane_key=bound_target.lane_key,
        ),
        queue_policy=request.queue_policy,
        priority=request.priority,
    )


def bound_request_metadata(
    *,
    request: OrchestrationIngressRequest,
    session_key: str,
) -> dict[str, object]:
    metadata = {
        "session_key": session_key,
        **dict(request.prepare_metadata),
    }
    requested_llm_id = (
        request.requested_llm_id.strip()
        if isinstance(request.requested_llm_id, str)
        and request.requested_llm_id.strip()
        else None
    )
    if requested_llm_id is not None:
        metadata.setdefault("requested_llm_id", requested_llm_id)
    return metadata


def bound_lane_key(*, session_key: str, lane_key: str | None) -> str:
    if isinstance(lane_key, str) and lane_key.strip():
        return lane_key.strip()
    return session_lane_key(session_key)


def ingress_bound_target(
    request: OrchestrationIngressRequest,
) -> OrchestrationBoundSessionTarget:
    bound_target = request.bound_session_target
    if bound_target is None:
        raise OrchestrationValidationError(
            f"Missing bound session target for ingress request '{request.id}'.",
        )
    return bound_target


def ingress_route_context(request: OrchestrationIngressRequest) -> SessionRouteContext:
    if request.kind is not OrchestrationIngressRequestKind.ROUTED_TURN:
        raise OrchestrationValidationError(
            f"Request '{request.id}' does not carry a route context.",
        )
    payload = dict(request.route_context_payload)
    direct_scope = payload.get("direct_scope")
    if direct_scope is not None:
        payload["direct_scope"] = (
            direct_scope
            if isinstance(direct_scope, DirectSessionScope)
            else DirectSessionScope(str(direct_scope))
        )
    metadata = payload.get("metadata")
    if not isinstance(metadata, dict):
        payload["metadata"] = {}
    try:
        return SessionRouteContext(**payload)
    except Exception as exc:
        raise OrchestrationValidationError(
            f"Invalid orchestration ingress route context for request '{request.id}'.",
        ) from exc


def ingress_reset_policy(
    request: OrchestrationIngressRequest,
) -> SessionResetPolicy | None:
    payload = request.reset_policy_payload
    if not payload:
        return None
    return SessionResetPolicy(
        idle_minutes=(
            int(payload["idle_minutes"])
            if payload.get("idle_minutes") is not None
            else None
        ),
        daily_reset_hour_utc=(
            int(payload["daily_reset_hour_utc"])
            if payload.get("daily_reset_hour_utc") is not None
            else None
        ),
    )


def _exception_code(exc: Exception, *, default: str) -> str:
    code = getattr(exc, "code", None)
    if isinstance(code, str) and code.strip():
        return code.strip()
    return default


def _exception_details(exc: Exception) -> dict[str, object]:
    details = getattr(exc, "details", None)
    if isinstance(details, dict):
        return dict(details)
    return {}


__all__ = [
    "bind_bound_request_input",
    "bound_lane_key",
    "bound_request_metadata",
    "enqueue_bound_request_input",
    "enqueue_input_from_ingress_request",
    "fail_assignment_input_from_ingress_error",
    "fail_ingress_backed_run_record",
    "ingress_bound_target",
    "ingress_reset_policy",
    "ingress_route_context",
    "prepare_and_enqueue_ingress_request",
    "prepare_input_from_ingress_request",
    "process_ingress_request",
    "route_bound_request_input",
]
