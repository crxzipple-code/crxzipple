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
from crxzipple.modules.operations.application.read_models.llm_overview_sections import (
    llm_health,
    page_metric_cards,
)
from crxzipple.modules.operations.application.read_models.llm_overview_rows import (
    invocation_reason,
    max_context_label,
    profile_limit_rows,
    profile_rows,
    queue_rows,
)
from crxzipple.modules.operations.application.read_models.llm_overview_actions import (
    llm_actions,
)


def _profile(
    profile_id: str = "openai.gpt",
    *,
    enabled: bool = True,
    context_window_tokens: int | None = 4096,
    max_concurrency: int | None = None,
    concurrency_key: str | None = None,
) -> LlmProfile:
    return LlmProfile(
        id=profile_id,
        provider=LlmProviderKind.OPENAI,
        api_family=LlmApiFamily.OPENAI_RESPONSES,
        model_name="gpt-5",
        enabled=enabled,
        context_window_tokens=context_window_tokens,
        max_concurrency=max_concurrency,
        concurrency_key=concurrency_key,
        timeout_seconds=30,
    )


def _invocation(
    invocation_id: str,
    *,
    llm_id: str = "openai.gpt",
    status: LlmInvocationStatus = LlmInvocationStatus.SUCCEEDED,
    created_at: datetime | None = None,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
    result: LlmResult | None = None,
) -> LlmInvocation:
    created_at = created_at or datetime(2026, 6, 21, 12, tzinfo=timezone.utc)
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
        created_at=created_at,
        started_at=started_at,
        completed_at=completed_at,
        result=result,
    )


def test_llm_health_distinguishes_empty_failed_active_and_blocked() -> None:
    profile = _profile()
    active = _invocation("running", status=LlmInvocationStatus.RUNNING)
    failed = _invocation("failed", status=LlmInvocationStatus.FAILED)

    assert (
        llm_health(
            profiles=[],
            enabled_profiles=[],
            active_invocations=[],
            failed_invocations=[],
        )
        == "warning"
    )
    assert (
        llm_health(
            profiles=[profile],
            enabled_profiles=[profile],
            active_invocations=[],
            failed_invocations=[failed],
        )
        == "warning"
    )
    assert (
        llm_health(
            profiles=[profile],
            enabled_profiles=[profile],
            active_invocations=[active],
            failed_invocations=[],
        )
        == "healthy"
    )
    assert (
        llm_health(
            profiles=[profile],
            enabled_profiles=[profile],
            active_invocations=[],
            failed_invocations=[],
            blocked_profiles=[profile],
        )
        == "warning"
    )


def test_page_metric_cards_keep_stable_ids_and_values() -> None:
    now = datetime(2026, 6, 21, 12, tzinfo=timezone.utc)
    invocation = _invocation(
        "done",
        started_at=now,
        completed_at=now + timedelta(seconds=2),
        result=LlmResult(
            finish_reason="stop",
            usage=LlmUsage(input_tokens=3, output_tokens=4, total_tokens=10),
        ),
    )
    running = _invocation("running", status=LlmInvocationStatus.RUNNING)
    profile = _profile()

    cards = page_metric_cards(
        profiles=[profile],
        invocations=[invocation, running],
        streaming_invocations=[running],
        failed_invocations=[],
        health="healthy",
    )

    assert [card.id for card in cards] == [
        "health",
        "invocations",
        "tokens",
        "streaming",
        "errors",
        "latency",
    ]
    assert {card.id: card.value for card in cards}["invocations"] == "2"
    assert {card.id: card.value for card in cards}["tokens"] == "10"
    assert {card.id: card.value for card in cards}["latency"] == "2s"


def test_actions_queue_profile_rows_and_context_label_are_stable() -> None:
    now = datetime(2026, 6, 21, 12, tzinfo=timezone.utc)
    profile = _profile(max_concurrency=2, concurrency_key="llm:openai")
    invocation = _invocation(
        "invocation-1",
        created_at=now - timedelta(seconds=30),
        started_at=now - timedelta(seconds=20),
        result=LlmResult(finish_reason="tool_calls"),
    )

    assert [action.id for action in llm_actions()] == [
        "open_invocation",
        "open_trace",
        "open_access",
        "warmup_profile",
        "view_limits",
        "configure_pricing",
        "disable_profile",
    ]
    assert queue_rows([invocation], now=now)[0] == {
        "Priority": "succeeded",
        "Run ID": "invocation-1",
        "Lane Key": "openai.gpt",
        "Wait Reason": "tool_calls",
        "Wait Time": "20s",
    }
    assert profile_limit_rows([profile])[0]["Lane Key"] == "llm:openai"
    assert profile_rows([profile], [invocation])[0]["Current Run"] == "invocation-1"
    assert max_context_label([profile]) == "4096"
    assert invocation_reason(invocation) == "tool_calls"
