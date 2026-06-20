"""Read/admin inspection operations for orchestration runs."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from crxzipple.modules.orchestration.application.engine import (
    OrchestrationEngine,
    RuntimeLlmRequestPreview,
)
from crxzipple.modules.orchestration.application.tool_resolver import (
    ResolvedToolSet,
    ToolExecutionDecision,
)
from crxzipple.modules.orchestration.domain.entities import OrchestrationRun
from crxzipple.modules.orchestration.domain.exceptions import (
    OrchestrationValidationError,
)
from crxzipple.modules.tool.domain import Tool, ToolExecutionTarget


@dataclass(slots=True)
class OrchestrationInspectionService:
    """Runtime request and tool inspection surface outside the run execution path."""

    engine: OrchestrationEngine | None
    get_run: Callable[[str], OrchestrationRun]

    def preview_runtime_llm_request(self, run_id: str) -> RuntimeLlmRequestPreview:
        engine = self._require_engine(
            "Runtime request preview requires an orchestration engine.",
        )
        return engine.preview_runtime_llm_request(self.get_run(run_id))

    def resolve_tools(self, run: OrchestrationRun) -> ResolvedToolSet:
        engine = self._require_engine(
            "Tool resolution requires an orchestration engine.",
        )
        return engine.tool_resolver.resolve(run)

    def decide_tool_execution(
        self,
        run: OrchestrationRun,
        *,
        tool: Tool,
        target: ToolExecutionTarget,
    ) -> ToolExecutionDecision:
        engine = self._require_engine(
            "Tool execution decisions require an orchestration engine.",
        )
        return engine.tool_resolver.execution_decision(
            run,
            tool=tool,
            target=target,
        )

    def _require_engine(self, message: str) -> OrchestrationEngine:
        if self.engine is None:
            raise OrchestrationValidationError(message)
        return self.engine
