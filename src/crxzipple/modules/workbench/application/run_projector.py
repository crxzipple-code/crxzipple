from __future__ import annotations

from crxzipple.modules.workbench.application import view_models as models
from collections.abc import Callable
from dataclasses import dataclass
from time import perf_counter
from typing import Any

from crxzipple.modules.orchestration.application.ports import OrchestrationRunQueryPort
from crxzipple.modules.workbench.application.action_projection import run_actions
from crxzipple.modules.workbench.application.execution_projection import (
    llm_invocations_for_runs,
)
from crxzipple.modules.workbench.application.inspector_loop_health import (
    loop_health_for_workbench,
)
from crxzipple.modules.workbench.application.inspector_projector import inspector_for_run
from crxzipple.modules.workbench.application.projection_diagnostics import (
    counted_owner,
    owner_call_count,
    owner_call_sources,
    processed_item_count,
    workbench_run_owner_fact_sources,
)
from crxzipple.modules.workbench.application.timeline_projector import (
    WorkbenchRunTimelineProjector,
)
from crxzipple.modules.workbench.application.run_session_projection import (
    safe_list_runs_for_session,
    session_runs_for_run,
    turn_summaries,
)
from crxzipple.modules.workbench.application.runtime_ref_projection import (
    agent_ref,
    model_ref,
)
from crxzipple.modules.workbench.application.run_identity_projection import turn_id
from crxzipple.modules.workbench.application.run_metrics_projection import (
    metrics_for_runs,
)
from crxzipple.modules.workbench.application.run_status_projection import (
    status_strip,
)
from crxzipple.modules.workbench.application.run_text_projection import (
    run_title,
)
from crxzipple.modules.workbench.application.run_time_projection import duration_ms
from crxzipple.modules.workbench.application.trace_context_projection import (
    trace_for_run,
)
from crxzipple.modules.workbench.application.tool_artifact_projection import (
    cover_artifact as cover_artifact_for_runs,
)
from crxzipple.modules.workbench.application.tool_run_projection import (
    display_tool_runs,
    safe_list_tool_runs_for_runs,
    tool_scope_run_ids,
)
from crxzipple.shared.time import format_optional_datetime_utc


@dataclass(frozen=True, slots=True)
class WorkbenchRunDetailProjector:
    run_query: OrchestrationRunQueryPort
    list_step_views_for_run: Callable[..., tuple[Any, ...]]
    tool_query: Any | None = None
    artifact_query: Any | None = None
    llm_query: Any | None = None
    agent_query: Any | None = None
    session_query: Any | None = None

    def project_run_view(
        self,
        run_id: str,
        *,
        include_timeline: bool = True,
    ):
        projection_started_at = perf_counter()
        run_query = counted_owner(self.run_query, owner="orchestration")
        tool_query = counted_owner(self.tool_query, owner="tool")
        artifact_query = counted_owner(self.artifact_query, owner="artifact")
        llm_query = counted_owner(self.llm_query, owner="llm")
        agent_query = counted_owner(self.agent_query, owner="agent")
        session_query = counted_owner(self.session_query, owner="session")
        run = run_query.get_run(run_id)
        candidate_runs = safe_list_runs_for_session(run_query, run.session_key)
        session_runs = session_runs_for_run(
            run_query,
            run,
            candidate_runs=candidate_runs,
        )
        tool_runs = safe_list_tool_runs_for_runs(
            tool_query,
            tool_scope_run_ids(
                run_query,
                session_runs,
                candidate_runs=candidate_runs,
            ),
        )
        turn_id_value = turn_id(run)
        session_display_tool_runs = tuple(
            display_tool_run
            for session_run in session_runs
            for display_tool_run in display_tool_runs(
                run_query,
                tool_query,
                session_run,
                candidate_runs=candidate_runs,
                tool_runs=tool_runs,
            )
        )
        llm_invocations = llm_invocations_for_runs(
            run_query,
            llm_query,
            session_runs,
        )
        trace = trace_for_run(run, turn_id=turn_id_value)
        agent_runtime_ref = agent_ref(run, agent_query)
        model_runtime_ref = model_ref(run, llm_query, run_query=run_query)
        cover_artifact = cover_artifact_for_runs(
            tuple(
                display_tool_run.tool_run
                for display_tool_run in session_display_tool_runs
            ),
            artifact_query=artifact_query,
        )
        actions = run_actions(run, trace=trace)
        timeline: tuple[Any, ...] = ()
        if include_timeline:
            timeline = WorkbenchRunTimelineProjector(
                run_query=run_query,
                list_step_views_for_run=self.list_step_views_for_run,
                llm_query=llm_query,
            ).project_timeline(
                run=run,
                candidate_runs=candidate_runs,
                tool_runs=tool_runs,
            )
        metrics = metrics_for_runs(
            session_runs,
            related_tool_runs=tuple(
                display_tool_run.tool_run
                for display_tool_run in session_display_tool_runs
            ),
            llm_invocations=llm_invocations,
            timeline=timeline,
        )
        loop_health = loop_health_for_workbench(
            run_query,
            run,
            llm_invocations=llm_invocations,
        )
        inspector = inspector_for_run(
            run,
            session_runs=session_runs,
            display_tool_runs=session_display_tool_runs,
            llm_invocations=llm_invocations,
            metrics=metrics,
            cover_artifact=cover_artifact,
            agent_ref=agent_runtime_ref,
            model_ref=model_runtime_ref,
            trace=trace,
            agent_query=agent_query,
            timeline=timeline,
            loop_health=loop_health,
        )
        projection_diagnostics = models.WorkbenchProjectionDiagnostics(
            owner_sources=workbench_run_owner_fact_sources(),
            owner_call_sources=owner_call_sources(
                run_query,
                tool_query,
                artifact_query,
                llm_query,
                agent_query,
                session_query,
            ),
            owner_call_count=owner_call_count(
                run_query,
                tool_query,
                artifact_query,
                llm_query,
                agent_query,
                session_query,
            ),
            processed_item_count=processed_item_count(
                candidate_runs,
                session_runs,
                tool_runs,
                session_display_tool_runs,
                llm_invocations,
                timeline,
            ),
            timeline_item_count=len(timeline),
            elapsed_ms=round((perf_counter() - projection_started_at) * 1000, 3),
        )
        return models.WorkbenchRunView(
            run_id=run.id,
            session_key=run.session_key or "",
            title=run_title(run),
            status=run.status.value,
            agent=agent_runtime_ref,
            model=model_runtime_ref,
            started_at=format_optional_datetime_utc(run.started_at),
            completed_at=format_optional_datetime_utc(run.completed_at),
            duration_ms=duration_ms(run),
            metrics=metrics,
            turns=turn_summaries(session_runs),
            current_turn_id=turn_id_value,
            status_strip=status_strip(run),
            cover_artifact=cover_artifact,
            timeline=timeline,
            actions=actions,
            inspector=inspector,
            trace=trace,
            projection_diagnostics=projection_diagnostics,
        )
