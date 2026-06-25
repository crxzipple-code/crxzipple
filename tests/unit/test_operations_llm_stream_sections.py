from __future__ import annotations

from datetime import datetime, timedelta, timezone

from crxzipple.modules.llm.domain import (
    LlmApiFamily,
    LlmCapability,
    LlmInputItem,
    LlmInputItemKind,
    LlmInvocation,
    LlmInvocationStatus,
    LlmMessage,
    LlmMessageRole,
    LlmProfile,
    LlmProviderKind,
)
from crxzipple.modules.operations.application.observation_models import OperationsObservedEvent
from crxzipple.modules.operations.application.read_models.llm_stream_sections import (
    stream_health_section,
)


def _profile(profile_id: str = "openai.gpt") -> LlmProfile:
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
    started_at: datetime,
) -> LlmInvocation:
    return LlmInvocation(
        id=invocation_id,
        llm_id="openai.gpt",
        status=status,
        messages=(LlmMessage(role=LlmMessageRole.USER, content="hello"),),
        input_items=(
            LlmInputItem(
                kind=LlmInputItemKind.MESSAGE,
                payload={"role": "user", "content": "hello"},
            ),
        ),
        created_at=started_at,
        started_at=started_at,
    )


def _event() -> OperationsObservedEvent:
    return OperationsObservedEvent(
        id="delta",
        cursor="delta",
        topic="events.named.llm.stream_delta_observed",
        event_name="llm.stream_delta_observed",
        module="llm",
        owner="llm",
        kind="fact",
        level="info",
        status="observed",
        entity_id="invocation-running",
        run_id=None,
        trace_id=None,
        source_event_name="llm.stream_delta_observed",
        occurred_at=datetime(2026, 6, 21, 12, tzinfo=timezone.utc),
        payload={},
    )


def test_stream_health_section_summarizes_streaming_invocations_and_delta_events() -> None:
    now = datetime(2026, 6, 21, 12, tzinfo=timezone.utc)
    running = _invocation(
        "running",
        status=LlmInvocationStatus.RUNNING,
        started_at=now - timedelta(seconds=130),
    )
    succeeded = _invocation(
        "succeeded",
        status=LlmInvocationStatus.SUCCEEDED,
        started_at=now - timedelta(seconds=10),
    )

    section = stream_health_section(
        [_profile()],
        streaming_invocations=[running, succeeded],
        observed_events=(_event(),),
        now=now,
    )

    values = {item.label: item.value for item in section.items}
    tones = {item.label: item.tone for item in section.items}
    assert section.id == "stream_health"
    assert values["Active Streams"] == "1"
    assert values["Completed Streams"] == "1"
    assert values["Failed Streams"] == "0"
    assert values["Delta Events"] == "1"
    assert values["Longest Active"] == "2m 10s"
    assert values["Stream-capable Profiles"] == "1"
    assert tones["Longest Active"] == "warning"
