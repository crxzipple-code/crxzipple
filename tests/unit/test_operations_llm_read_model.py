from __future__ import annotations

from types import SimpleNamespace

from crxzipple.modules.llm.domain import (
    LlmApiFamily,
    LlmContinuationReason,
    LlmContinuationSignal,
    LlmInvocation,
    LlmInvocationStatus,
    LlmMessage,
    LlmMessagePhase,
    LlmMessageRole,
    LlmProfile,
    LlmProviderKind,
    LlmResponseEvent,
    LlmResponseEventType,
    LlmResponseItem,
    LlmResponseItemKind,
    LlmResult,
    ToolCallIntent,
)
from crxzipple.modules.operations.application.read_models.llm import (
    LlmOperationsReadModelProvider,
)


def test_llm_operations_page_exposes_prompt_transcript_budget_metadata() -> None:
    profile = LlmProfile(
        id="openai.gpt-budget",
        provider=LlmProviderKind.OPENAI,
        api_family=LlmApiFamily.OPENAI_RESPONSES,
        model_name="gpt-5",
        context_window_tokens=2_000,
        credential_binding_id="openai-api-key",
    )
    invocation = LlmInvocation(
        id="llm-invocation-budget",
        llm_id=profile.id,
        messages=(
            LlmMessage(
                role=LlmMessageRole.USER,
                content="continue",
            ),
        ),
        request_metadata={
            "context_render_snapshot_id": "ctxsnap-budget",
            "estimated_provider_prompt_tokens": 1_800,
                "direct_session_item_count": 3,
            "direct_transcript_estimated_tokens": 120,
            "artifact_content_estimated_tokens": 40,
            "artifact_content_block_count": 2,
            "artifact_content_omitted_count": 1,
            "direct_tool_protocol_call_ids": ["call-weather-1"],
            "direct_transcript_sequence_range": {
                "sessions": [
                    {
                        "session_id": "session-budget",
                        "from_sequence_no": 5,
                        "to_sequence_no": 9,
                            "item_count": 3,
                    },
                ],
            },
            "llm_request_policy": {
                "resolution_trace": [
                    {
                        "field": "provider_options.max_output_tokens",
                        "source": "settings.llm_request_defaults",
                        "status": "applied",
                        "value": 800,
                    },
                    {
                        "field": "reasoning_config.summary",
                        "source": "agent_profile.llm_policy",
                        "status": "downgraded",
                        "value": "auto",
                        "reason": "llm_capability_not_supported",
                    },
                ],
            },
        },
        status=LlmInvocationStatus.SUCCEEDED,
        result=LlmResult(
            text="我先检查页面状态。",
            tool_calls=(
                ToolCallIntent(
                    id="call-browser",
                    name="browser.snapshot",
                    arguments={},
                ),
            ),
            finish_reason="tool_calls",
        ),
        response_items=(
            LlmResponseItem(
                id="item-response-message",
                invocation_id="llm-invocation-budget",
                sequence_no=1,
                kind=LlmResponseItemKind.ASSISTANT_MESSAGE,
                role=LlmMessageRole.ASSISTANT,
                phase=LlmMessagePhase.COMMENTARY,
                content_payload={"text": "我先检查页面状态。"},
                provider_payload={"type": "message"},
                provider_item_type="message",
                model_visible=True,
                user_visible=True,
            ),
            LlmResponseItem(
                id="item-response-tool",
                invocation_id="llm-invocation-budget",
                sequence_no=2,
                kind=LlmResponseItemKind.TOOL_CALL,
                role=LlmMessageRole.ASSISTANT,
                content_payload={"tool_name": "browser.snapshot"},
                provider_payload={"type": "function_call"},
                provider_item_type="function_call",
                call_id="call-browser",
                tool_name="browser.snapshot",
                model_visible=True,
                user_visible=False,
            ),
        ),
        continuation=LlmContinuationSignal(
            end_turn=False,
            needs_follow_up=True,
            reason=LlmContinuationReason.TOOL_CALL,
            provider_payload={"status": "requires_action"},
        ),
        provider_request_payload_preview={
            "has_previous_response_id": True,
            "previous_response_id": "resp_previous",
            "input_item_types": ["function_call_output"],
            "tool_count": 3,
            "option_summary": {
                "parallel_tool_calls": True,
                "prompt_cache_key": "crxzipple:assistant:session:budget",
                "service_tier": "priority",
                "text": {"verbosity": "low"},
            },
        },
    )
    response_events = (
        LlmResponseEvent(
            id="event-response-item-started",
            invocation_id=invocation.id,
            sequence_no=1,
            type=LlmResponseEventType.ITEM_STARTED,
            item_id="item-response-tool",
            delta_payload={"provider_event_type": "response.output_item.added"},
            provider_payload={"type": "response.output_item.added"},
        ),
        LlmResponseEvent(
            id="event-response-tool-delta",
            invocation_id=invocation.id,
            sequence_no=2,
            type=LlmResponseEventType.TOOL_ARGUMENT_DELTA,
            item_id="item-response-tool",
            delta_payload={"delta": "{}"},
            provider_payload={"type": "response.function_call_arguments.delta"},
        ),
    )
    provider = LlmOperationsReadModelProvider(
        llm_service=_FakeLlmQueryService(profile, invocation, response_events),
        run_query=_FakeRunQuery(invocation.id),
    )

    page = provider.page()

    row = page.recent_invocations.rows[0].cells
    assert row["provider_prompt_tokens"] == "1800"
    assert row["direct_items"] == "3"
    assert row["direct_tokens"] == "120"
    assert row["tool_protocol"] == "1"
    assert row["response_text"] == "9 chars"
    assert row["tool_calls"] == "1"
    assert row["response_items"] == "2"
    assert row["continuation"] == "tool_call"
    assert row["end_turn"] == "No"
    assert row["progress"] == "1"

    detail = page.invocation_details[0]
    summary = {item.label: item.value for item in detail.summary}
    assert summary["Response Text"] == "9 chars"
    assert summary["Tool Calls"] == "1"
    assert summary["Response Items"] == "2"
    assert summary["Response Events"] == "2"
    assert summary["Continuation"] == "tool_call"
    assert summary["End Turn"] == "No"
    assert summary["Assistant Progress Items"] == "1"
    assert summary["Assistant Progress IDs"] == "item-progress"
    request_context = {item.label: item.value for item in detail.request_context}
    assert request_context["Provider Prompt Tokens"] == "1800"
    assert request_context["Direct Transcript Items"] == "3"
    assert request_context["Direct Transcript Tokens"] == "120"
    assert request_context["Tool Protocol Calls"] == "1"
    assert request_context["Artifact Tokens"] == "40"
    assert request_context["Artifact Blocks"] == "2"
    assert request_context["Artifact Omitted"] == "1"
    assert request_context["Direct Sequence Range"] == "session-budget:5-9 (3)"
    assert request_context["Context Snapshot"] == "ctxsnap-budget"
    assert request_context["Provider Continuation"] == (
        "previous_response_id=resp_previous"
    )
    assert request_context["Provider Input Items"] == "function_call_output"
    assert request_context["Provider Tool Count"] == "3"
    assert request_context["Provider Options"] == (
        "parallel_tool_calls, prompt_cache_key, service_tier, text"
    )
    assert detail.policy_trace.total == 2
    assert detail.policy_trace.rows[0].cells["source"] == (
        "settings.llm_request_defaults"
    )
    assert detail.policy_trace.rows[1].tone == "warning"
    assert detail.policy_trace.rows[1].cells["reason"] == (
        "llm_capability_not_supported"
    )
    assert detail.response_items.total == 2
    assert detail.response_items.rows[1].cells["tool"] == "browser.snapshot"
    assert detail.response_events.total == 2
    assert detail.response_events.rows[1].cells["provider_event"] == (
        "response.function_call_arguments.delta"
    )

    assert page.context_pressure.total == 1
    pressure = {segment.id: segment.value for segment in page.context_pressure.segments}
    assert pressure["high"] == 1


