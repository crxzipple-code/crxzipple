from __future__ import annotations

from typing import Any

from crxzipple.modules.workbench.application import view_models as models
from crxzipple.shared.runtime_console import TraceContext


def linked_entity(
    *,
    entity_type: str,
    entity_id: str,
    label: str | None = None,
    owner: str | None = None,
    route: str | None = None,
    copy_value: str | None = None,
    trace: TraceContext | None = None,
):
    return models.WorkbenchLinkedEntity(
        type=entity_type,
        id=entity_id,
        label=label,
        owner=owner,
        route=route,
        copy_value=copy_value or entity_id,
        trace=trace,
    )


def runtime_action(
    *,
    action_id: str,
    label: str,
    owner: str,
    risk: str = "normal",
    allowed: bool = True,
    disabled_reason: str | None = None,
    requires_confirmation: bool = False,
    reason_required: bool = False,
    method: str | None = None,
    endpoint: str | None = None,
    target: Any | None = None,
    trace: TraceContext | None = None,
):
    return models.WorkbenchAction(
        id=action_id,
        label=label,
        owner=owner,
        risk=risk,
        allowed=allowed,
        disabled_reason=disabled_reason,
        requires_confirmation=requires_confirmation,
        reason_required=reason_required,
        method=method,
        endpoint=endpoint,
        target=target,
        trace=trace,
    )


def trace_route(trace: TraceContext) -> str:
    route = f"/workbench/traces/{trace.trace_id}"
    focus_id = trace_focus_id(trace)
    if focus_id:
        return f"{route}?focus_id={focus_id}"
    return route


def trace_focus_id(trace: TraceContext) -> str | None:
    for value in (
        trace.source_event_id,
        trace.llm_invocation_id,
        trace.tool_run_id,
        trace.session_item_id,
        trace.request_render_snapshot_id,
        trace.artifact_id,
        trace.approval_request_id,
    ):
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def trace_entity(trace: TraceContext):
    return linked_entity(
        entity_type="trace",
        entity_id=trace.trace_id,
        label="Trace",
        owner="events",
        route=trace_route(trace),
        trace=trace,
    )


def view_trace_action(trace: TraceContext):
    return runtime_action(
        action_id="view_trace",
        label="View trace",
        owner="events",
        target=trace_entity(trace),
        trace=trace,
    )


def linked_entities_for_trace(
    trace: TraceContext,
    *,
    artifacts: tuple[Any, ...] = (),
) -> tuple[Any, ...]:
    entities: list[Any] = []
    if trace.tool_run_id:
        entities.append(
            linked_entity(
                entity_type="tool_run",
                entity_id=trace.tool_run_id,
                label="Tool run",
                owner="tool",
                route=trace_route(trace),
                trace=trace,
            ),
        )
    if trace.llm_invocation_id:
        entities.append(
            linked_entity(
                entity_type="llm_invocation",
                entity_id=trace.llm_invocation_id,
                label="LLM invocation",
                owner="llm",
                route=trace_route(trace),
                trace=trace,
            ),
        )
    if trace.session_item_id:
        entities.append(
            linked_entity(
                entity_type="session_item",
                entity_id=trace.session_item_id,
                label="Session item",
                owner="session",
                route=trace_route(trace),
                trace=trace,
            ),
        )
    if trace.approval_request_id:
        entities.append(
            linked_entity(
                entity_type="approval_request",
                entity_id=trace.approval_request_id,
                label="Approval request",
                owner="orchestration",
                route=trace_route(trace),
                trace=trace,
            ),
        )
    artifact_ids = [trace.artifact_id] if trace.artifact_id else []
    artifact_ids.extend(artifact.artifact_id for artifact in artifacts)
    for artifact_id in dict.fromkeys(artifact_ids):
        entities.append(
            linked_entity(
                entity_type="artifact",
                entity_id=artifact_id,
                label="Artifact",
                owner="artifacts",
                route=trace_route(trace),
                trace=trace,
            ),
        )
    return dedupe_linked_entities(tuple(entities))


def dedupe_linked_entities(entities: tuple[Any, ...]) -> tuple[Any, ...]:
    deduped: list[Any] = []
    seen: set[tuple[str, str]] = set()
    for entity in entities:
        key = (entity.type, entity.id)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(entity)
    return tuple(deduped)


def cancelled_or_failed_trace_action(trace: TraceContext):
    return runtime_action(
        action_id="inspect_failure",
        label="Inspect failure",
        owner="orchestration",
        risk="controlled",
        target=trace_entity(trace),
        trace=trace,
    )
