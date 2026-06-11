from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

from crxzipple.modules.orchestration.application.coordinators import (
    RunIntakeCoordinator,
)
from crxzipple.modules.orchestration.application.lane import session_lane_key
from crxzipple.modules.orchestration.application.ports import OrchestrationDispatchPort
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
    prompt_flow_hint_factory: Callable[
        ["PrepareSessionRunInput", ResolvedSessionBundle],
        dict[str, object] | None,
    ]

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
        route_metadata = dict(data.metadata)
        route_metadata["session_key"] = bundle.routing.key_resolution.key
        route_metadata["session_kind"] = bundle.routing.key_resolution.kind.value
        requested_llm_id = self._requested_llm_id(data)
        if requested_llm_id is not None:
            route_metadata["requested_llm_id"] = requested_llm_id
        return PreparedSessionRunPlan(
            agent_id=data.context.agent_id,
            lane_key=session_lane_key(bundle.routing.key_resolution.key),
            active_session_id=bundle.active_instance.id,
            priority=data.priority,
            route_metadata=route_metadata,
            prompt_flow_hint=self.prompt_flow_hint_factory(data, bundle),
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


def prompt_flow_hint_from_input(
    data: "PrepareSessionRunInput",
    bundle: ResolvedSessionBundle,
) -> dict[str, object] | None:
    payload: dict[str, object] = {}
    session_start_hint = session_start_prompt_flow_hint(bundle)
    if session_start_hint is not None:
        payload.update(session_start_hint)
    explicit_hint = _metadata_dict(data.metadata.get("prompt_flow_hint"))
    if explicit_hint:
        payload.update(explicit_hint)
    prompt_bootstrap = _prompt_bootstrap_policy(data.metadata)
    if prompt_bootstrap:
        payload.update(prompt_bootstrap)
    return payload or None


def _prompt_bootstrap_policy(metadata: dict[str, object]) -> dict[str, object]:
    policy = _metadata_dict(metadata.get("prompt_bootstrap_policy"))
    runtime_policy = _metadata_dict(metadata.get("runtime_task_policy"))
    runtime_prompt_bootstrap = _metadata_dict(runtime_policy.get("prompt_bootstrap"))
    if runtime_prompt_bootstrap:
        policy = {**runtime_prompt_bootstrap, **policy}
    payload: dict[str, object] = {}
    default_schema_ids = _metadata_string_list(policy.get("default_tool_schema_ids"))
    if default_schema_ids:
        payload["default_tool_schema_ids"] = default_schema_ids
    default_schema_source = _metadata_text(policy.get("default_tool_schema_source"))
    if default_schema_source is not None:
        payload["default_tool_schema_source"] = default_schema_source
    group_refs = _metadata_tool_schema_group_refs(
        policy.get("default_tool_schema_group_refs")
        or policy.get("tool_schema_group_refs"),
    )
    if group_refs:
        payload["default_tool_schema_group_refs"] = [dict(ref) for ref in group_refs]
    if payload and "default_tool_schema_source" not in payload:
        payload["default_tool_schema_source"] = "prompt_bootstrap_policy"
    return payload


def _metadata_dict(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, dict) else {}


def _metadata_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _metadata_string_list(value: object) -> list[str]:
    if isinstance(value, str):
        candidates: tuple[object, ...] = (value,)
    elif isinstance(value, (list, tuple, set, frozenset)):
        candidates = tuple(value)
    else:
        return []
    items: list[str] = []
    for item in candidates:
        if not isinstance(item, str):
            continue
        normalized = item.strip()
        if normalized and normalized not in items:
            items.append(normalized)
    return items


def _metadata_tool_schema_group_refs(value: object) -> list[dict[str, str]]:
    if isinstance(value, dict):
        candidates: tuple[object, ...] = (value,)
    elif isinstance(value, str):
        candidates = (value,)
    elif isinstance(value, (list, tuple)):
        candidates = tuple(value)
    else:
        return []
    refs: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in candidates:
        ref = _metadata_tool_schema_group_ref(item)
        if ref is None:
            continue
        key = (
            ref.get("node_id", ""),
            ref.get("source_id", ""),
            ref.get("group_key", ""),
        )
        if key in seen:
            continue
        seen.add(key)
        refs.append(ref)
    return refs


def _metadata_tool_schema_group_ref(value: object) -> dict[str, str] | None:
    if isinstance(value, dict):
        node_id = _metadata_text(value.get("node_id"))
        source_id = _metadata_text(value.get("source_id"))
        group_key = _metadata_text(value.get("group_key"))
        reason = _metadata_text(value.get("reason"))
        if node_id is not None:
            payload = {"node_id": node_id}
            if source_id is not None:
                payload["source_id"] = source_id
            if group_key is not None:
                payload["group_key"] = group_key
            if reason is not None:
                payload["reason"] = reason
            return payload
        if source_id is not None and group_key is not None:
            payload = {"source_id": source_id, "group_key": group_key}
            if reason is not None:
                payload["reason"] = reason
            return payload
        return None
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    if raw.startswith("tools."):
        return {"node_id": raw}
    for separator in (":", "#", "/"):
        if separator not in raw:
            continue
        source_id, group_key = raw.rsplit(separator, 1)
        source_id = source_id.strip()
        group_key = group_key.strip()
        if source_id and group_key:
            return {"source_id": source_id, "group_key": group_key}
    return None


def build_session_run_preparation_workflow(
    resolve_session_bundle: Callable[[ResolveSessionInput], ResolvedSessionBundle],
) -> SessionRunPreparationWorkflow:
    return SessionRunPreparationWorkflow(
        resolve_session_bundle=resolve_session_bundle,
        resolve_session_input_factory=lambda **kwargs: ResolveSessionInput(**kwargs),
        prompt_flow_hint_factory=prompt_flow_hint_from_input,
    )


def build_run_intake_coordinator(
    *,
    uow_factory: Callable[[], Any],
    scheduler: OrchestrationScheduler,
    dispatch_port: OrchestrationDispatchPort,
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
