from __future__ import annotations

from crxzipple.modules.orchestration.application.runtime_step_budget_policy import (
    RuntimeStepBudgetPolicy,
)
from crxzipple.modules.orchestration.domain import (
    InboundInstruction,
    OrchestrationRun,
)


def test_runtime_step_budget_policy_reports_available() -> None:
    budget = RuntimeStepBudgetPolicy().for_run(_run(current_step=1, max_steps=20))

    assert budget.remaining_steps == 19
    assert budget.status == "available"
    assert budget.to_payload()["step_budget_status"] == "available"


def test_runtime_step_budget_policy_reports_constrained() -> None:
    budget = RuntimeStepBudgetPolicy().for_run(_run(current_step=14, max_steps=20))

    assert budget.remaining_steps == 6
    assert budget.status == "constrained"


def test_runtime_step_budget_policy_reports_critical() -> None:
    budget = RuntimeStepBudgetPolicy().for_run(_run(current_step=17, max_steps=20))

    assert budget.remaining_steps == 3
    assert budget.status == "critical"


def test_runtime_step_budget_policy_reports_finalize_now() -> None:
    budget = RuntimeStepBudgetPolicy().for_run(_run(current_step=19, max_steps=20))

    assert budget.remaining_steps == 1
    assert budget.status == "finalize_now"


def _run(*, current_step: int, max_steps: int) -> OrchestrationRun:
    run = OrchestrationRun(
        id="run-step-budget",
        inbound_instruction=InboundInstruction(source="test", content="hello"),
    )
    run.current_step = current_step
    run.max_steps = max_steps
    return run
