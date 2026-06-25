from __future__ import annotations

from typing import Any

from crxzipple.modules.orchestration.domain import OrchestrationRun
from crxzipple.modules.workbench.application import view_models as models
from crxzipple.modules.workbench.application.projection_helpers import optional_text
from crxzipple.modules.workbench.application.run_llm_projection import (
    llm_id,
    llm_invocation_token_total,
)
from crxzipple.modules.workbench.application.timeline_refs import timeline_ref


def metrics(
    run: OrchestrationRun,
    *,
    related_tool_runs: tuple[Any, ...] = (),
    llm_invocations: tuple[Any, ...] = (),
):
    known_tool_ids = {
        *run.pending_tool_run_ids,
        *(tool_run.id for tool_run in related_tool_runs),
    }
    runtime_request_report = run.metadata.get("runtime_request_report")
    token_total = token_total_from_invocations(llm_invocations)
    if not llm_invocations and isinstance(runtime_request_report, dict):
        raw_total = runtime_request_report.get("token_total") or runtime_request_report.get("total_tokens")
        if isinstance(raw_total, int):
            token_total = max(raw_total, 0)
    return models.RunMetrics(
        tool_calls=len(known_tool_ids),
        llm_calls=(
            len(llm_invocations)
            if llm_invocations
            else max(run.current_step, 1 if llm_id(run) else 0)
        ),
        tokens=token_total,
        estimated_cost_usd=None,
    )


def metrics_for_runs(
    runs: tuple[OrchestrationRun, ...],
    *,
    related_tool_runs: tuple[Any, ...] = (),
    llm_invocations: tuple[Any, ...] = (),
    timeline: tuple[Any, ...] = (),
):
    known_tool_ids = {tool_run.id for tool_run in related_tool_runs}
    known_tool_call_ids: set[str] = set()
    known_llm_invocation_ids = {
        invocation_id
        for invocation in llm_invocations
        if (invocation_id := optional_text(getattr(invocation, "id", None)))
        is not None
    }
    for item in timeline:
        if tool_call_id := timeline_ref(item, "tool_call_id"):
            known_tool_call_ids.add(tool_call_id)
        if tool_run_id := timeline_ref(item, "tool_run_id"):
            known_tool_ids.add(tool_run_id)
        if llm_invocation_id := timeline_ref(item, "llm_invocation_id"):
            known_llm_invocation_ids.add(llm_invocation_id)
    token_total = token_total_from_invocations(llm_invocations)
    llm_calls = len(known_llm_invocation_ids)
    for run in runs:
        known_tool_ids.update(run.pending_tool_run_ids)
        runtime_request_report = run.metadata.get("runtime_request_report")
        if not known_llm_invocation_ids and isinstance(runtime_request_report, dict):
            raw_total = runtime_request_report.get("token_total") or runtime_request_report.get("total_tokens")
            if isinstance(raw_total, int):
                token_total += max(raw_total, 0)
        if not known_llm_invocation_ids:
            llm_calls += max(run.current_step, 1 if llm_id(run) else 0)
    return models.RunMetrics(
        tool_calls=len(known_tool_call_ids) if known_tool_call_ids else len(known_tool_ids),
        llm_calls=llm_calls,
        tokens=token_total,
        estimated_cost_usd=None,
    )


def token_total_from_invocations(invocations: tuple[Any, ...]) -> int:
    return sum(
        token_total
        for token_total in (
            llm_invocation_token_total(invocation) for invocation in invocations
        )
        if token_total is not None
    )
