from __future__ import annotations

from crxzipple.modules.workbench.application import view_models as models
from datetime import datetime
from typing import Any

from crxzipple.modules.orchestration.domain import OrchestrationRun
from crxzipple.modules.workbench.application.action_projection import (
    dedupe_linked_entities,
    linked_entities_for_trace,
    step_actions,
)
from crxzipple.modules.workbench.application.run_time_projection import span_ms
from crxzipple.modules.workbench.application.trace_context_projection import (
    trace_for_run,
)
from crxzipple.shared.time import format_optional_datetime_utc


def make_step_view(
    *,
    run: OrchestrationRun,
    turn_id: str,
    step_id: str,
    step_type: str,
    status: str,
    title: str,
    summary: str,
    started_at: datetime | None,
    completed_at: datetime | None,
    markdown: str | None = None,
    artifacts: tuple[Any, ...] = (),
    badges: tuple[Any, ...] = (),
    linked_entities: tuple[Any, ...] = (),
    actions: tuple[Any, ...] = (),
    approval: Any | None = None,
    tool_run_id: str | None = None,
    llm_invocation_id: str | None = None,
    request_render_snapshot_id: str | None = None,
    session_item_id: str | None = None,
    artifact_id: str | None = None,
    approval_request_id: str | None = None,
    trace_step_id: str | None = None,
    source_owner: str | None = None,
    source_event_id: str | None = None,
    source_event_name: str | None = None,
) -> Any:
    stable_step_id = f"{run.id}:{step_id}"
    trace = trace_for_run(
        run,
        turn_id=turn_id,
        step_id=trace_step_id or stable_step_id,
        tool_run_id=tool_run_id,
        llm_invocation_id=llm_invocation_id,
        request_render_snapshot_id=request_render_snapshot_id,
        session_item_id=session_item_id,
        artifact_id=artifact_id,
        approval_request_id=approval_request_id,
        source_owner=source_owner,
        source_event_id=source_event_id,
        source_event_name=source_event_name,
    )
    resolved_linked_entities = dedupe_linked_entities(
        (
            *linked_entities_for_trace(trace, artifacts=artifacts),
            *linked_entities,
        ),
    )
    resolved_actions = actions or step_actions(
        run,
        trace=trace,
        step_type=step_type,
        status=status,
        artifacts=artifacts,
    )
    return models.TurnStepView(
        step_id=stable_step_id,
        turn_id=turn_id,
        run_id=run.id,
        type=step_type,
        status=status,
        title=title,
        summary=summary,
        markdown=markdown,
        started_at=format_optional_datetime_utc(started_at),
        completed_at=format_optional_datetime_utc(completed_at),
        duration_ms=span_ms(started_at, completed_at),
        artifacts=artifacts,
        badges=badges,
        linked_entities=resolved_linked_entities,
        actions=resolved_actions,
        approval=approval,
        details_available=True,
        trace=trace,
    )
