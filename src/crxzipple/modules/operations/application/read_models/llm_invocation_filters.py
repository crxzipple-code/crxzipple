from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from crxzipple.modules.llm.domain import LlmInvocation, LlmInvocationStatus, LlmProfile
from crxzipple.modules.operations.application.observation_models import OperationsObservedEvent
from crxzipple.modules.operations.application.read_models.llm_invocation_streaming import (
    streaming_invocation_ids,
)
from crxzipple.shared.time import coerce_utc_datetime

_RECENT_WINDOW = timedelta(hours=24)
_INVOCATION_PAGE_BASE_LIMIT = 240


@dataclass(frozen=True, slots=True)
class LlmOperationsQuery:
    status: str = "all"
    time_window: str = "all"
    search: str = ""
    llm_id: str = "all"
    run_id: str = "all"
    provider: str = "all"
    streaming: str = "all"
    limit: int = 50
    offset: int = 0


def filter_invocations(
    invocations: list[LlmInvocation],
    *,
    query: LlmOperationsQuery,
    profiles_by_id: dict[str, LlmProfile],
    observed_events: tuple[OperationsObservedEvent, ...],
    now: datetime,
) -> list[LlmInvocation]:
    streaming_ids = streaming_invocation_ids(observed_events)
    result: list[LlmInvocation] = []
    search = query.search.strip().lower()
    for invocation in sorted(invocations, key=lambda item: item.created_at, reverse=True):
        if (
            query.time_window == "24h"
            and coerce_utc_datetime(invocation.created_at) < now - _RECENT_WINDOW
        ):
            continue
        if query.status != "all":
            if (
                query.status == "active"
                and invocation.status is not LlmInvocationStatus.RUNNING
            ):
                continue
            if query.status != "active" and invocation.status.value != query.status:
                continue
        if query.llm_id != "all" and invocation.llm_id != query.llm_id:
            continue
        if query.run_id != "all" and invocation.run_id != query.run_id:
            continue
        profile = profiles_by_id.get(invocation.llm_id)
        if (
            query.provider != "all"
            and (profile is None or profile.provider.value != query.provider)
        ):
            continue
        if query.streaming != "all":
            streaming = invocation.id in streaming_ids
            if query.streaming == "yes" and not streaming:
                continue
            if query.streaming == "no" and streaming:
                continue
        if search and search not in invocation_search_text(invocation, profile).lower():
            continue
        result.append(invocation)
    return result


def normalize_query(query: LlmOperationsQuery | None) -> LlmOperationsQuery:
    if query is None:
        return LlmOperationsQuery()
    return LlmOperationsQuery(
        status=query.status if query.status else "all",
        time_window=query.time_window if query.time_window in {"all", "24h"} else "all",
        search=query.search or "",
        llm_id=query.llm_id or "all",
        run_id=query.run_id or "all",
        provider=query.provider or "all",
        streaming=query.streaming if query.streaming in {"all", "yes", "no"} else "all",
        limit=max(min(int(query.limit), 200), 1),
        offset=max(int(query.offset), 0),
    )


def invocation_page_read_limit(query: LlmOperationsQuery) -> int:
    requested_window = query.offset + query.limit
    return max(requested_window, _INVOCATION_PAGE_BASE_LIMIT)


def paginate_invocations(
    invocations: list[LlmInvocation],
    *,
    query: LlmOperationsQuery,
) -> list[LlmInvocation]:
    return invocations[query.offset : query.offset + query.limit]


def invocations_empty_state(query: LlmOperationsQuery) -> str:
    if has_invocation_filters(query):
        return "No LLM invocations match the current filters."
    return "No LLM invocations recorded yet."


def has_invocation_filters(query: LlmOperationsQuery) -> bool:
    return any(
        (
            query.status != "all",
            query.time_window != "all",
            query.search.strip(),
            query.llm_id != "all",
            query.run_id != "all",
            query.provider != "all",
            query.streaming != "all",
        ),
    )


def invocation_search_text(
    invocation: LlmInvocation,
    profile: LlmProfile | None,
) -> str:
    parts = [
        invocation.id,
        invocation.llm_id,
        invocation.run_id or "",
        invocation.session_key or "",
        invocation.active_session_id or "",
        invocation.agent_id or "",
        invocation.status.value,
        profile.provider.value if profile is not None else "",
        profile.model_name if profile is not None else "",
        invocation.error.code if invocation.error is not None else "",
        invocation.error.message if invocation.error is not None else "",
    ]
    return " ".join(parts)


def dedupe_invocations(
    invocations: tuple[LlmInvocation, ...],
) -> tuple[LlmInvocation, ...]:
    seen: set[str] = set()
    result: list[LlmInvocation] = []
    for invocation in invocations:
        if invocation.id in seen:
            continue
        seen.add(invocation.id)
        result.append(invocation)
    return tuple(result[:80])
