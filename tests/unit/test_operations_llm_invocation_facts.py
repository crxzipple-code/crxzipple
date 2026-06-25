from __future__ import annotations

from datetime import datetime, timedelta, timezone

from crxzipple.modules.llm.domain import (
    LlmInputItem,
    LlmInputItemKind,
    LlmInvocation,
    LlmMessage,
    LlmMessageRole,
    LlmResult,
    LlmUsage,
)
from crxzipple.modules.operations.application.read_models.llm_invocation_facts import (
    age_label,
    age_seconds,
    duration_label,
    duration_or_age_label,
    duration_seconds,
    invocation_input_tokens,
    invocation_token_total,
    metadata_int,
    metadata_int_label,
    metadata_text_label,
    seconds_label,
    token_total,
)


def _invocation(
    invocation_id: str = "invocation-1",
    *,
    result: LlmResult | None = None,
    request_metadata: dict[str, object] | None = None,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
) -> LlmInvocation:
    return LlmInvocation(
        id=invocation_id,
        llm_id="openai.gpt",
        messages=(LlmMessage(role=LlmMessageRole.USER, content="hello"),),
        input_items=(
            LlmInputItem(
                kind=LlmInputItemKind.MESSAGE,
                payload={"role": "user", "content": "hello"},
            ),
        ),
        result=result,
        request_metadata=dict(request_metadata or {}),
        started_at=started_at,
        completed_at=completed_at,
    )


def test_invocation_token_facts_use_total_or_input_output_fallback() -> None:
    explicit = _invocation(
        "explicit",
        result=LlmResult(usage=LlmUsage(input_tokens=3, output_tokens=4, total_tokens=10)),
    )
    fallback = _invocation(
        "fallback",
        result=LlmResult(usage=LlmUsage(input_tokens=3, output_tokens=4)),
    )

    assert invocation_token_total(explicit) == 10
    assert invocation_token_total(fallback) == 7
    assert invocation_input_tokens(fallback) == 3
    assert token_total([explicit, fallback]) == 17


def test_invocation_metadata_facts_normalize_int_and_text_labels() -> None:
    invocation = _invocation(
        request_metadata={
            "estimated_provider_input_tokens": "120",
            "negative": -3,
            "enabled": True,
            "input_mode": " runtime_transcript ",
        },
    )

    assert metadata_int(invocation, "estimated_provider_input_tokens") == 120
    assert metadata_int(invocation, "negative") == 0
    assert metadata_int(invocation, "enabled") == 1
    assert metadata_int_label(invocation, "estimated_provider_input_tokens") == "120"
    assert metadata_int_label(invocation, "missing") == "-"
    assert metadata_text_label(invocation, "input_mode") == "runtime_transcript"


def test_invocation_duration_and_age_labels_are_stable() -> None:
    now = datetime(2026, 6, 21, 12, tzinfo=timezone.utc)
    started = now - timedelta(seconds=90)
    completed = now - timedelta(seconds=30)
    invocation = _invocation(started_at=started, completed_at=completed)

    assert duration_seconds(invocation) == 60
    assert duration_label(invocation) == "1m 0s"
    assert duration_or_age_label(invocation, now=now) == "1m 0s"
    assert age_seconds(started, now=now) == 90
    assert age_label(started, now=now) == "1m 30s"
    assert seconds_label(0.5) == "500ms"
    assert seconds_label(1.5) == "1.5s"