class _FakeLlmQueryService:
    def __init__(
        self,
        profile: LlmProfile,
        invocation: LlmInvocation,
        response_events: tuple[LlmResponseEvent, ...] = (),
    ) -> None:
        self._profile = profile
        self._invocation = invocation
        self._response_events = response_events

    def list_profiles(self) -> list[LlmProfile]:
        return [self._profile]

    def list_invocations(
        self,
        *,
        llm_id: str | None = None,
        limit: int = 50,
    ) -> list[LlmInvocation]:
        if llm_id is not None and llm_id != self._profile.id:
            return []
        return [self._invocation][:limit]

    def list_response_events(
        self,
        invocation_id: str,
        *,
        limit: int | None = None,
        after_sequence: int | None = None,
    ) -> list[LlmResponseEvent]:
        if invocation_id != self._invocation.id:
            return []
        events = list(self._response_events)
        if after_sequence is not None:
            events = [event for event in events if event.sequence_no > after_sequence]
        if limit is not None:
            events = events[:limit]
        return events


class _FakeRunQuery:
    def __init__(self, invocation_id: str) -> None:
        self._invocation_id = invocation_id

    def find_execution_step_items_by_owner(self, owner):  # noqa: ANN001, ANN201
        if owner.owner_id != self._invocation_id:
            return []
        return [
            SimpleNamespace(
                id="item-llm",
                step_id="step-llm",
                chain_id="chain-1",
                turn_id="run-1",
                status=SimpleNamespace(value="completed"),
                updated_at=None,
                summary_payload={
                    "assistant_progress_item_ids": ["item-progress"],
                    "assistant_progress_text": "我先检查页面状态。",
                    "tool_call_names": ["browser.snapshot"],
                },
            ),
        ]

    def get_execution_step(self, step_id: str):  # noqa: ANN201
        return SimpleNamespace(
            id=step_id,
            kind=SimpleNamespace(value="llm"),
            status=SimpleNamespace(value="completed"),
        )

    def get_run(self, run_id: str):  # noqa: ANN201
        return SimpleNamespace(
            id=run_id,
            metadata={
                "trace_id": "trace-1",
                "session_key": "agent:assistant:main",
            },
        )
