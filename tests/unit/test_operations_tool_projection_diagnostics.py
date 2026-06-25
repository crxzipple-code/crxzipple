from __future__ import annotations

from crxzipple.modules.operations.application.read_models.tool_projection_diagnostics import (
    tool_projection_diagnostics,
)


def test_tool_projection_diagnostics_declares_owner_sources_and_cost() -> None:
    diagnostics = tool_projection_diagnostics(
        tools=[],
        runs=[],
        workers=[],
        assignments=[],
        sources=(object(),),
        functions=(object(), object()),
        provider_backends=(object(),),
        discovery_runs_by_source={"source-1": (object(), object())},
        observed_events=(),
        owner_call_count=9,
        elapsed_ms=1.23456,
        freshness_at="2026-06-21T00:00:00Z",
    )

    assert diagnostics.module == "tool"
    assert diagnostics.owner_call_count == 9
    assert diagnostics.processed_item_count == 6
    assert diagnostics.elapsed_ms == 1.235
    assert diagnostics.freshness_at == "2026-06-21T00:00:00Z"
    assert {
        source.module
        for source in diagnostics.owner_sources
    } == {"tool", "orchestration", "artifacts", "operations"}
    tool_source = diagnostics.owner_sources[0]
    assert tool_source.read_path == "OperationsToolQueryPort"
    assert "tool_runs" in tool_source.facts
