from __future__ import annotations

from crxzipple.modules.operations.application.read_models.llm_projection_diagnostics import (
    llm_projection_diagnostics,
)


def test_llm_projection_diagnostics_declares_owner_sources_and_cost() -> None:
    diagnostics = llm_projection_diagnostics(
        profiles=[object()],  # type: ignore[list-item]
        invocations=[object(), object()],  # type: ignore[list-item]
        observed_events=(object(),),  # type: ignore[arg-type]
        resolver_events=(object(), object()),  # type: ignore[arg-type]
        response_events_by_invocation={
            "invocation-1": (object(), object()),
            "invocation-2": (object(),),
        },
        owner_call_count=11,
        elapsed_ms=1.23456,
        freshness_at="2026-06-21T00:00:00Z",
    )

    assert diagnostics.module == "llm"
    assert diagnostics.owner_call_count == 11
    assert diagnostics.processed_item_count == 9
    assert diagnostics.elapsed_ms == 1.235
    assert diagnostics.freshness_at == "2026-06-21T00:00:00Z"
    assert {
        source.module
        for source in diagnostics.owner_sources
    } == {"llm", "access", "orchestration", "operations"}
    llm_source = diagnostics.owner_sources[0]
    assert llm_source.read_path == "OperationsLlmQueryPort"
    assert "response_events" in llm_source.facts
