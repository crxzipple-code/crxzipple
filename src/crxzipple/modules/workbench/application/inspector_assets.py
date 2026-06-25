from __future__ import annotations

from typing import Any

from crxzipple.modules.orchestration.domain import OrchestrationRun
from crxzipple.modules.workbench.application.action_projection import (
    dedupe_linked_entities,
    linked_entity,
    trace_route,
)
from crxzipple.modules.workbench.application.projection_helpers import optional_text
from crxzipple.modules.workbench.application.tool_artifact_projection import (
    tool_artifacts,
)


def linked_assets_for_run(
    run: OrchestrationRun,
    *,
    display_tool_runs: tuple[Any, ...],
    llm_invocations: tuple[Any, ...],
    cover_artifact: Any | None,
    trace: Any,
) -> tuple[Any, ...]:
    entities: list[Any] = [
        linked_entity(
            entity_type="run",
            entity_id=run.id,
            label="Run",
            owner="orchestration",
            route=trace_route(trace),
            trace=trace,
        ),
    ]
    for invocation in llm_invocations:
        invocation_id = optional_text(getattr(invocation, "id", None))
        if invocation_id is None:
            continue
        entities.append(
            linked_entity(
                entity_type="llm_invocation",
                entity_id=invocation_id,
                label="LLM invocation",
                owner="llm",
                route=trace_route(trace),
                trace=trace,
            ),
        )
    for display_tool_run in display_tool_runs:
        tool_run = display_tool_run.tool_run
        entities.append(
            linked_entity(
                entity_type="tool_run",
                entity_id=tool_run.id,
                label=tool_run.tool_id,
                owner="tool",
                route=trace_route(trace),
                trace=trace,
            ),
        )
        for artifact in tool_artifacts(tool_run, artifact_query=None):
            entities.append(
                linked_entity(
                    entity_type="artifact",
                    entity_id=artifact.artifact_id,
                    label=artifact.name,
                    owner="artifacts",
                    route=trace_route(trace),
                    trace=trace,
                ),
            )
    if cover_artifact is not None:
        entities.append(
            linked_entity(
                entity_type="artifact",
                entity_id=cover_artifact.artifact_id,
                label=cover_artifact.name,
                owner="artifacts",
                route=trace_route(trace),
                trace=trace,
            ),
        )
    return dedupe_linked_entities(tuple(entities))
