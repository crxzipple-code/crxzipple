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
from crxzipple.modules.operations.application.read_models.llm_invocation_filters import (
    LlmOperationsQuery,
    dedupe_invocations,
    filter_invocations,
    has_invocation_filters,
    invocation_page_read_limit,
    invocations_empty_state,
    normalize_query,
    paginate_invocations,
)
from crxzipple.modules.operations.application.read_models.llm_invocation_streaming import (
    streaming_invocation_ids,
    streaming_invocations,
)


def _profile(
    profile_id: str,
    *,
    provider: LlmProviderKind,
    model_name: str,
    capabilities: tuple[LlmCapability, ...] = (),
) -> LlmProfile:
    return LlmProfile(
        id=profile_id,
        provider=provider,
        api_family=LlmApiFamily.OPENAI_RESPONSES,
        model_name=model_name,
        capabilities=capabilities,
    )


def _invocation(
    invocation_id: str,
    *,
    llm_id: str,
    status: LlmInvocationStatus,
    created_at: datetime,
) -> LlmInvocation:
    return LlmInvocation(
        id=invocation_id,
        llm_id=llm_id,
        messages=(LlmMessage(role=LlmMessageRole.USER, content="hello"),),
        input_items=(
            LlmInputItem(
                kind=LlmInputItemKind.MESSAGE,
                payload={"role": "user", "content": "hello"},
            ),
        ),
        status=status,
        created_at=created_at,
    )


def _event(
    event_id: str,
    *,
    invocation_id: str,
    streaming: bool = True,
) -> OperationsObservedEvent:
    return OperationsObservedEvent(
        id=event_id,
        cursor=event_id,
        topic="events.named.llm.stream_delta_observed",
        event_name="llm.stream_delta_observed",
        module="llm",
        owner="llm",
        kind="fact",
        level="info",
        status="observed",
        entity_id=invocation_id,
        run_id=None,
        trace_id=None,
        source_event_name=None,
        occurred_at=datetime(2026, 6, 21, tzinfo=timezone.utc),
        payload={"invocation_id": invocation_id, "streaming": streaming},
    )


def test_normalize_llm_query_bounds_filters_and_page_read_limit() -> None:
    query = normalize_query(
        LlmOperationsQuery(
            status="",
            time_window="bad",
            streaming="maybe",
            limit=999,
            offset=-5,
        ),
    )

    assert query.status == "all"
    assert query.time_window == "all"
    assert query.streaming == "all"
    assert query.limit == 200
    assert query.offset == 0
    assert invocation_page_read_limit(query) == 240
    assert not has_invocation_filters(query)
    assert invocations_empty_state(query) == "No LLM invocations recorded yet."


def test_filter_llm_invocations_by_status_provider_streaming_search_and_time() -> None:
    now = datetime(2026, 6, 21, 12, tzinfo=timezone.utc)
    openai = _profile(
        "openai.gpt",
        provider=LlmProviderKind.OPENAI,
        model_name="gpt-5",
        capabilities=(LlmCapability.STREAMING,),
    )
    anthropic = _profile(
        "anthropic.claude",
        provider=LlmProviderKind.ANTHROPIC,
        model_name="claude",
    )
    recent_running = _invocation(
        "inv-running",
        llm_id=openai.id,
        status=LlmInvocationStatus.RUNNING,
        created_at=now,
    )
    recent_succeeded = _invocation(
        "inv-succeeded",
        llm_id=anthropic.id,
        status=LlmInvocationStatus.SUCCEEDED,
        created_at=now - timedelta(hours=1),
    )
    old_openai = _invocation(
        "inv-old",
        llm_id=openai.id,
        status=LlmInvocationStatus.SUCCEEDED,
        created_at=now - timedelta(days=2),
    )
    events = (
        _event("event-stream-running", invocation_id=recent_running.id),
        _event("event-stream-succeeded", invocation_id=recent_succeeded.id),
    )

    filtered = filter_invocations(
        [old_openai, recent_succeeded, recent_running],
        query=normalize_query(
            LlmOperationsQuery(
                status="active",
                time_window="24h",
                provider="openai",
                streaming="yes",
                search="gpt",
            ),
        ),
        profiles_by_id={openai.id: openai, anthropic.id: anthropic},
        observed_events=events,
        now=now,
    )

    assert filtered == [recent_running]
    assert streaming_invocation_ids(events) == {
        recent_running.id,
        recent_succeeded.id,
    }
    assert streaming_invocations(
        [recent_running, recent_succeeded, old_openai],
        profiles_by_id={openai.id: openai, anthropic.id: anthropic},
        observed_events=events,
    ) == [recent_running, recent_succeeded]


def test_paginate_and_dedupe_llm_invocations_preserve_first_seen_order() -> None:
    now = datetime(2026, 6, 21, 12, tzinfo=timezone.utc)
    first = _invocation(
        "inv-1",
        llm_id="openai.gpt",
        status=LlmInvocationStatus.SUCCEEDED,
        created_at=now,
    )
    second = _invocation(
        "inv-2",
        llm_id="openai.gpt",
        status=LlmInvocationStatus.FAILED,
        created_at=now,
    )

    assert dedupe_invocations((first, second, first)) == (first, second)
    assert paginate_invocations(
        [first, second],
        query=LlmOperationsQuery(limit=1, offset=1),
    ) == [second]
    assert has_invocation_filters(LlmOperationsQuery(search="inv-2"))
    assert (
        invocations_empty_state(LlmOperationsQuery(search="inv-2"))
        == "No LLM invocations match the current filters."
    )
