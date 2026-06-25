from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from crxzipple.modules.orchestration.application.ports import OrchestrationRunQueryPort
from crxzipple.modules.orchestration.domain import OrchestrationRun
from crxzipple.modules.tool.domain import ToolRun
from crxzipple.modules.workbench.application.projection_helpers import (
    optional_text,
)
from crxzipple.modules.workbench.application.run_projector import (
    WorkbenchRunDetailProjector,
)
from crxzipple.modules.workbench.application.run_identity_projection import (
    turn_id as run_turn_id,
)
from crxzipple.modules.workbench.application.run_session_projection import (
    safe_list_runs_for_session,
    session_runs_for_run,
)
from crxzipple.modules.workbench.application.step_projector import (
    WorkbenchRunStepProjector,
)
from crxzipple.modules.workbench.application.thread_projector import (
    WorkbenchThreadListProjector,
)
from crxzipple.modules.workbench.application.tool_run_projection import (
    safe_list_tool_runs_for_runs,
    tool_scope_run_ids,
)
from crxzipple.modules.workbench.application.view_models import (
    TurnStepView,
    WorkbenchHomeView,
    WorkbenchRunView,
)


class WorkbenchToolRunQueryPort(Protocol):
    def list_tool_runs(
        self,
        *,
        tool_id: str | None = None,
        limit: int | None = None,
    ) -> list[ToolRun]:
        ...

    def get_tool_run(self, run_id: str) -> ToolRun:
        ...

    def list_tool_runs_for_orchestration_runs(
        self,
        run_ids: tuple[str, ...],
    ) -> list[ToolRun]:
        ...


class WorkbenchArtifactQueryPort(Protocol):
    def get_artifact(self, artifact_id: str) -> Any:
        ...


class WorkbenchLlmQueryPort(Protocol):
    def get_profile(self, llm_id: str) -> Any:
        ...

    def get_invocation(self, invocation_id: str) -> Any:
        ...

    def list_invocations(self, *, llm_id: str | None = None) -> list[Any]:
        ...


class WorkbenchAgentQueryPort(Protocol):
    def get_profile(self, profile_id: str) -> Any:
        ...


class WorkbenchSessionQueryPort(Protocol):
    def get_item(self, item_id: str) -> Any:
        ...


@dataclass(slots=True)
class WorkbenchReadModelProvider:
    run_query: OrchestrationRunQueryPort
    tool_query: WorkbenchToolRunQueryPort | None = None
    artifact_query: WorkbenchArtifactQueryPort | None = None
    llm_query: WorkbenchLlmQueryPort | None = None
    agent_query: WorkbenchAgentQueryPort | None = None
    session_query: WorkbenchSessionQueryPort | None = None

    def get_home_view(
        self,
        *,
        run_id: str | None = None,
        session_key: str | None = None,
    ) -> WorkbenchHomeView:
        return WorkbenchThreadListProjector(self.run_query).project_home_view(
            run_id=run_id,
            session_key=session_key,
        )

    def get_run_view(
        self,
        run_id: str,
        *,
        include_timeline: bool = True,
    ) -> WorkbenchRunView:
        return WorkbenchRunDetailProjector(
            run_query=self.run_query,
            list_step_views_for_run=self._list_step_views_for_run,
            tool_query=self.tool_query,
            artifact_query=self.artifact_query,
            llm_query=self.llm_query,
            agent_query=self.agent_query,
            session_query=self.session_query,
        ).project_run_view(
            run_id,
            include_timeline=include_timeline,
        )

    def list_step_views(
        self,
        run_id: str,
        *,
        turn_id: str | None = None,
    ) -> tuple[TurnStepView, ...]:
        run = self.run_query.get_run(run_id)
        candidate_runs = safe_list_runs_for_session(self.run_query, run.session_key)
        steps: list[TurnStepView] = []
        session_runs = session_runs_for_run(
            self.run_query,
            run,
            candidate_runs=candidate_runs,
        )
        selected_turn_id = optional_text(turn_id)
        if selected_turn_id is not None:
            selected_runs = tuple(
                session_run
                for session_run in session_runs
                if session_run.id == selected_turn_id
                or run_turn_id(session_run) == selected_turn_id
            )
            session_runs = selected_runs or (run,)
        tool_runs = safe_list_tool_runs_for_runs(
            self.tool_query,
            tool_scope_run_ids(
                self.run_query,
                session_runs,
                candidate_runs=candidate_runs,
            ),
        )
        for session_run in session_runs:
            steps.extend(
                self._list_step_views_for_run(
                    session_run,
                    candidate_runs=candidate_runs,
                    tool_runs=tool_runs,
                ),
            )
        return tuple(steps)

    def _list_step_views_for_run(
        self,
        run: OrchestrationRun,
        *,
        candidate_runs: list[OrchestrationRun] | None = None,
        tool_runs: list[ToolRun] | None = None,
    ) -> tuple[TurnStepView, ...]:
        return WorkbenchRunStepProjector(
            run_query=self.run_query,
            tool_query=self.tool_query,
            artifact_query=self.artifact_query,
            llm_query=self.llm_query,
            session_query=self.session_query,
        ).project_step_views_for_run(
            run,
            candidate_runs=candidate_runs,
            tool_runs=tool_runs,
        )
