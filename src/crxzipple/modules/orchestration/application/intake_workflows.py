from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

from crxzipple.modules.orchestration.application.coordinators import (
    RunIntakeCoordinator,
)
from crxzipple.modules.orchestration.application.lane import session_lane_key
from crxzipple.modules.orchestration.application.ports import RunDispatchPort
from crxzipple.modules.orchestration.application.scheduler import (
    OrchestrationScheduler,
)
from crxzipple.modules.orchestration.domain.exceptions import (
    OrchestrationValidationError,
)
from crxzipple.modules.session.application import (
    ResolveSessionInput,
    ResolvedSessionBundle,
)

if TYPE_CHECKING:
    from crxzipple.modules.orchestration.application.intake_commands import (
        PrepareSessionRunInput,
    )


@dataclass(frozen=True, slots=True)
class PreparedSessionRunPlan:
    agent_id: str
    lane_key: str
    active_session_id: str
    priority: int | None
    route_metadata: dict[str, object]
    prompt_flow_hint: dict[str, object] | None = None


@dataclass(slots=True)
class SessionRunPreparationWorkflow:
    resolve_session_bundle: Callable[[ResolveSessionInput], ResolvedSessionBundle]
    resolve_session_input_factory: Callable[..., ResolveSessionInput]
    session_start_prompt_flow_hint: Callable[[ResolvedSessionBundle], dict[str, object] | None]

    def plan(self, data: "PrepareSessionRunInput") -> PreparedSessionRunPlan:
        bundle = self.resolve_session_bundle(
            self.resolve_session_input_factory(
                context=data.context,
                ensure=data.ensure,
                touch_activity=data.touch_activity,
                reset_policy=data.reset_policy,
                now=data.now,
            ),
        )
        if bundle.session is None or bundle.active_instance is None:
            raise OrchestrationValidationError(
                "Session resolution did not produce an active session to bind.",
            )
        route_metadata = {
            "session_key": bundle.routing.key_resolution.key,
            "session_kind": bundle.routing.key_resolution.kind.value,
        }
        requested_llm_id = self._requested_llm_id(data)
        if requested_llm_id is not None:
            route_metadata.setdefault("requested_llm_id", requested_llm_id)
        route_metadata.update(data.metadata)
        return PreparedSessionRunPlan(
            agent_id=data.context.agent_id,
            lane_key=session_lane_key(bundle.routing.key_resolution.key),
            active_session_id=bundle.active_instance.id,
            priority=data.priority,
            route_metadata=route_metadata,
            prompt_flow_hint=self.session_start_prompt_flow_hint(bundle),
        )

    @staticmethod
    def _requested_llm_id(data: "PrepareSessionRunInput") -> str | None:
        if not isinstance(data.requested_llm_id, str):
            return None
        value = data.requested_llm_id.strip()
        return value or None


def session_start_prompt_flow_hint(
    bundle: ResolvedSessionBundle,
) -> dict[str, object] | None:
    resolution = bundle.resolution.resolution
    if resolution.created:
        return {
            "mode": "session_start",
            "event": "created",
            "session_kind": resolution.kind.value,
        }
    if resolution.reset:
        payload: dict[str, object] = {
            "mode": "session_start",
            "event": "reset",
            "session_kind": resolution.kind.value,
        }
        if resolution.reset_reason is not None and resolution.reset_reason.strip():
            payload["reason"] = resolution.reset_reason.strip()
        return payload
    return None


def build_session_run_preparation_workflow(
    resolve_session_bundle: Callable[[ResolveSessionInput], ResolvedSessionBundle],
) -> SessionRunPreparationWorkflow:
    return SessionRunPreparationWorkflow(
        resolve_session_bundle=resolve_session_bundle,
        resolve_session_input_factory=lambda **kwargs: ResolveSessionInput(**kwargs),
        session_start_prompt_flow_hint=session_start_prompt_flow_hint,
    )


def build_run_intake_coordinator(
    *,
    uow_factory: Callable[[], Any],
    scheduler: OrchestrationScheduler,
    dispatch_port: RunDispatchPort,
    resolve_session_bundle: Callable[[ResolveSessionInput], ResolvedSessionBundle],
) -> RunIntakeCoordinator:
    session_run_preparation = build_session_run_preparation_workflow(
        resolve_session_bundle,
    )
    return RunIntakeCoordinator(
        uow_factory=uow_factory,
        scheduler=scheduler,
        dispatch_port=dispatch_port,
        plan_prepared_session_run=session_run_preparation.plan,
    )
