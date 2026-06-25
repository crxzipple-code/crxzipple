from __future__ import annotations

from datetime import datetime, timedelta, timezone

from crxzipple.modules.llm.domain import (
    LlmApiFamily,
    LlmInputItem,
    LlmInputItemKind,
    LlmInvocation,
    LlmInvocationStatus,
    LlmMessage,
    LlmMessageRole,
    LlmProfile,
    LlmProviderKind,
    LlmResult,
    LlmUsage,
)
from crxzipple.modules.operations.application.read_models.llm_usage_sections import (
    context_pressure_section,
    invocation_rate_section,
    latency_section,
    token_usage_section,
)


def _profile(profile_id: str, *, context_window_tokens: int = 100) -> LlmProfile:
    return LlmProfile(
        id=profile_id,
        provider=LlmProviderKind.OPENAI,
        api_family=LlmApiFamily.OPENAI_RESPONSES,
        model_name="gpt-5",
        context_window_tokens=context_window_tokens,
    )


def _invocation(
    invocation_id: str,
    *,
    llm_id: str = "openai.gpt",
    status: LlmInvocationStatus = LlmInvocationStatus.SUCCEEDED,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
    result: LlmResult | None = None,
    request_metadata: dict[str, object] | None = None,
) -> LlmInvocation:
    created_at = started_at or datetime(2026, 6, 21, 12, tzinfo=timezone.utc)
    return LlmInvocation(
        id=invocation_id,
        llm_id=llm_id,
        status=status,
        messages=(LlmMessage(role=LlmMessageRole.USER, content="hello"),),
        input_items=(
            LlmInputItem(
                kind=LlmInputItemKind.MESSAGE,
                payload={"role": "user", "content": "hello"},
            ),
        ),
        result=result,
        request_metadata=dict(request_metadata or {}),
        created_at=created_at,
        started_at=started_at,
        completed_at=completed_at,
    )


def test_latency_section_groups_average_duration_by_provider() -> None:
    started = datetime(2026, 6, 21, 12, tzinfo=timezone.utc)
    invocations = [
        _invocation(
            "one",
            started_at=started,
            completed_at=started + timedelta(seconds=2),
        ),
        _invocation(
            "two",
            started_at=started,
            completed_at=started + timedelta(seconds=4),
        ),
        _invocation(
            "failed",
            status=LlmInvocationStatus.FAILED,
            started_at=started,
            completed_at=started + timedelta(seconds=10),
        ),
    ]

    section = latency_section(
        invocations,
        profiles_by_id={"openai.gpt": _profile("openai.gpt")},
    )

    assert section.id == "latency"
    assert section.total == 3000
    assert section.segments[0].id == "openai"
    assert section.segments[0].value == 3000


def test_token_usage_section_splits_usage_categories() -> None:
    invocation = _invocation(
        "tokens",
        result=LlmResult(
            usage=LlmUsage(
                input_tokens=10,
                output_tokens=7,
                reasoning_tokens=2,
                total_tokens=25,
            ),
        ),
    )

    section = token_usage_section([invocation])

    assert section.id == "token_usage"
    assert section.total == 25
    assert {segment.id: segment.value for segment in section.segments} == {
        "input": 10,
        "output": 7,
        "reasoning": 2,
        "unclassified": 6,
    }


def test_invocation_rate_section_counts_statuses_in_stable_order() -> None:
    invocations = [
        _invocation("running", status=LlmInvocationStatus.RUNNING),
        _invocation("succeeded", status=LlmInvocationStatus.SUCCEEDED),
        _invocation("failed", status=LlmInvocationStatus.FAILED),
    ]

    section = invocation_rate_section(invocations)

    assert section.id == "invocation_rate"
    assert [segment.id for segment in section.segments] == [
        "running",
        "succeeded",
        "failed",
    ]
    assert {segment.id: segment.tone for segment in section.segments}["failed"] == "danger"


def test_context_pressure_section_uses_usage_or_provider_input_metadata() -> None:
    profile = _profile("openai.gpt", context_window_tokens=100)
    invocations = [
        _invocation(
            "normal",
            result=LlmResult(usage=LlmUsage(input_tokens=50, output_tokens=1)),
        ),
        _invocation(
            "elevated",
            request_metadata={"estimated_provider_input_tokens": 85},
        ),
        _invocation(
            "high",
            request_metadata={"estimated_provider_input_tokens": 95},
        ),
    ]

    section = context_pressure_section(
        invocations,
        profiles_by_id={"openai.gpt": profile},
    )

    assert section.id == "context_pressure"
    assert {segment.id: segment.value for segment in section.segments} == {
        "normal": 1,
        "elevated": 1,
        "high": 1,
    }
