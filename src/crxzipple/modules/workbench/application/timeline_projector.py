from __future__ import annotations

from crxzipple.modules.workbench.application import view_models as models
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from crxzipple.modules.orchestration.application.ports import OrchestrationRunQueryPort
from crxzipple.modules.orchestration.domain import OrchestrationRun
from crxzipple.modules.tool.domain import ToolRun
from crxzipple.modules.workbench.application.execution_projection import (
    llm_invocations_for_runs,
)
from crxzipple.modules.workbench.application.projection_helpers import optional_text
from crxzipple.modules.workbench.application.run_display_values import key_value
from crxzipple.modules.workbench.application.timeline_refs import (
    timeline_source_refs,
)
from crxzipple.modules.workbench.application.timeline_response_items import (
    timeline_items_from_llm_response_items,
)
from crxzipple.modules.workbench.application.timeline_tool_lifecycle import (
    timeline_items_with_tool_lifecycle,
)
from crxzipple.modules.workbench.application.timeline_visibility import (
    deduplicate_timeline_items,
    step_should_be_visible_in_timeline,
)


def timeline_items_from_steps(
    steps: tuple[Any, ...],
    *,
    llm_invocations_by_id: dict[str, Any] | None = None,
) -> tuple[Any, ...]:

    items: list[Any] = []
    for index, step in enumerate(steps):
        if step.type == "llm" and llm_invocations_by_id:
            invocation_id = step.trace.llm_invocation_id
            invocation = (
                llm_invocations_by_id.get(invocation_id)
                if invocation_id
                else None
            )
            if invocation is not None:
                response_items = tuple(
                    getattr(invocation, "response_items", ()) or (),
                )
                items.extend(
                    timeline_items_from_llm_response_items(
                        step,
                        response_items=response_items,
                        base_index=index,
                    ),
                )
        if not step_should_be_visible_in_timeline(step):
            continue
        items.append(_timeline_item_from_step(step, index=index))
    return deduplicate_timeline_items(tuple(items))


def _timeline_item_from_step(step: Any, *, index: int) -> Any:
    content: dict[str, Any] = {}
    if step.markdown:
        content["markdown"] = step.markdown
    if step.summary:
        content["text"] = step.summary
    source_refs = timeline_source_refs(step)
    return models.WorkbenchTimelineItem(
        id=f"timeline:{step.step_id}:{index}",
        turn_id=step.turn_id,
        run_id=step.run_id,
        kind=_timeline_kind_for_step(step),
        status=step.status,
        title=step.title,
        content=content,
        phase=_timeline_phase_for_step(step),
        source_refs=source_refs,
        started_at=step.started_at,
        completed_at=step.completed_at,
        trace=step.trace,
    )


def _timeline_kind_for_step(step: Any) -> str:
    if step.type == "agent_progress":
        return "assistant_commentary"
    if step.type == "agent_thinking":
        return "reasoning_summary"
    if step.type == "llm":
        return "llm_invocation"
    if step.type == "continuation_decision":
        return "continuation"
    if step.type == "approval_required":
        return "approval"
    if step.type == "missing_access":
        return "wait_state"
    if step.type == "tool_call":
        if step.trace.tool_run_id:
            return "tool_run"
        return "tool_call"
    if step.type == "tool_result":
        return "tool_result"
    if step.type == "final_response":
        return "final_answer"
    return step.type


def _timeline_phase_for_step(step: Any) -> str | None:
    if step.type == "agent_progress":
        return "commentary"
    if step.type in {"agent_thinking", "llm"}:
        return "reasoning"
    if step.type == "final_response":
        return "final"
    return None


def timeline_diagnostic_items(timeline: tuple[Any, ...]) -> tuple[Any, ...]:
    response_item_count = sum(
        1 for item in timeline if item.source_refs.get("llm_response_item_id")
    )
    tool_lifecycle_count = sum(
        1 for item in timeline if item.kind in {"tool_call", "tool_run", "tool_result"}
    )
    hidden_reasoning_count = sum(
        1
        for item in timeline
        if item.kind == "reasoning_summary"
        and bool(item.content.get("reasoning_hidden"))
    )
    provider_external_count = sum(
        1 for item in timeline if item.kind == "provider_external_activity"
    )
    return (
        key_value("Timeline items", str(len(timeline))),
        key_value("LLM response items", str(response_item_count)),
        key_value("Tool lifecycle items", str(tool_lifecycle_count)),
        key_value("Hidden reasoning items", str(hidden_reasoning_count)),
        key_value("Provider external items", str(provider_external_count)),
    )


@dataclass(frozen=True, slots=True)
class WorkbenchRunTimelineProjector:
    run_query: OrchestrationRunQueryPort
    list_step_views_for_run: Callable[..., tuple[Any, ...]]
    llm_query: Any | None = None

    def project_timeline(
        self,
        *,
        run: OrchestrationRun,
        candidate_runs: list[OrchestrationRun] | None,
        tool_runs: list[ToolRun] | None,
    ):
        timeline_steps: list[Any] = []
        timeline_runs = (run,)
        timeline_llm_invocations = llm_invocations_for_runs(
            self.run_query,
            self.llm_query,
            timeline_runs,
        )
        for session_run in timeline_runs:
            timeline_steps.extend(
                self.list_step_views_for_run(
                    session_run,
                    candidate_runs=candidate_runs,
                    tool_runs=tool_runs,
                ),
            )
        timeline = timeline_items_from_steps(
            tuple(timeline_steps),
            llm_invocations_by_id={
                invocation_id: invocation
                for invocation in timeline_llm_invocations
                if (invocation_id := optional_text(getattr(invocation, "id", None)))
                is not None
            },
        )
        return timeline_items_with_tool_lifecycle(
            timeline,
            run_query=self.run_query,
            runs=timeline_runs,
            tool_runs=tool_runs,
        )
