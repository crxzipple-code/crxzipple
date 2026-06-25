from __future__ import annotations

from crxzipple.modules.workbench.application import view_models as models
from typing import Any

from crxzipple.modules.orchestration.domain import OrchestrationRun
from crxzipple.modules.workbench.application.action_projection import (
    run_actions,
    trace_route,
    view_trace_action,
)
from crxzipple.modules.workbench.application.inspector_assets import (
    linked_assets_for_run,
)
from crxzipple.modules.workbench.application.inspector_loop_health import (
    loop_health_section as _loop_health_section,
)
from crxzipple.modules.workbench.application.projection_helpers import (
    metadata_str,
    optional_text,
)
from crxzipple.modules.workbench.application.run_display_values import (
    key_value,
    tone_for_status,
)
from crxzipple.modules.workbench.application.run_identity_projection import (
    turn_id,
)
from crxzipple.modules.workbench.application.run_text_projection import (
    instruction_summary,
)
from crxzipple.modules.workbench.application.run_time_projection import (
    duration_label,
    duration_ms,
)
from crxzipple.modules.workbench.application.timeline_projector import (
    timeline_diagnostic_items,
)


def inspector_for_run(
    run: OrchestrationRun,
    *,
    session_runs: tuple[OrchestrationRun, ...],
    display_tool_runs: tuple[Any, ...],
    llm_invocations: tuple[Any, ...],
    metrics: Any,
    cover_artifact: Any | None,
    agent_ref: Any,
    model_ref: Any,
    trace: Any,
    agent_query: Any | None,
    timeline: tuple[Any, ...] = (),
    loop_health: dict[str, object] | None = None,
):
    agent_profile = _safe_agent_profile(agent_query, run.agent_id)
    linked_assets = linked_assets_for_run(
        run,
        display_tool_runs=display_tool_runs,
        llm_invocations=llm_invocations,
        cover_artifact=cover_artifact,
        trace=trace,
    )
    quick_actions = tuple(
        action
        for action in run_actions(run, trace=trace)
        if action.id != "cancel_run" or action.allowed
    )
    return models.WorkbenchInspectorView(
        tabs=("overview", "debug", "memory", "agent"),
        active_tab="overview",
        overview=(
            models.WorkbenchKeyValueSection(
                id="runtime",
                title="Runtime",
                items=(
                    key_value("Status", run.status.value, tone=tone_for_status(run.status.value)),
                    key_value("Stage", run.stage.value),
                    key_value("Waiting", run.waiting_reason or "-"),
                    key_value("Duration", duration_label(duration_ms(run))),
                ),
            ),
            models.WorkbenchKeyValueSection(
                id="metrics",
                title="Metrics",
                items=(
                    key_value("Tool calls", str(metrics.tool_calls)),
                    key_value("LLM calls", str(metrics.llm_calls)),
                    key_value("Tokens", str(metrics.tokens)),
                    key_value(
                        "Estimated cost",
                        (
                            f"${metrics.estimated_cost_usd:.3f}"
                            if metrics.estimated_cost_usd is not None
                            else "-"
                        ),
                    ),
                ),
            ),
        ),
        debug=(
            models.WorkbenchKeyValueSection(
                id="ids",
                title="Identifiers",
                items=(
                    key_value("Trace ID", trace.trace_id, route=trace_route(trace)),
                    key_value("Run ID", run.id),
                    key_value("Session", run.session_key or "-"),
                    key_value("Current turn", turn_id(run)),
                    key_value("Lane", run.lane_key or "-"),
                    key_value("Worker", run.worker_id or "-"),
                ),
                actions=(view_trace_action(trace),),
            ),
            models.WorkbenchKeyValueSection(
                id="step_counts",
                title="Step Counts",
                items=(
                    key_value("Turns", str(len(session_runs))),
                    key_value("Tool runs", str(len({item.tool_run.id for item in display_tool_runs}))),
                    key_value("LLM invocations", str(len(llm_invocations))),
                ),
            ),
            models.WorkbenchKeyValueSection(
                id="timeline_diagnostics",
                title="Timeline Diagnostics",
                items=timeline_diagnostic_items(timeline),
            ),
            _loop_health_section(loop_health),
        ),
        memory=(
            models.WorkbenchKeyValueSection(
                id="memory_context",
                title="Memory Context",
                items=(
                    key_value("Agent", run.agent_id or "-"),
                    key_value("Memory tools", str(_memory_tool_run_count(display_tool_runs))),
                    key_value("Runtime request mode", metadata_str(run, "runtime_request_mode") or "-"),
                ),
            ),
        ),
        agent=(
            models.WorkbenchKeyValueSection(
                id="agent_runtime",
                title="Agent Runtime",
                items=(
                    key_value("Agent", agent_ref.name),
                    key_value("Agent ID", agent_ref.id),
                    key_value("Model", model_ref.name),
                    key_value("Model ID", model_ref.id),
                    key_value(
                        "Default model",
                        _agent_default_llm_id(agent_profile) or "-",
                    ),
                    key_value(
                        "Memory scope",
                        _agent_memory_scope(agent_profile) or "-",
                    ),
                ),
            ),
        ),
        current_turn_summary=instruction_summary(run),
        linked_assets=linked_assets,
        quick_actions=quick_actions,
    )


def _safe_agent_profile(
    agent_query: Any | None,
    agent_id: str | None,
) -> Any | None:
    if agent_query is None or agent_id is None:
        return None
    try:
        return agent_query.get_profile(agent_id)
    except Exception:
        return None


def _agent_default_llm_id(agent_profile: Any | None) -> str | None:
    if agent_profile is None:
        return None
    routing = getattr(agent_profile, "llm_routing_policy", None)
    return optional_text(getattr(routing, "default_llm_id", None))


def _agent_memory_scope(agent_profile: Any | None) -> str | None:
    if agent_profile is None:
        return None
    memory = getattr(agent_profile, "memory", None)
    if not bool(getattr(memory, "enabled", False)):
        return "disabled"
    if hasattr(memory, "effective_scope_ref"):
        agent_id = optional_text(getattr(agent_profile, "id", None))
        if agent_id is not None:
            return optional_text(memory.effective_scope_ref(agent_id))
    return optional_text(getattr(memory, "scope_ref", None)) or "agent default"


def _memory_tool_run_count(display_tool_runs: tuple[Any, ...]) -> int:
    return sum(
        1
        for item in display_tool_runs
        if item.tool_run.tool_id.startswith("memory_")
    )
