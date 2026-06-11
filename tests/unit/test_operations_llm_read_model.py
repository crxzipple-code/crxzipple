from __future__ import annotations

from types import SimpleNamespace

from crxzipple.modules.llm.domain import (
    LlmApiFamily,
    LlmInvocation,
    LlmInvocationStatus,
    LlmMessage,
    LlmMessageRole,
    LlmProfile,
    LlmProviderKind,
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
            "direct_transcript_session_message_count": 3,
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
                        "message_count": 3,
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
    )
    provider = LlmOperationsReadModelProvider(
        llm_service=_FakeLlmQueryService(profile, invocation),
        run_query=_FakeRunQuery(invocation.id),
    )

    page = provider.page()

    row = page.recent_invocations.rows[0].cells
    assert row["provider_prompt_tokens"] == "1800"
    assert row["direct_messages"] == "3"
    assert row["direct_tokens"] == "120"
    assert row["tool_protocol"] == "1"
    assert row["response_text"] == "9 chars"
    assert row["tool_calls"] == "1"
    assert row["progress"] == "1"

    detail = page.invocation_details[0]
    summary = {item.label: item.value for item in detail.summary}
    assert summary["Response Text"] == "9 chars"
    assert summary["Tool Calls"] == "1"
    assert summary["Assistant Progress Messages"] == "1"
    assert summary["Assistant Progress IDs"] == "message-progress"
    request_context = {item.label: item.value for item in detail.request_context}
    assert request_context["Provider Prompt Tokens"] == "1800"
    assert request_context["Direct Transcript Messages"] == "3"
    assert request_context["Direct Transcript Tokens"] == "120"
    assert request_context["Tool Protocol Calls"] == "1"
    assert request_context["Artifact Tokens"] == "40"
    assert request_context["Artifact Blocks"] == "2"
    assert request_context["Artifact Omitted"] == "1"
    assert request_context["Direct Sequence Range"] == "session-budget:5-9 (3)"
    assert request_context["Context Snapshot"] == "ctxsnap-budget"

    assert page.context_pressure.total == 1
    pressure = {segment.id: segment.value for segment in page.context_pressure.segments}
    assert pressure["high"] == 1


class _FakeLlmQueryService:
    def __init__(self, profile: LlmProfile, invocation: LlmInvocation) -> None:
        self._profile = profile
        self._invocation = invocation

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
                    "assistant_progress_message_ids": ["message-progress"],
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
