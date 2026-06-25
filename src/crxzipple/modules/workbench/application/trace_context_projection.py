from __future__ import annotations

from crxzipple.modules.orchestration.domain import OrchestrationRun
from crxzipple.modules.workbench.application.projection_helpers import metadata_str
from crxzipple.shared.runtime_console import TraceContext


def trace_for_run(
    run: OrchestrationRun,
    *,
    turn_id: str,
    step_id: str | None = None,
    tool_run_id: str | None = None,
    llm_invocation_id: str | None = None,
    request_render_snapshot_id: str | None = None,
    session_item_id: str | None = None,
    artifact_id: str | None = None,
    approval_request_id: str | None = None,
    source_owner: str | None = None,
    source_event_id: str | None = None,
    source_event_name: str | None = None,
) -> TraceContext:
    trace_id = metadata_str(run, "trace_id") or run.id
    return TraceContext(
        trace_id=trace_id,
        correlation_id=metadata_str(run, "correlation_id"),
        session_key=run.session_key,
        session_id=run.active_session_id,
        turn_id=turn_id,
        run_id=run.id,
        step_id=step_id,
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
