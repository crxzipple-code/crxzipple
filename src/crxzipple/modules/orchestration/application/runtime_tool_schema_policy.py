from __future__ import annotations

from dataclasses import dataclass

from crxzipple.modules.orchestration.application.runtime_request_mode import RuntimeRequestMode
from crxzipple.modules.orchestration.application.runtime_request_report import (
    RunSurfacePolicy,
)
from crxzipple.modules.orchestration.application.runtime_step_budget_policy import (
    RuntimeStepBudget,
)
from crxzipple.modules.orchestration.application.tool_resolver import ResolvedToolSet


@dataclass(frozen=True, slots=True)
class RuntimeToolSchemaPolicy:
    def should_include_tool_schemas(
        self,
        *,
        resolved_mode: RuntimeRequestMode,
        surface_policy: RunSurfacePolicy,
        resolved_tools: ResolvedToolSet | None,
        step_budget: RuntimeStepBudget,
    ) -> bool:
        if resolved_tools is None or not resolved_tools.tools:
            return False
        if not surface_policy.include_tool_schemas:
            return False
        return True
