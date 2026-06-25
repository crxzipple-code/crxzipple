from __future__ import annotations

from typing import Any

from crxzipple.modules.tool.application.concurrency import ToolRunConcurrencyPolicy
from crxzipple.modules.operations.application.read_models.tool_lifecycle_events import (
    tool_lifecycle_events_section,
)
from crxzipple.modules.operations.application.read_models.tool_overview_execution_sections import (
    inline_risk_section,
    strategies_section,
)
from crxzipple.modules.operations.application.read_models.tool_page_facts import (
    ToolPageFacts,
)
from crxzipple.modules.operations.application.read_models.tool_page_helpers import (
    active_tool_runs_table_section,
    recent_tool_artifacts_section,
    tool_runs_table_section,
)
from crxzipple.modules.operations.application.read_models.tool_page_run_selection import (
    tool_page_runs_empty_state,
)
from crxzipple.modules.operations.application.read_models.tool_provider_limits import (
    provider_limits_section,
)
from crxzipple.modules.operations.application.read_models.tool_scheduling_blocker_sections import (
    run_blockers_section,
)
from crxzipple.modules.operations.application.read_models.tool_scheduling_capability_sections import (
    capability_limits_section,
)
from crxzipple.modules.operations.application.read_models.tool_scheduling_queue_sections import (
    tool_queue_runs_section,
    tool_queue_section,
    tool_waiting_io_section,
)


def tool_execution_sections(
    *,
    facts: ToolPageFacts,
    concurrency_policy: ToolRunConcurrencyPolicy,
    artifact_service: Any | None,
    runtime_metrics: Any | None,
    runtime_registry: Any | None,
) -> dict[str, Any]:
    return {
        "active_tool_runs": active_tool_runs_table_section(
            facts.active_runs,
            tools=facts.tools,
            assignment_by_run=facts.assignment_by_run,
            run_contexts=facts.run_contexts,
            now=facts.now,
        ),
        "tool_queue_runs": tool_queue_runs_section(
            facts.waiting_runs,
            active_runs=facts.active_runs,
            tools=facts.tools,
            workers=facts.workers,
            assignments=facts.assignments,
            assignment_by_run=facts.assignment_by_run,
            concurrency_policy=concurrency_policy,
            now=facts.now,
        ),
        "tool_waiting_io": tool_waiting_io_section(
            facts.waiting_runs,
            active_runs=facts.active_runs,
            tools=facts.tools,
            workers=facts.workers,
            assignments=facts.assignments,
            assignment_by_run=facts.assignment_by_run,
            concurrency_policy=concurrency_policy,
            now=facts.now,
        ),
        "tool_runs": tool_runs_table_section(
            facts.visible_tool_runs,
            tools=facts.tools,
            assignment_by_run=facts.assignment_by_run,
            artifact_service=artifact_service,
            run_contexts=facts.run_contexts,
            now=facts.now,
            total_count=len(facts.filtered_tool_runs),
            empty_state=tool_page_runs_empty_state(facts.query),
        ),
        "tool_queue": tool_queue_section(
            facts.waiting_runs,
            active_runs=facts.active_runs,
            tools=facts.tools,
            workers=facts.workers,
            assignments=facts.assignments,
            assignment_by_run=facts.assignment_by_run,
            concurrency_policy=concurrency_policy,
            now=facts.now,
        ),
        "capability_limits": capability_limits_section(
            tools=facts.tools,
            runs=facts.runs,
            workers=facts.workers,
            assignments=facts.assignments,
            concurrency_policy=concurrency_policy,
            now=facts.now,
        ),
        "provider_limits": provider_limits_section(
            tools=facts.tools,
            runs=facts.runs,
            workers=facts.workers,
            assignments=facts.assignments,
            concurrency_policy=concurrency_policy,
            runtime_metrics=runtime_metrics,
            runtime_registry=runtime_registry,
            now=facts.now,
        ),
        "provider_history": facts.provider_history,
        "run_blockers": run_blockers_section(
            facts.active_runs,
            tools=facts.tools,
            workers=facts.workers,
            assignments=facts.assignments,
            assignment_by_run=facts.assignment_by_run,
            concurrency_policy=concurrency_policy,
            now=facts.now,
        ),
        "inline_risk": inline_risk_section(
            facts.runs,
            active_runs=facts.active_runs,
            assignment_by_run=facts.assignment_by_run,
            now=facts.now,
        ),
        "recent_artifacts": recent_tool_artifacts_section(
            facts.runs,
            tools=facts.tools,
            artifact_service=artifact_service,
        ),
        "tool_lifecycle_events": tool_lifecycle_events_section(
            facts.observed_events,
            tools=facts.tools,
            runs=facts.runs,
        ),
        "strategies": strategies_section(facts.runs),
    }
