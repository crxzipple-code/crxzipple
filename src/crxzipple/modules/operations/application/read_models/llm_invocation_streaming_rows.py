from __future__ import annotations

from datetime import datetime

from crxzipple.modules.llm.domain import LlmInvocation, LlmProfile
from crxzipple.modules.operations.application.observation_models import (
    OperationsObservedEvent,
)
from crxzipple.modules.operations.application.read_models.llm_invocation_facts import (
    duration_or_age_label,
    invocation_token_total,
)
from crxzipple.modules.operations.application.read_models.llm_invocation_labels import (
    datetime_label,
    invocation_status_tone,
    provider_model_label,
    stream_status_label,
)
from crxzipple.modules.operations.application.read_models.llm_invocation_stream_status import (
    stream_delta_count,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableRowModel,
)


def streaming_request_rows(
    streaming_invocations: list[LlmInvocation],
    *,
    profiles_by_id: dict[str, LlmProfile],
    events_by_invocation: dict[str, tuple[OperationsObservedEvent, ...]],
    run_contexts: dict[str, dict[str, str]],
    now: datetime,
) -> tuple[OperationsTableRowModel, ...]:
    rows: list[OperationsTableRowModel] = []
    for invocation in sorted(
        streaming_invocations,
        key=lambda item: item.started_at or item.created_at,
        reverse=True,
    )[:50]:
        profile = profiles_by_id.get(invocation.llm_id)
        events = events_by_invocation.get(invocation.id, ())
        run_context = run_contexts.get(invocation.id, {})
        rows.append(
            OperationsTableRowModel(
                id=invocation.id,
                cells={
                    "started_at": datetime_label(invocation.started_at),
                    "profile": invocation.llm_id,
                    "provider_model": provider_model_label(profile),
                    "status": stream_status_label(invocation, events=events, now=now),
                    "run_id": run_context.get("run_id", "-"),
                    "chain_id": run_context.get("chain_id", "-"),
                    "step_id": run_context.get("step_id", "-"),
                    "trace": run_context.get("trace_id", "-"),
                    "duration": duration_or_age_label(invocation, now=now),
                    "tokens": str(invocation_token_total(invocation)),
                    "events": str(stream_delta_count(events)),
                    "actions": "Open / Trace",
                    "route": run_context.get("route", "-"),
                    "trace_route": run_context.get("trace_route", "-"),
                },
                status=invocation.status.value,
                tone=invocation_status_tone(invocation.status.value),
            ),
        )
    return tuple(rows)
