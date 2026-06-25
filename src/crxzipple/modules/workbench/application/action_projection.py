from __future__ import annotations

from typing import Any

from crxzipple.modules.orchestration.domain import OrchestrationRun
from crxzipple.modules.orchestration.domain.value_objects import (
    OrchestrationRunStatus,
)
from crxzipple.modules.workbench.application.action_approval import approval_actions
from crxzipple.modules.workbench.application.action_links import (
    cancelled_or_failed_trace_action,
    dedupe_linked_entities,
    linked_entities_for_trace,
    linked_entity,
    runtime_action,
    trace_entity,
    trace_focus_id,
    trace_route,
    view_trace_action,
)
from crxzipple.shared.runtime_console import TraceContext

__all__ = [
    "approval_actions",
    "cancelled_or_failed_trace_action",
    "dedupe_linked_entities",
    "linked_entities_for_trace",
    "linked_entity",
    "run_actions",
    "runtime_action",
    "step_actions",
    "trace_entity",
    "trace_focus_id",
    "trace_route",
    "view_trace_action",
]


def step_actions(
    run: OrchestrationRun,
    *,
    trace: TraceContext,
    step_type: str,
    status: str,
    artifacts: tuple[Any, ...],
) -> tuple[Any, ...]:

    actions: list[Any] = [view_trace_action(trace)]
    for artifact in artifacts:
        if artifact.preview_url:
            actions.append(
                runtime_action(
                    action_id=f"view_artifact:{artifact.artifact_id}",
                    label="View artifact",
                    owner="artifacts",
                    method="GET",
                    endpoint=artifact.preview_url,
                    target=linked_entity(
                        entity_type="artifact",
                        entity_id=artifact.artifact_id,
                        label=artifact.name,
                        owner="artifacts",
                        route=trace_route(trace),
                        trace=trace,
                    ),
                    trace=trace,
                ),
            )
        if artifact.download_url:
            actions.append(
                runtime_action(
                    action_id=f"download_artifact:{artifact.artifact_id}",
                    label="Download artifact",
                    owner="artifacts",
                    method="GET",
                    endpoint=artifact.download_url,
                    target=linked_entity(
                        entity_type="artifact",
                        entity_id=artifact.artifact_id,
                        label=artifact.name,
                        owner="artifacts",
                        route=trace_route(trace),
                        trace=trace,
                    ),
                    trace=trace,
                ),
            )
    if step_type == "approval_required":
        actions.extend(approval_actions(run, trace=trace))
    if step_type == "missing_access":
        actions.append(
            runtime_action(
                action_id="open_access_inventory",
                label="Open access inventory",
                owner="access",
                target=linked_entity(
                    entity_type="access_inventory",
                    entity_id="access",
                    label="Access inventory",
                    owner="access",
                    route="/settings/access-assets",
                    trace=trace,
                ),
                trace=trace,
            ),
        )
    if step_type == "error" and status == "failed":
        actions.append(cancelled_or_failed_trace_action(trace))
    return tuple(actions)


def run_actions(
    run: OrchestrationRun,
    *,
    trace: TraceContext,
) -> tuple[Any, ...]:
    cancellable = run.status not in {
        OrchestrationRunStatus.COMPLETED,
        OrchestrationRunStatus.FAILED,
        OrchestrationRunStatus.CANCELLED,
    }
    approval_runtime_actions = approval_actions(run, trace=trace)
    return (
        view_trace_action(trace),
        runtime_action(
            action_id="open_operations",
            label="Open operations",
            owner="orchestration",
            target=linked_entity(
                entity_type="operations_view",
                entity_id="orchestration",
                label="Orchestration operations",
                owner="orchestration",
                route="/operations/orchestration",
                trace=trace,
            ),
            trace=trace,
        ),
        *approval_runtime_actions,
        runtime_action(
            action_id="cancel_run",
            label="Cancel run",
            owner="orchestration",
            risk="controlled",
            allowed=cancellable,
            disabled_reason=None if cancellable else "Run is already terminal.",
            requires_confirmation=True,
            reason_required=True,
            method="POST",
            endpoint=f"/turns/{run.id}/cancel",
            target=linked_entity(
                entity_type="run",
                entity_id=run.id,
                label="Run",
                owner="orchestration",
                route=trace_route(trace),
                trace=trace,
            ),
            trace=trace,
        ),
    )
