from __future__ import annotations

from typing import Any, Mapping

from crxzipple.modules.operations.application.observation_models import OperationsObservedEvent
from crxzipple.modules.operations.application.read_models.models import (
    OperationsOwnerFactSourceModel,
    OperationsProjectionDiagnosticsModel,
)
from crxzipple.modules.tool.domain import (
    Tool,
    ToolRun,
    ToolRunAssignment,
    ToolWorkerRegistration,
)


def tool_projection_diagnostics(
    *,
    tools: list[Tool],
    runs: list[ToolRun],
    workers: list[ToolWorkerRegistration],
    assignments: list[ToolRunAssignment],
    sources: tuple[Any, ...],
    functions: tuple[Any, ...],
    provider_backends: tuple[Any, ...],
    discovery_runs_by_source: Mapping[str, tuple[Any, ...]],
    observed_events: tuple[OperationsObservedEvent, ...],
    owner_call_count: int,
    elapsed_ms: float,
    freshness_at: str,
) -> OperationsProjectionDiagnosticsModel:
    discovery_count = sum(len(items) for items in discovery_runs_by_source.values())
    return OperationsProjectionDiagnosticsModel(
        module="tool",
        owner_sources=(
            OperationsOwnerFactSourceModel(
                module="tool",
                facts=(
                    "tools",
                    "tool_runs",
                    "tool_workers",
                    "tool_run_assignments",
                    "tool_sources",
                    "tool_functions",
                    "provider_backends",
                    "source_discovery_runs",
                ),
                read_path="OperationsToolQueryPort",
            ),
            OperationsOwnerFactSourceModel(
                module="orchestration",
                facts=("execution_step_items",),
                read_path="OrchestrationRunQueryPort",
            ),
            OperationsOwnerFactSourceModel(
                module="artifacts",
                facts=("artifact_refs",),
                read_path="OperationsArtifactReadPort",
            ),
            OperationsOwnerFactSourceModel(
                module="operations",
                facts=("observed_events",),
                read_path="OperationsObservationReadPort",
            ),
        ),
        owner_call_count=owner_call_count,
        processed_item_count=(
            len(tools)
            + len(runs)
            + len(workers)
            + len(assignments)
            + len(sources)
            + len(functions)
            + len(provider_backends)
            + discovery_count
            + len(observed_events)
        ),
        elapsed_ms=round(elapsed_ms, 3),
        freshness_at=freshness_at,
    )
