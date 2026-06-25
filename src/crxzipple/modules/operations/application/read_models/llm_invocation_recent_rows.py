from __future__ import annotations

from crxzipple.modules.llm.domain import LlmInvocation, LlmProfile
from crxzipple.modules.operations.application.observation_models import (
    OperationsObservedEvent,
)
from crxzipple.modules.operations.application.read_models.llm_invocation_facts import (
    duration_label,
    invocation_token_total,
    metadata_int_label,
)
from crxzipple.modules.operations.application.read_models.llm_invocation_labels import (
    continuation_reason_label,
    end_turn_label,
    invocation_status_tone,
    provider_model_label,
    response_item_count_label,
    response_text_label,
    result_tool_calls_label,
    status_label,
    tool_protocol_issue_count,
)
from crxzipple.modules.operations.application.read_models.llm_invocation_stream_status import (
    row_stream_status,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableRowModel,
)
from crxzipple.shared.time import format_datetime_utc


def recent_invocation_rows(
    invocations: list[LlmInvocation],
    *,
    profiles_by_id: dict[str, LlmProfile],
    streaming_ids: set[str],
    events_by_invocation: dict[str, tuple[OperationsObservedEvent, ...]],
    run_contexts: dict[str, dict[str, str]],
) -> tuple[OperationsTableRowModel, ...]:
    rows: list[OperationsTableRowModel] = []
    for invocation in invocations:
        profile = profiles_by_id.get(invocation.llm_id)
        error_code = invocation.error.code if invocation.error is not None else "-"
        events = events_by_invocation.get(invocation.id, ())
        run_context = run_contexts.get(invocation.id, {})
        rows.append(
            OperationsTableRowModel(
                id=invocation.id,
                cells={
                    "time": format_datetime_utc(invocation.created_at),
                    "invocation_id": invocation.id,
                    "provider_model": provider_model_label(profile),
                    "provider": profile.provider.value if profile is not None else "-",
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
                    "tokens": str(invocation_token_total(invocation)),
                    "provider_input_tokens": metadata_int_label(
                        invocation,
                        "estimated_provider_input_tokens",
                    ),
                    "draft_input_items": metadata_int_label(
                        invocation,
                        "draft_input_session_item_count",
                    ),
                    "draft_input_tokens": metadata_int_label(
                        invocation,
                        "draft_input_estimated_tokens",
                    ),
                    "tool_protocol": str(tool_protocol_issue_count(invocation)),
                    "response_text": response_text_label(invocation),
                    "tool_calls": result_tool_calls_label(invocation),
                    "response_items": response_item_count_label(invocation),
                    "response_events": "-",
                    "continuation": continuation_reason_label(invocation),
                    "end_turn": end_turn_label(invocation),
                    "progress": run_context.get("assistant_progress_item_count", "-"),
                    "finish_reason": (
                        invocation.result.finish_reason
                        if invocation.result is not None
                        and invocation.result.finish_reason
                        else "-"
                    ),
                    "error_code": error_code,
                    "actions": "Open / Trace",
                    "route": run_context.get("route", "-"),
                    "trace_route": run_context.get("trace_route", "-"),
                },
                status=invocation.status.value,
                tone=invocation_status_tone(invocation.status.value),
            ),
        )
    return tuple(rows)
