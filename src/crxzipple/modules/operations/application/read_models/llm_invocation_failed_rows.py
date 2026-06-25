from __future__ import annotations

from crxzipple.modules.llm.domain import LlmInvocation, LlmProfile
from crxzipple.modules.operations.application.observation_models import (
    OperationsObservedEvent,
)
from crxzipple.modules.operations.application.read_models.llm_invocation_facts import (
    duration_label,
)
from crxzipple.modules.operations.application.read_models.llm_invocation_labels import (
    invocation_status_tone,
    provider_model_label,
    status_label,
)
from crxzipple.modules.operations.application.read_models.llm_invocation_stream_status import (
    row_stream_status,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableRowModel,
)
from crxzipple.shared.time import format_datetime_utc


def failed_invocation_rows(
    failed_invocations: list[LlmInvocation],
    *,
    profiles_by_id: dict[str, LlmProfile],
    streaming_ids: set[str],
    events_by_invocation: dict[str, tuple[OperationsObservedEvent, ...]],
    run_contexts: dict[str, dict[str, str]],
) -> tuple[OperationsTableRowModel, ...]:
    rows: list[OperationsTableRowModel] = []
    for invocation in failed_invocations:
        profile = profiles_by_id.get(invocation.llm_id)
        events = events_by_invocation.get(invocation.id, ())
        run_context = run_contexts.get(invocation.id, {})
        rows.append(
            OperationsTableRowModel(
                id=invocation.id,
                cells={
                    "time": format_datetime_utc(invocation.created_at),
                    "invocation_id": invocation.id,
                    "provider_model": provider_model_label(profile),
                    "status": status_label(invocation.status.value),
                    "run_id": run_context.get("run_id", "-"),
                    "chain_id": run_context.get("chain_id", "-"),
                    "step_id": run_context.get("step_id", "-"),
                    "trace": run_context.get("trace_id", "-"),
                    "duration": duration_label(invocation),
                    "streaming": row_stream_status(
                        invocation,
                        events=events,
                        streaming_ids=streaming_ids,
                    ),
                    "error_code": (
                        invocation.error.code if invocation.error is not None else "-"
                    ),
                    "actions": "Open / Trace",
                    "route": run_context.get("route", "-"),
                    "trace_route": run_context.get("trace_route", "-"),
                },
                status=invocation.status.value,
                tone=invocation_status_tone(invocation.status.value),
            ),
        )
    return tuple(rows)
