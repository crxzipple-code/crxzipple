from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.tool_page_facts import (
    ToolPageFacts,
)
from crxzipple.modules.operations.application.read_models.tool_run_details import (
    tool_run_details,
)
from crxzipple.modules.operations.application.read_models.tool_worker_details import (
    tool_worker_details,
)


def tool_detail_sections(
    *,
    facts: ToolPageFacts,
    artifact_service: Any | None,
) -> dict[str, Any]:
    return {
        "worker_details": tool_worker_details(
            facts.workers,
            active_runs=facts.active_runs,
            observed_events=facts.observed_events,
            now=facts.now,
        ),
        "tool_run_details": tool_run_details(
            facts.detail_runs,
            tools=facts.tools,
            assignments=facts.assignments,
            observed_events=facts.observed_events,
            artifact_service=artifact_service,
            run_contexts=facts.run_contexts,
            now=facts.now,
        ),
    }
