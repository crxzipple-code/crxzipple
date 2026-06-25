from __future__ import annotations

from datetime import datetime

from crxzipple.modules.llm.domain import LlmInvocation, LlmProfile
from crxzipple.modules.operations.application.observation_models import OperationsObservedEvent
from crxzipple.modules.operations.application.read_models.llm_invocation_streaming import (
    streaming_invocation_ids,
)
from crxzipple.modules.operations.application.read_models.llm_invocation_failed_rows import (
    failed_invocation_rows,
)
from crxzipple.modules.operations.application.read_models.llm_invocation_recent_rows import (
    recent_invocation_rows,
)
from crxzipple.modules.operations.application.read_models.llm_invocation_streaming_rows import (
    streaming_request_rows,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableColumnModel,
    OperationsTableSectionModel,
)


def streaming_requests_section(
    streaming_invocations: list[LlmInvocation],
    *,
    profiles_by_id: dict[str, LlmProfile],
    events_by_invocation: dict[str, tuple[OperationsObservedEvent, ...]],
    run_contexts: dict[str, dict[str, str]],
    now: datetime,
) -> OperationsTableSectionModel:
    rows = streaming_request_rows(
        streaming_invocations,
        profiles_by_id=profiles_by_id,
        events_by_invocation=events_by_invocation,
        run_contexts=run_contexts,
        now=now,
    )
    return OperationsTableSectionModel(
        id="streaming_requests",
        title="Streaming Requests",
        columns=_columns(
            ("started_at", "Started At"),
            ("profile", "LLM Profile"),
            ("provider_model", "Provider / Model"),
            ("status", "Status"),
            ("run_id", "Run ID"),
            ("chain_id", "Chain ID"),
            ("step_id", "Step ID"),
            ("trace", "Trace"),
            ("duration", "Duration"),
            ("tokens", "Tokens"),
            ("events", "Events"),
            ("actions", "Actions"),
        ),
        rows=tuple(rows),
        total=len(streaming_invocations),
        empty_state="No streaming LLM invocations observed.",
    )


def recent_invocations_section(
    invocations: list[LlmInvocation],
    *,
    profiles_by_id: dict[str, LlmProfile],
    observed_events: tuple[OperationsObservedEvent, ...],
    events_by_invocation: dict[str, tuple[OperationsObservedEvent, ...]],
    run_contexts: dict[str, dict[str, str]],
    total_count: int,
    empty_state: str,
) -> OperationsTableSectionModel:
    streaming_ids = streaming_invocation_ids(observed_events)
    rows = recent_invocation_rows(
        invocations,
        profiles_by_id=profiles_by_id,
        streaming_ids=streaming_ids,
        events_by_invocation=events_by_invocation,
        run_contexts=run_contexts,
    )
    return OperationsTableSectionModel(
        id="recent_invocations",
        title="Recent Invocations",
        columns=_columns(
            ("time", "Time"),
            ("invocation_id", "Invocation ID"),
            ("provider_model", "Provider / Model"),
            ("provider", "Provider"),
            ("status", "Status"),
            ("run_id", "Run ID"),
            ("chain_id", "Chain ID"),
            ("step_id", "Step ID"),
            ("trace", "Trace"),
            ("duration", "Duration"),
            ("streaming", "Streaming"),
            ("tokens", "Tokens"),
            ("provider_input_tokens", "Provider Input"),
            ("draft_input_items", "Draft Input Items"),
            ("draft_input_tokens", "Draft Input Tokens"),
            ("tool_protocol", "Tool Protocol"),
            ("response_text", "Text"),
            ("tool_calls", "Tool Calls"),
            ("response_items", "Items"),
            ("response_events", "Events"),
            ("continuation", "Continuation"),
            ("end_turn", "End Turn"),
            ("progress", "Progress"),
            ("finish_reason", "Finish Reason"),
            ("error_code", "Error Code"),
            ("actions", "Actions"),
        ),
        rows=tuple(rows),
        total=total_count,
        empty_state=empty_state,
    )


def failed_invocations_section(
    failed_invocations: list[LlmInvocation],
    *,
    profiles_by_id: dict[str, LlmProfile],
    observed_events: tuple[OperationsObservedEvent, ...],
    events_by_invocation: dict[str, tuple[OperationsObservedEvent, ...]],
    run_contexts: dict[str, dict[str, str]],
    total_count: int,
    empty_state: str,
) -> OperationsTableSectionModel:
    streaming_ids = streaming_invocation_ids(observed_events)
    rows = failed_invocation_rows(
        failed_invocations,
        profiles_by_id=profiles_by_id,
        streaming_ids=streaming_ids,
        events_by_invocation=events_by_invocation,
        run_contexts=run_contexts,
    )
    return OperationsTableSectionModel(
        id="failed_invocations",
        title="Failed Invocations",
        columns=_columns(
            ("time", "Time"),
            ("invocation_id", "Invocation ID"),
            ("provider_model", "Provider / Model"),
            ("status", "Status"),
            ("run_id", "Run ID"),
            ("chain_id", "Chain ID"),
            ("step_id", "Step ID"),
            ("trace", "Trace"),
            ("duration", "Duration"),
            ("streaming", "Streaming"),
            ("error_code", "Error Code"),
            ("actions", "Actions"),
        ),
        rows=tuple(rows),
        total=total_count,
        empty_state=empty_state,
    )


def _columns(*pairs: tuple[str, str]) -> tuple[OperationsTableColumnModel, ...]:
    return tuple(OperationsTableColumnModel(key=key, label=label) for key, label in pairs)
