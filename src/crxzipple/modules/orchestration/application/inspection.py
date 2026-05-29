"""Read/admin inspection operations for orchestration runs."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from crxzipple.modules.orchestration.application.engine import (
    OrchestrationEngine,
    PromptSurfacePreview,
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
    """Prompt and tool inspection surface outside the run execution path."""

    engine: OrchestrationEngine | None
    get_run: Callable[[str], OrchestrationRun]

    def preview_prompt(self, run_id: str) -> PromptSurfacePreview:
        engine = self._require_engine(
            "Prompt surface preview requires an orchestration engine.",
        )
        return engine.preview_prompt(self.get_run(run_id))

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

    def set_memory_flush_transcript_max_chars(self, max_chars: int) -> None:
        engine = self._require_engine(
            "Memory flush transcript configuration requires an orchestration engine.",
        )
        engine.prompt_surface.memory_flush_transcript_max_chars = max_chars

    def _require_engine(self, message: str) -> OrchestrationEngine:
        if self.engine is None:
            raise OrchestrationValidationError(message)
        return self.engine
