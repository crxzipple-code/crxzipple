from __future__ import annotations

from typing import Any

from crxzipple.modules.llm.domain import LlmInvocation
from crxzipple.modules.operations.application.read_models.llm_invocation_detail_common import (
    duration_seconds_label,
    int_value,
    optional_int_label,
    text_or_dash,
)
from crxzipple.modules.operations.application.read_models.llm_invocation_labels import (
    tool_protocol_render_report,
)
from crxzipple.modules.operations.application.read_models.models import (
    OperationsKeyValueItemModel,
    OperationsKeyValueSectionModel,
)


def runtime_observations_section(
    invocation: LlmInvocation,
    *,
    response_event_retention_policy: dict[str, object],
) -> OperationsKeyValueSectionModel:
    tool_protocol_payload = tool_protocol_render_report(invocation)
    observation_count = int(bool(tool_protocol_payload))
    items = (
        OperationsKeyValueItemModel(
            "Runtime observations",
            str(observation_count) if observation_count else "none",
            "success" if observation_count else "neutral",
        ),
        OperationsKeyValueItemModel(
            "Tool protocol replay",
            _tool_protocol_replay_label(tool_protocol_payload),
            (
                "danger"
                if tool_protocol_payload.get("replay_has_protocol_breaks") is True
                else "success"
                if tool_protocol_payload
                else "neutral"
            ),
        ),
        OperationsKeyValueItemModel(
            "Tool protocol source",
            _tool_protocol_source_label(tool_protocol_payload),
            (
                "warning"
                if tool_protocol_payload.get("source_had_protocol_breaks") is True
                else "success"
                if tool_protocol_payload
                else "neutral"
            ),
        ),
        OperationsKeyValueItemModel(
            "Tool protocol filtered",
            _tool_protocol_filtered_label(tool_protocol_payload),
            (
                "warning"
                if _tool_protocol_filtered_count(tool_protocol_payload) > 0
                else "neutral"
            ),
        ),
        OperationsKeyValueItemModel(
            "Response event window",
            duration_seconds_label(
                response_event_retention_policy.get("full_event_window_seconds"),
            ),
            "info",
        ),
        OperationsKeyValueItemModel(
            "Response event detail limit",
            optional_int_label(
                response_event_retention_policy.get("detail_event_limit"),
            ),
            "neutral",
        ),
        OperationsKeyValueItemModel(
            "Response event durable fact",
            text_or_dash(response_event_retention_policy.get("durable_fact")),
            "neutral",
        ),
        OperationsKeyValueItemModel(
            "Response event overflow action",
            text_or_dash(response_event_retention_policy.get("overflow_action")),
            "neutral",
        ),
    )
    return OperationsKeyValueSectionModel(
        id="runtime_observations",
        title="Runtime Observations",
        items=items,
    )


def response_event_count_label(response_events: tuple[Any, ...]) -> str:
    return str(len(response_events)) if response_events else "-"


def _tool_protocol_replay_label(payload: dict[Any, Any]) -> str:
    if not payload:
        return "-"
    if payload.get("replay_has_protocol_breaks") is True:
        return (
            "breaks: "
            f"orphan={int_value(payload.get('replay_orphan_tool_output_count'))}; "
            f"missing={int_value(payload.get('replay_missing_tool_output_count'))}; "
            f"dup_call={int_value(payload.get('replay_duplicate_tool_call_id_count'))}; "
            f"dup_output={int_value(payload.get('replay_duplicate_tool_output_id_count'))}"
        )
    return "clean"


def _tool_protocol_source_label(payload: dict[Any, Any]) -> str:
    if not payload:
        return "-"
    return (
        "had breaks"
        if payload.get("source_had_protocol_breaks") is True
        else "clean"
    )


def _tool_protocol_filtered_label(payload: dict[Any, Any]) -> str:
    if not payload:
        return "-"
    filtered_count = _tool_protocol_filtered_count(payload)
    if filtered_count <= 0:
        return "none"
    return (
        f"filtered={filtered_count}; "
        f"orphan={int_value(payload.get('dropped_orphan_tool_output_count'))}; "
        f"missing={int_value(payload.get('dropped_missing_tool_output_count'))}; "
        f"dup_call={int_value(payload.get('dropped_duplicate_tool_call_id_count'))}; "
        f"dup_output={int_value(payload.get('dropped_duplicate_tool_output_id_count'))}"
    )


def _tool_protocol_filtered_count(payload: dict[Any, Any]) -> int:
    return sum(
        int_value(payload.get(key))
        for key in (
            "dropped_orphan_tool_output_count",
            "dropped_missing_tool_output_count",
            "dropped_duplicate_tool_call_id_count",
            "dropped_duplicate_tool_output_id_count",
        )
    )
