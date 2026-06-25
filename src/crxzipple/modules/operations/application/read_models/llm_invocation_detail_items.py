from __future__ import annotations

from typing import Any

from crxzipple.modules.llm.domain import LlmInvocation, LlmProfile
from crxzipple.modules.operations.application.read_models.llm_invocation_detail_runtime import (
    response_event_count_label,
)
from crxzipple.modules.operations.application.read_models.llm_invocation_facts import (
    duration_label,
    invocation_token_total,
)
from crxzipple.modules.operations.application.read_models.llm_invocation_labels import (
    continuation_reason_label,
    datetime_label,
    end_turn_label,
    invocation_status_tone,
    response_item_count_label,
    response_text_label,
    result_tool_calls_label,
    status_label,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsKeyValueItemModel,
)


def summary_items(
    invocation: LlmInvocation,
    *,
    profile: LlmProfile | None,
    run_context: dict[str, str],
    response_events: tuple[Any, ...],
) -> tuple[OperationsKeyValueItemModel, ...]:
    return (
        OperationsKeyValueItemModel(
            "Status",
            status_label(invocation.status.value),
            invocation_status_tone(invocation.status.value),
        ),
        OperationsKeyValueItemModel("Profile", invocation.llm_id),
        OperationsKeyValueItemModel(
            "Provider",
            profile.provider.value if profile is not None else "-",
        ),
        OperationsKeyValueItemModel(
            "Model",
            profile.model_name if profile is not None else "-",
        ),
        OperationsKeyValueItemModel("Run ID", run_context.get("run_id", "-")),
        OperationsKeyValueItemModel("Chain ID", run_context.get("chain_id", "-")),
        OperationsKeyValueItemModel("Step ID", run_context.get("step_id", "-")),
        OperationsKeyValueItemModel(
            "Step Kind",
            run_context.get("step_kind", "-"),
        ),
        OperationsKeyValueItemModel("Trace", run_context.get("trace_id", "-")),
        OperationsKeyValueItemModel("Turn ID", run_context.get("turn_id", "-")),
        OperationsKeyValueItemModel("Started At", datetime_label(invocation.started_at)),
        OperationsKeyValueItemModel(
            "Completed At",
            datetime_label(invocation.completed_at),
        ),
        OperationsKeyValueItemModel("Duration", duration_label(invocation)),
        OperationsKeyValueItemModel(
            "Tokens",
            str(invocation_token_total(invocation)),
        ),
        OperationsKeyValueItemModel(
            "Response Text",
            response_text_label(invocation),
        ),
        OperationsKeyValueItemModel(
            "Tool Calls",
            result_tool_calls_label(invocation),
        ),
        OperationsKeyValueItemModel(
            "Response Items",
            response_item_count_label(invocation),
        ),
        OperationsKeyValueItemModel(
            "Response Events",
            response_event_count_label(response_events),
        ),
        OperationsKeyValueItemModel(
            "Continuation",
            continuation_reason_label(invocation),
        ),
        OperationsKeyValueItemModel("End Turn", end_turn_label(invocation)),
        OperationsKeyValueItemModel(
            "Assistant Progress Items",
            run_context.get("assistant_progress_item_count", "-"),
        ),
        OperationsKeyValueItemModel(
            "Assistant Progress IDs",
            run_context.get("assistant_progress_item_ids", "-"),
        ),
    )
