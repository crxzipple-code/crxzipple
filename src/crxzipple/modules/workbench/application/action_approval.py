from __future__ import annotations

from dataclasses import replace
from typing import Any

from crxzipple.modules.orchestration.domain import OrchestrationRun
from crxzipple.modules.workbench.application.action_links import (
    linked_entity,
    runtime_action,
    trace_route,
)
from crxzipple.modules.workbench.application.run_status_projection import (
    run_is_waiting_for_approval,
)
from crxzipple.shared.runtime_console import TraceContext


def approval_actions(
    run: OrchestrationRun,
    *,
    trace: TraceContext,
) -> tuple[Any, ...]:
    if not run_is_waiting_for_approval(run):
        return ()
    request_payload = (
        dict(run.pending_approval_request_payload)
        if isinstance(run.pending_approval_request_payload, dict)
        else {}
    )
    request_id = (
        str(request_payload.get("request_id", "")).strip()
        or trace.approval_request_id
        or ""
    )
    if not request_id:
        return ()
    approval_trace = (
        trace
        if trace.approval_request_id == request_id
        else replace(trace, approval_request_id=request_id)
    )
    approval_endpoint = f"/turns/{run.id}/approvals/{request_id}"
    actions: list[Any] = []
    for action_id, label, risk in (
        ("allow_once", "Allow once", "controlled"),
        ("allow_for_session", "Allow for session", "controlled"),
        ("always_for_agent", "Always allow for agent", "controlled"),
        ("deny", "Deny", "dangerous"),
    ):
        actions.append(
            runtime_action(
                action_id=f"approval:{action_id}",
                label=label,
                owner="orchestration",
                risk=risk,
                method="POST",
                endpoint=approval_endpoint,
                target=linked_entity(
                    entity_type="approval_request",
                    entity_id=request_id,
                    label="Approval request",
                    owner="orchestration",
                    route=trace_route(approval_trace),
                    trace=approval_trace,
                ),
                trace=approval_trace,
            ),
        )
    return tuple(actions)
