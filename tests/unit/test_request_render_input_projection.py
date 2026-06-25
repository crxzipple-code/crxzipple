from __future__ import annotations

from crxzipple.app.integration.context_workspace_orchestration.draft_input_projection import (
    draft_current_input_projection,
    merge_projected_input_items,
)
from crxzipple.app.integration.context_workspace_orchestration.request_render_refs import (
    merge_current_inbound_budget_refs,
    request_input_refs,
)
from crxzipple.modules.llm.domain import (
    LlmInputItem,
    LlmInputItemKind,
    LlmMessage,
    LlmMessageRole,
)
from crxzipple.modules.orchestration.application.runtime_llm_request_draft import (
    RuntimeLlmRequestDraft,
)
from crxzipple.modules.orchestration.application.runtime_request_mode import (
    RuntimeRequestMode,
)


def test_approval_resume_projects_session_user_goal_as_current_inbound() -> None:
    draft = RuntimeLlmRequestDraft(
        llm_id="llm.test",
        session_key="session:test",
        active_session_id="active-session",
        messages=(
            LlmMessage(
                role=LlmMessageRole.USER,
                content=[{"type": "text", "text": "Inspect local state."}],
                metadata={
                    "session_item_id": "item-user-1",
                    "session_id": "active-session",
                    "sequence_no": 1,
                    "kind": "user_message",
                    "source_module": "orchestration",
                    "source_kind": "orchestration_run",
                    "source_id": "run-1",
                },
            ),
        ),
        input_items=(
            LlmInputItem(
                kind=LlmInputItemKind.MESSAGE,
                payload={
                    "role": "user",
                    "content": [{"type": "text", "text": "Inspect local state."}],
                },
                source="session_item",
                metadata={
                    "session_item_id": "item-user-1",
                    "session_id": "active-session",
                    "sequence_no": 1,
                    "kind": "user_message",
                    "source_module": "orchestration",
                    "source_kind": "orchestration_run",
                    "source_id": "run-1",
                },
            ),
        ),
        mode=RuntimeRequestMode.APPROVAL_RESUME,
    )

    projected = draft_current_input_projection(draft)

    assert projected == (
        {
            "kind": "message",
            "payload": {
                "role": "user",
                "content": [{"type": "text", "text": "Inspect local state."}],
            },
            "source": "current_inbound",
            "metadata": {
                "session_item_id": "item-user-1",
                "session_id": "active-session",
                "sequence_no": 1,
                "kind": "user_message",
                "source_module": "orchestration",
                "source_kind": "orchestration_run",
                "source_id": "run-1",
                "runtime_request_block_kind": "current_inbound",
            },
        },
    )


def test_current_inbound_is_inserted_before_tool_protocol_replay() -> None:
    current_user = {
        "kind": "message",
        "payload": {
            "role": "user",
            "content": [{"type": "text", "text": "Inspect local state."}],
        },
        "source": "current_inbound",
        "metadata": {
            "session_item_id": "item-user-1",
            "source_module": "orchestration",
            "source_kind": "orchestration_run",
            "source_id": "run-1",
            "runtime_request_block_kind": "current_inbound",
        },
    }
    tool_call = {
        "kind": "function_call",
        "payload": {
            "type": "function_call",
            "call_id": "call-1",
            "name": "exec",
            "arguments": {"cmd": "pwd"},
        },
        "source": "context_slice",
        "metadata": {"tool_call_id": "call-1"},
    }
    tool_output = {
        "kind": "function_call_output",
        "payload": {
            "type": "function_call_output",
            "call_id": "call-1",
            "output": [{"type": "text", "text": "/tmp"}],
        },
        "source": "context_slice",
        "metadata": {"tool_call_id": "call-1"},
    }

    merged = merge_projected_input_items(
        (tool_call, tool_output),
        (current_user,),
    )

    assert [item["kind"] for item in merged] == [
        "message",
        "function_call",
        "function_call_output",
    ]


def test_request_refs_include_current_inbound_budget_ref_for_resume_slice() -> None:
    current_user_ref = {
        "owner_module": "session",
        "owner_kind": "session_item",
        "owner_id": "item-user-1",
        "item_id": "item-user-1",
        "session_id": "active-session",
        "sequence_no": 1,
        "kind": "user_message",
        "role": "user",
        "source_module": "orchestration",
        "source_kind": "orchestration_run",
        "source_id": "run-1",
        "budget_class": "current_inbound",
    }
    tool_ref = {
        "owner_module": "orchestration",
        "owner_kind": "execution_step_item",
        "owner_id": "step-item-1",
        "item_id": "step-item-1",
        "kind": "tool_result",
        "tool_call_id": "call-1",
        "protocol_required": True,
    }

    current_refs = merge_current_inbound_budget_refs(
        [],
        {"included_refs": [current_user_ref]},
        run_id="run-1",
    )
    requested_refs = request_input_refs(
        current_refs,
        (tool_ref,),
        run_id="run-1",
    )

    assert requested_refs == (current_user_ref,)

