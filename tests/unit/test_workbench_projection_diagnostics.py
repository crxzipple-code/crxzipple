from __future__ import annotations

from crxzipple.modules.workbench.application.projection_diagnostics import (
    workbench_run_owner_fact_sources,
)


def test_workbench_run_projection_declares_owner_fact_sources() -> None:
    sources = workbench_run_owner_fact_sources()

    modules = {source.module for source in sources}
    assert modules == {
        "agent",
        "artifacts",
        "llm",
        "orchestration",
        "session",
        "tool",
    }
    orchestration_source = next(
        source for source in sources if source.module == "orchestration"
    )
    assert orchestration_source.read_path == "OrchestrationRunQueryPort"
    assert "execution_step_items" in orchestration_source.facts
    assert "approval_requests" in orchestration_source.facts
    llm_source = next(source for source in sources if source.module == "llm")
    assert llm_source.read_path == "WorkbenchLlmQueryPort"
    assert "response_items" in llm_source.facts
