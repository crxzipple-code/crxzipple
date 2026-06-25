from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

from crxzipple.modules.llm.domain import (
    LlmInputItem,
    LlmInputItemKind,
    LlmInvocation,
    LlmMessage,
    LlmMessagePhase,
    LlmMessageRole,
    LlmResponseItem,
    LlmResponseItemKind,
)
from crxzipple.modules.operations.application.observation_models import OperationsObservedEvent
from crxzipple.modules.operations.application.read_models.llm_policy_trace_tables import (
    policy_trace_table_for_invocation,
)
from crxzipple.modules.operations.application.read_models.llm_response_event_tables import (
    events_table_for_invocation,
    response_events_table_for_invocation,
)
from crxzipple.modules.operations.application.read_models.llm_response_item_tables import (
    response_items_table_for_invocation,
    response_runtime_mapping_table_for_invocation,
)


def _invocation() -> LlmInvocation:
    return LlmInvocation(
        id="inv-detail-tables",
        llm_id="openai.codex",
        messages=(LlmMessage(role=LlmMessageRole.USER, content="hello"),),
        input_items=(
            LlmInputItem(
                kind=LlmInputItemKind.MESSAGE,
                payload={"role": "user", "content": "hello"},
            ),
        ),
        response_items=(
            LlmResponseItem(
                id="item-message",
                invocation_id="inv-detail-tables",
                sequence_no=1,
                kind=LlmResponseItemKind.ASSISTANT_MESSAGE,
                role=LlmMessageRole.ASSISTANT,
                phase=LlmMessagePhase.COMMENTARY,
                content_payload={"text": "working"},
                provider_payload={"type": "message"},
                provider_item_id="provider-item-message",
                provider_item_type="message",
                provider_replay_candidate=True,
                user_timeline_candidate=True,
            ),
            LlmResponseItem(
                id="item-tool",
                invocation_id="inv-detail-tables",
                sequence_no=2,
                kind=LlmResponseItemKind.TOOL_CALL,
                role=LlmMessageRole.ASSISTANT,
                phase=LlmMessagePhase.COMMENTARY,
                content_payload={"arguments": {"cmd": "pwd"}},
                provider_payload={"type": "function_call"},
                provider_item_id="provider-item-tool",
                provider_item_type="function_call",
                call_id="call-1",
                tool_name="command_exec",
                provider_replay_candidate=True,
                user_timeline_candidate=False,
            ),
        ),
        request_metadata={
            "llm_request_policy": {
                "resolution_trace": [
                    {
                        "field": "model",
                        "source": "profile",
                        "status": "applied",
                        "value": "gpt-5",
                        "reason": "profile default",
                    },
                ],
            },
        },
    )


def test_detail_response_item_and_runtime_mapping_tables() -> None:
    invocation = _invocation()

    response_items = response_items_table_for_invocation(invocation)
    assert response_items.rows[0].cells["kind"] == "assistant_message"
    assert response_items.rows[0].cells["provider_type"] == "message"
    assert response_items.rows[1].cells["tool"] == "command_exec"
    assert response_items.rows[1].cells["call_id"] == "call-1"

    mapping = response_runtime_mapping_table_for_invocation(invocation)
    assert mapping.rows[0].cells["runtime_semantic"] == "runtime.assistant_progress"
    assert mapping.rows[1].cells["runtime_semantic"] == "runtime.assistant_tool_call"
    assert mapping.rows[1].cells["provider_item"] == "provider-item-tool"


def test_detail_policy_response_event_and_observed_event_tables() -> None:
    invocation = _invocation()

    policy = policy_trace_table_for_invocation(invocation)
    assert policy.rows[0].cells["field"] == "model"
    assert policy.rows[0].cells["source"] == "profile"
    assert policy.rows[0].cells["status"] == "applied"

    response_events = response_events_table_for_invocation(
        invocation.id,
        (
            SimpleNamespace(
                id="response-event-1",
                sequence_no=1,
                type="tool_argument_delta",
                item_id="item-tool",
                provider_payload={"type": "response.function_call_arguments.delta"},
                delta_payload={"delta": '{"cmd": "pwd"}'},
            ),
        ),
    )
    assert response_events.rows[0].cells["type"] == "tool_argument_delta"
    assert response_events.rows[0].cells["provider_event"] == (
        "response.function_call_arguments.delta"
    )

    observed_events = events_table_for_invocation(
        invocation.id,
        (
            OperationsObservedEvent(
                id="event-1",
                cursor="event-1",
                topic="events.named.llm.invocation_succeeded",
                event_name="llm.invocation_succeeded",
                module="llm",
                owner="llm",
                kind="fact",
                level="info",
                status="succeeded",
                entity_id=invocation.id,
                run_id=None,
                trace_id=None,
                source_event_name="llm.invocation_succeeded",
                occurred_at=datetime(2026, 6, 21, 12, tzinfo=timezone.utc),
                payload={"invocation_id": invocation.id},
            ),
        ),
    )
    assert observed_events.rows[0].cells["event"] == "llm.invocation_succeeded"
    assert observed_events.rows[0].cells["status"] == "succeeded"
