from __future__ import annotations

from datetime import datetime, timedelta, timezone

from crxzipple.modules.llm.domain import (
    LlmApiFamily,
    LlmCapability,
    LlmContinuationReason,
    LlmContinuationSignal,
    LlmErrorPayload,
    LlmInputItem,
    LlmInputItemKind,
    LlmInvocation,
    LlmInvocationStatus,
    LlmMessage,
    LlmMessagePhase,
    LlmMessageRole,
    LlmProfile,
    LlmProviderKind,
    LlmResponseItem,
    LlmResponseItemKind,
    LlmResult,
    LlmUsage,
    ToolCallIntent,
)
from crxzipple.modules.operations.application.observation_models import OperationsObservedEvent
from crxzipple.modules.operations.application.read_models.llm_invocation_tables import (
    failed_invocations_section,
    recent_invocations_section,
    streaming_requests_section,
)


def _profile(profile_id: str = "openai.codex") -> LlmProfile:
    return LlmProfile(
        id=profile_id,
        provider=LlmProviderKind.OPENAI,
        api_family=LlmApiFamily.OPENAI_RESPONSES,
        model_name="gpt-5",
        capabilities=(LlmCapability.STREAMING,),
    )


def _invocation(
    invocation_id: str,
    *,
    status: LlmInvocationStatus,
    created_at: datetime,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
) -> LlmInvocation:
    return LlmInvocation(
        id=invocation_id,
        llm_id="openai.codex",
        messages=(LlmMessage(role=LlmMessageRole.USER, content="hello"),),
        input_items=(
            LlmInputItem(
                kind=LlmInputItemKind.MESSAGE,
                payload={"role": "user", "content": "hello"},
            ),
        ),
        status=status,
        result=LlmResult(
            text="done",
            tool_calls=(ToolCallIntent(id="call-1", name="exec", arguments={}),),
            usage=LlmUsage(input_tokens=10, output_tokens=5, total_tokens=15),
            finish_reason="tool_calls",
        ),
        response_items=(
            LlmResponseItem(
                id=f"{invocation_id}-message",
                invocation_id=invocation_id,
                sequence_no=1,
                kind=LlmResponseItemKind.ASSISTANT_MESSAGE,
                role=LlmMessageRole.ASSISTANT,
                phase=LlmMessagePhase.COMMENTARY,
                content_payload={"text": "working"},
            ),
        ),
        continuation=LlmContinuationSignal(
            end_turn=False,
            needs_follow_up=True,
            reason=LlmContinuationReason.TOOL_CALL,
        ),
        request_metadata={
            "estimated_provider_input_tokens": 100,
            "draft_input_session_item_count": 3,
            "draft_input_estimated_tokens": 40,
        },
        provider_request_payload_preview={
            "render_report": {
                "tool_protocol": {
                    "replay_orphan_tool_output_count": 1,
                    "dropped_missing_tool_output_count": 2,
                },
            },
        },
        created_at=created_at,
        started_at=started_at,
        completed_at=completed_at,
    )


def _event(
    event_id: str,
    *,
    invocation_id: str,
    event_name: str = "llm.stream_delta_observed",
) -> OperationsObservedEvent:
    return OperationsObservedEvent(
        id=event_id,
        cursor=event_id,
        topic=f"events.named.{event_name}",
        event_name=event_name,
        module="llm",
        owner="llm",
        kind="fact",
        level="info",
        status="observed",
        entity_id=invocation_id,
        run_id=None,
        trace_id=None,
        source_event_name=event_name,
        occurred_at=datetime(2026, 6, 21, 12, tzinfo=timezone.utc),
        payload={"invocation_id": invocation_id, "streaming": True},
    )


def test_streaming_requests_section_projects_active_stream_rows() -> None:
    now = datetime(2026, 6, 21, 12, tzinfo=timezone.utc)
    invocation = _invocation(
        "inv-stream",
        status=LlmInvocationStatus.RUNNING,
        created_at=now - timedelta(seconds=30),
        started_at=now - timedelta(seconds=30),
    )

    section = streaming_requests_section(
        [invocation],
        profiles_by_id={"openai.codex": _profile()},
        events_by_invocation={"inv-stream": (_event("event-1", invocation_id="inv-stream"),)},
        run_contexts={
            "inv-stream": {
                "run_id": "run-1",
                "chain_id": "chain-1",
                "step_id": "step-1",
                "trace_id": "trace-1",
            },
        },
        now=now,
    )

    row = section.rows[0].cells
    assert section.id == "streaming_requests"
    assert row["provider_model"] == "openai / gpt-5"
    assert row["status"] == "Streaming"
    assert row["duration"] == "30s"
    assert row["tokens"] == "15"
    assert row["events"] == "1"
    assert row["run_id"] == "run-1"


def test_recent_invocations_section_projects_provider_and_response_diagnostics() -> None:
    now = datetime(2026, 6, 21, 12, tzinfo=timezone.utc)
    invocation = _invocation(
        "inv-recent",
        status=LlmInvocationStatus.SUCCEEDED,
        created_at=now,
        started_at=now - timedelta(seconds=5),
        completed_at=now,
    )

    section = recent_invocations_section(
        [invocation],
        profiles_by_id={"openai.codex": _profile()},
        observed_events=(_event("event-stream", invocation_id="inv-recent"),),
        events_by_invocation={"inv-recent": (_event("event-delta", invocation_id="inv-recent"),)},
        run_contexts={"inv-recent": {"assistant_progress_item_count": "2"}},
        total_count=1,
        empty_state="empty",
    )

    row = section.rows[0].cells
    assert row["provider_model"] == "openai / gpt-5"
    assert row["status"] == "Succeeded"
    assert row["streaming"] == "Completed"
    assert row["tokens"] == "15"
    assert row["provider_input_tokens"] == "100"
    assert row["draft_input_items"] == "3"
    assert row["draft_input_tokens"] == "40"
    assert row["tool_protocol"] == "3"
    assert row["response_text"] == "4 chars"
    assert row["tool_calls"] == "1"
    assert row["response_items"] == "1"
    assert row["continuation"] == "tool_call"
    assert row["end_turn"] == "No"
    assert row["progress"] == "2"


def test_failed_invocations_section_projects_error_rows() -> None:
    now = datetime(2026, 6, 21, 12, tzinfo=timezone.utc)
    invocation = _invocation(
        "inv-failed",
        status=LlmInvocationStatus.FAILED,
        created_at=now,
        started_at=now - timedelta(seconds=8),
        completed_at=now,
    )
    invocation.error = LlmErrorPayload(message="boom", code="provider_error")

    section = failed_invocations_section(
        [invocation],
        profiles_by_id={"openai.codex": _profile()},
        observed_events=(_event("event-stream", invocation_id="inv-failed"),),
        events_by_invocation={},
        run_contexts={"inv-failed": {"trace_id": "trace-failed"}},
        total_count=1,
        empty_state="empty",
    )

    row = section.rows[0].cells
    assert section.id == "failed_invocations"
    assert row["provider_model"] == "openai / gpt-5"
    assert row["status"] == "Failed"
    assert row["streaming"] == "Failed"
    assert row["error_code"] == "provider_error"
    assert row["trace"] == "trace-failed"
