from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from crxzipple.modules.llm.domain import LlmInvocationStatus
from crxzipple.modules.operations.application.read_models.llm_invocation_filters import (
    LlmOperationsQuery,
    dedupe_invocations,
    filter_invocations,
    paginate_invocations,
)
from crxzipple.modules.operations.application.read_models.llm_invocation_streaming import (
    streaming_invocations as streaming_invocation_set,
)


@dataclass(frozen=True, slots=True)
class LlmPageInvocationSets:
    active: list[Any]
    failed: list[Any]
    filtered: list[Any]
    filtered_failed: list[Any]
    visible: list[Any]
    streaming: list[Any]
    detail: tuple[Any, ...]


def collect_llm_page_invocation_sets(
    invocations: list[Any],
    *,
    query: LlmOperationsQuery,
    profiles_by_id: dict[str, Any],
    observed_events: list[Any],
    now: datetime,
) -> LlmPageInvocationSets:
    active = [
        invocation
        for invocation in invocations
        if invocation.status is LlmInvocationStatus.RUNNING
    ]
    failed = [
        invocation
        for invocation in invocations
        if invocation.status is LlmInvocationStatus.FAILED
    ]
    filtered = filter_invocations(
        invocations,
        query=query,
        profiles_by_id=profiles_by_id,
        observed_events=observed_events,
        now=now,
    )
    filtered_failed = [
        invocation
        for invocation in filtered
        if invocation.status is LlmInvocationStatus.FAILED
    ]
    visible = paginate_invocations(filtered, query=query)
    streaming = streaming_invocation_set(
        invocations,
        profiles_by_id=profiles_by_id,
        observed_events=observed_events,
    )
    detail = dedupe_invocations((*visible, *active, *failed[:20]))
    return LlmPageInvocationSets(
        active=active,
        failed=failed,
        filtered=filtered,
        filtered_failed=filtered_failed,
        visible=visible,
        streaming=streaming,
        detail=detail,
    )
