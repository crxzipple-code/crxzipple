from __future__ import annotations

from datetime import datetime
from typing import Any

from crxzipple.modules.llm.domain import LlmInvocation, LlmInvocationStatus, LlmProfile
from crxzipple.modules.operations.application.observation_models import OperationsObservedEvent
from crxzipple.modules.operations.application.read_models.presenters import status_tone
from crxzipple.shared.time import format_datetime_utc


def provider_model_label(profile: LlmProfile | None) -> str:
    if profile is None:
        return "-"
    return f"{profile.provider.value} / {profile.model_name}"


def datetime_label(value: datetime | None) -> str:
    return format_datetime_utc(value) if value is not None else "-"


def status_label(status: str) -> str:
    return {
        "created": "Created",
        "running": "Running",
        "succeeded": "Succeeded",
        "failed": "Failed",
    }.get(status, status)


def stream_status_label(
    invocation: LlmInvocation,
    *,
    events: tuple[OperationsObservedEvent, ...],
    now: datetime,
) -> str:
    if invocation.status is LlmInvocationStatus.FAILED:
        return "Failed"
    if invocation.status is LlmInvocationStatus.SUCCEEDED:
        return "Completed"
    delta_seen = any(
        event.event_name in {
            "llm.stream_delta_observed",
            "orchestration.run.llm_text_delta",
        }
        for event in events
    )
    if invocation.status is LlmInvocationStatus.RUNNING:
        return "Streaming" if delta_seen else "Connecting"
    if invocation.started_at is not None and (now - invocation.started_at).total_seconds() < 5:
        return "Connecting"
    return "Streaming" if delta_seen else "No"


def invocation_status_tone(status: str) -> str:
    return status_tone(
        status,
        danger=frozenset({"failed"}),
        warning=frozenset(),
        success=frozenset({"succeeded"}),
        info=frozenset({"running"}),
    )


def response_text_label(invocation: LlmInvocation) -> str:
    text = getattr(getattr(invocation, "result", None), "text", None)
    if isinstance(text, str) and text.strip():
        return f"{len(text.strip())} chars"
    return "-"


def result_tool_calls_label(invocation: LlmInvocation) -> str:
    tool_calls = getattr(getattr(invocation, "result", None), "tool_calls", None)
    if isinstance(tool_calls, (list, tuple)) and tool_calls:
        return str(len(tool_calls))
    return "-"


def response_item_count_label(invocation: LlmInvocation) -> str:
    response_items = getattr(invocation, "response_items", None)
    if isinstance(response_items, (list, tuple)) and response_items:
        return str(len(response_items))
    return "-"


def continuation_reason_label(invocation: LlmInvocation) -> str:
    continuation = getattr(invocation, "continuation", None)
    reason = getattr(continuation, "reason", None)
    return _enum_value(reason) if reason is not None else "-"


def end_turn_label(invocation: LlmInvocation) -> str:
    continuation = getattr(invocation, "continuation", None)
    end_turn = getattr(continuation, "end_turn", None)
    if end_turn is True:
        return "Yes"
    if end_turn is False:
        return "No"
    return "-"


def provider_request_preview(invocation: LlmInvocation) -> dict[str, Any]:
    preview = getattr(invocation, "provider_request_payload_preview", None)
    return dict(preview) if isinstance(preview, dict) else {}


def provider_render_report(invocation: LlmInvocation) -> dict[str, Any]:
    preview = provider_request_preview(invocation)
    render_report = preview.get("render_report")
    return dict(render_report) if isinstance(render_report, dict) else {}


def tool_protocol_render_report(invocation: LlmInvocation) -> dict[str, Any]:
    render_report = provider_render_report(invocation)
    tool_protocol = render_report.get("tool_protocol")
    return dict(tool_protocol) if isinstance(tool_protocol, dict) else {}


def tool_protocol_issue_count(invocation: LlmInvocation) -> int:
    payload = tool_protocol_render_report(invocation)
    if not payload:
        return 0
    return _tool_protocol_filtered_count(payload) + sum(
        _int_value(payload.get(key))
        for key in (
            "replay_orphan_tool_output_count",
            "replay_missing_tool_output_count",
            "replay_duplicate_tool_call_id_count",
            "replay_duplicate_tool_output_id_count",
        )
    )


def _tool_protocol_filtered_count(payload: dict[Any, Any]) -> int:
    return sum(
        _int_value(payload.get(key))
        for key in (
            "dropped_orphan_tool_output_count",
            "dropped_missing_tool_output_count",
            "dropped_duplicate_tool_call_id_count",
            "dropped_duplicate_tool_output_id_count",
        )
    )


def _enum_value(value: Any) -> str:
    raw = getattr(value, "value", value)
    if raw is None:
        return "-"
    normalized = str(raw).strip()
    return normalized or "-"


def _int_value(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return max(value, 0)
    if isinstance(value, float):
        return max(int(value), 0)
    if isinstance(value, str):
        try:
            return max(int(value), 0)
        except ValueError:
            return 0
    return 0
