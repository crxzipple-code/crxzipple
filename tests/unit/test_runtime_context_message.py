from crxzipple.app.integration.context_workspace_orchestration.runtime_context_message import (
    build_runtime_context_message,
)


def test_runtime_context_message_includes_step_budget_guidance() -> None:
    message = build_runtime_context_message(
        agent_id="assistant",
        llm_id="test-llm",
        home_dir=None,
        workspace_dir="/workspace",
        available_tool_ids=("exec",),
        current_step=29,
        max_steps=30,
        remaining_steps=1,
        step_budget_status="finalize_now",
    )

    assert "- Step budget: 29/30 used; 1 remaining; status=finalize_now" in message
    assert "finish with the best supported answer now" in message


def test_runtime_context_message_constrained_budget_prefers_convergence() -> None:
    message = build_runtime_context_message(
        agent_id="assistant",
        llm_id="test-llm",
        home_dir=None,
        workspace_dir="/workspace",
        available_tool_ids=("exec",),
        current_step=24,
        max_steps=30,
        remaining_steps=6,
        step_budget_status="constrained",
    )

    assert "- Step budget: 24/30 used; 6 remaining; status=constrained" in message
    assert "Before any new probe, identify the specific missing fact" in message
    assert "otherwise summarize the current evidence and answer" in message


def test_runtime_context_message_critical_budget_avoids_new_branches() -> None:
    message = build_runtime_context_message(
        agent_id="assistant",
        llm_id="test-llm",
        home_dir=None,
        workspace_dir="/workspace",
        available_tool_ids=("exec",),
        current_step=27,
        max_steps=30,
        remaining_steps=3,
        step_budget_status="critical",
    )

    assert "- Step budget: 27/30 used; 3 remaining; status=critical" in message
    assert "when available evidence can support an answer" in message
    assert "unless a specific missing fact is required" in message
