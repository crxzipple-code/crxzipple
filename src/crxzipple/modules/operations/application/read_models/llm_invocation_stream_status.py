from __future__ import annotations

from datetime import datetime, timezone

from crxzipple.modules.llm.domain import LlmInvocation
from crxzipple.modules.operations.application.observation_models import (
    OperationsObservedEvent,
)
from crxzipple.modules.operations.application.read_models.llm_invocation_labels import (
    stream_status_label,
)


def stream_delta_count(events: tuple[OperationsObservedEvent, ...]) -> int:
    return sum(
        1
        for event in events
        if event.event_name
        in {"llm.stream_delta_observed", "orchestration.run.llm_text_delta"}
    )


def row_stream_status(
    invocation: LlmInvocation,
    *,
    events: tuple[OperationsObservedEvent, ...],
    streaming_ids: set[str],
) -> str:
    if invocation.id not in streaming_ids:
        return "No"
    return stream_status_label(
        invocation,
        events=events,
        now=datetime.now(timezone.utc),
    )
