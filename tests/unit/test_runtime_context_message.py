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
