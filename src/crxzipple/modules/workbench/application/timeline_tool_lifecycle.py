from __future__ import annotations

from crxzipple.modules.workbench.application import view_models as models
from typing import Any

from crxzipple.modules.orchestration.application.ports import OrchestrationRunQueryPort
from crxzipple.modules.orchestration.domain import OrchestrationRun
from crxzipple.modules.orchestration.domain.value_objects import (
    ExecutionStepItemKind,
    ExecutionStepKind,
)
from crxzipple.modules.tool.domain import ToolRun
from crxzipple.modules.workbench.application.execution_projection import (
    execution_item_summary,
    execution_item_view_status,
    execution_step_bundles,
    request_render_snapshot_id as execution_request_render_snapshot_id,
    summary_text,
    summary_text_list,
)
from crxzipple.modules.workbench.application.run_identity_projection import turn_id
from crxzipple.modules.workbench.application.trace_context_projection import (
    trace_for_run,
)
from crxzipple.modules.workbench.application.timeline_refs import (
    timeline_ref,
    timeline_sort_key,
)
from crxzipple.modules.workbench.application.timeline_tool_interactions import (
    merge_tool_interaction_timeline_items,
)
from crxzipple.modules.workbench.application.timeline_tool_lifecycle_content import (
    timeline_content_for_tool_execution_item,
)
from crxzipple.modules.workbench.application.timeline_visibility import (
    suppress_loop_control_timeline_items,
)
from crxzipple.shared.time import format_optional_datetime_utc


def timeline_items_with_tool_lifecycle(
    timeline: tuple[Any, ...],
    *,
    run_query: OrchestrationRunQueryPort,
    runs: tuple[OrchestrationRun, ...],
    tool_runs: tuple[ToolRun, ...] = (),
) -> tuple[Any, ...]:
    lifecycle_items: list[Any] = []
    replaced_tool_run_item_ids: set[str] = set()
    replaced_tool_run_ids: set[str] = set()
    tool_runs_by_id = {tool_run.id: tool_run for tool_run in tool_runs}
    for run in runs:
        resolved_turn_id = turn_id(run)
        for bundle in execution_step_bundles(run_query, run.id):
            if bundle.step.kind is not ExecutionStepKind.TOOL_BATCH:
                continue
            for item in bundle.items:
                if item.kind not in {
                    ExecutionStepItemKind.TOOL_CALL,
                    ExecutionStepItemKind.TOOL_RUN,
                    ExecutionStepItemKind.TOOL_RESULT,
                }:
                    continue
                lifecycle_item = _timeline_item_from_tool_execution_item(
                    run,
                    turn_id=resolved_turn_id,
                    bundle=bundle,
                    item=item,
                    tool_runs_by_id=tool_runs_by_id,
                )
                lifecycle_items.append(lifecycle_item)
                if item.kind is ExecutionStepItemKind.TOOL_RUN:
                    replaced_tool_run_item_ids.add(item.id)
                    tool_run_id = lifecycle_item.source_refs.get("tool_run_id")
                    if tool_run_id:
                        replaced_tool_run_ids.add(tool_run_id)
    if not lifecycle_items:
        return suppress_loop_control_timeline_items(timeline)
    retained = tuple(
        item
        for item in timeline
        if not (
            item.kind == "tool_run"
            and (
                item.source_refs.get("execution_item_id") in replaced_tool_run_item_ids
                or timeline_ref(item, "tool_run_id") in replaced_tool_run_ids
            )
        )
    )
    merged = merge_tool_interaction_timeline_items(
        tuple(
            sorted(
                (*retained, *lifecycle_items),
                key=timeline_sort_key,
            ),
        ),
    )
    return suppress_loop_control_timeline_items(merged)


def _timeline_item_from_tool_execution_item(
    run: OrchestrationRun,
    *,
    turn_id: str,
    bundle: Any,
    item: Any,
    tool_runs_by_id: dict[str, ToolRun] | None = None,
) -> Any:
    summary = execution_item_summary(item)
    request_render_snapshot_id = execution_request_render_snapshot_id(
        run,
        summary=summary,
    )
    tool_run_id = summary_text(summary, "tool_run_id")
    tool_run = tool_runs_by_id.get(tool_run_id) if tool_runs_by_id and tool_run_id else None
    tool_call_id = summary_text(summary, "tool_call_id") or item.correlation_key
    result_session_item_id = summary_text(summary, "result_session_item_id")
    session_item_ids = summary_text_list(summary, "session_item_ids")
    session_item_id = result_session_item_id or (
        session_item_ids[0] if session_item_ids else None
    )
    tool_name = (
        summary_text(summary, "tool_name")
        or summary_text(summary, "tool_id")
        or "tool"
    )
    source_refs = {
        "run_id": run.id,
        "turn_id": turn_id,
        "execution_step_id": bundle.step.id,
        "execution_item_id": item.id,
    }
    if tool_call_id:
        source_refs["tool_call_id"] = tool_call_id
    if tool_run_id:
        source_refs["tool_run_id"] = tool_run_id
    if session_item_id:
        source_refs["session_item_id"] = session_item_id
    if request_render_snapshot_id:
        source_refs["request_render_snapshot_id"] = request_render_snapshot_id
    tool_id = summary_text(summary, "tool_id")
    if tool_id:
        source_refs["tool_id"] = tool_id
    trace = trace_for_run(
        run,
        turn_id=turn_id,
        step_id=bundle.step.id,
        tool_run_id=tool_run_id,
        request_render_snapshot_id=request_render_snapshot_id,
        session_item_id=session_item_id,
        source_owner=item.owner.owner_kind if item.owner is not None else None,
        source_event_id=item.owner.owner_id if item.owner is not None else item.id,
        source_event_name=item.kind.value,
    )
    return models.WorkbenchTimelineItem(
        id=f"timeline:{run.id}:execution:{bundle.step.id}:{item.id}",
        turn_id=turn_id,
        run_id=run.id,
        kind=_timeline_kind_for_tool_execution_item(item),
        status=execution_item_view_status(item),
        title=_timeline_title_for_tool_execution_item(item, tool_name=tool_name),
        content=timeline_content_for_tool_execution_item(
            item,
            summary=summary,
            tool_name=tool_name,
            tool_run=tool_run,
        ),
        phase=None,
        source_refs=source_refs,
        started_at=format_optional_datetime_utc(item.created_at),
        completed_at=format_optional_datetime_utc(item.completed_at),
        trace=trace,
    )


def _timeline_kind_for_tool_execution_item(item: Any) -> str:
    if item.kind is ExecutionStepItemKind.TOOL_CALL:
        return "tool_call"
    if item.kind is ExecutionStepItemKind.TOOL_RESULT:
        return "tool_result"
    return "tool_run"


def _timeline_title_for_tool_execution_item(
    item: Any,
    *,
    tool_name: str,
) -> str:
    if item.kind is ExecutionStepItemKind.TOOL_CALL:
        return f"Tool Call: {tool_name}"
    if item.kind is ExecutionStepItemKind.TOOL_RESULT:
        return f"Tool Result: {tool_name}"
    return f"Tool Run: {tool_name}"
