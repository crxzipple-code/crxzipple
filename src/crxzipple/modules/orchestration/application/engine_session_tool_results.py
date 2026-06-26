from __future__ import annotations

from typing import Any, Protocol, TYPE_CHECKING

from crxzipple.modules.llm.domain import ToolCallIntent
from crxzipple.modules.orchestration.domain import (
    ExecutionOwnerReference,
    OrchestrationRun,
    OrchestrationValidationError,
)
from crxzipple.modules.session.application import AppendSessionItemInput
from crxzipple.modules.session.domain import SessionItemKind, SessionItemPhase
from crxzipple.modules.tool.application.result_envelope import (
    TOOL_RESULT_ENVELOPE_METADATA_KEY,
)
from crxzipple.modules.tool.domain import ToolRun, ToolRunStatus
from crxzipple.shared.content_blocks import text_content_block

if TYPE_CHECKING:
    from crxzipple.modules.orchestration.domain import (
        ExecutionStepItem,
        ExecutionStepItemStatus,
    )


class ExecutionStepItemLookupPort(Protocol):
    def find_execution_step_items_by_owner(
        self,
        owner: ExecutionOwnerReference,
        *,
        status: "ExecutionStepItemStatus | None" = None,
    ) -> list["ExecutionStepItem"]:
        ...


def build_tool_result_session_item_input(
    *,
    session_key: str,
    active_session_id: str,
    tool_call: ToolCallIntent,
    tool_run: ToolRun,
    source_kind: str,
    source_id: str,
) -> AppendSessionItemInput:
    return AppendSessionItemInput(
        session_key=session_key,
        session_id=active_session_id,
        role="tool",
        kind=SessionItemKind.TOOL_RESULT,
        phase=SessionItemPhase.UNKNOWN,
        content_payload=tool_result_payload(
            tool_call=tool_call,
            tool_run=tool_run,
        ),
        source_module="tool",
        source_kind=source_kind,
        source_id=source_id,
        call_id=tool_call.id,
        tool_name=tool_call.name,
        metadata={
            "tool_call_id": tool_call.id,
            "tool_name": tool_call.name,
            "tool_run_id": tool_run.id,
            "tool_status": tool_run.status.value,
        },
    )


def tool_result_payload(
    *,
    tool_call: ToolCallIntent,
    tool_run: ToolRun,
) -> dict[str, object]:
    envelope_payload = _tool_result_envelope_payload(tool_run)
    if envelope_payload is not None:
        return _tool_result_payload_from_envelope(
            tool_call=tool_call,
            tool_run=tool_run,
            envelope=envelope_payload,
        )
    tool_result = tool_run.result
    payload: dict[str, object] = {
        "tool_name": tool_call.name,
        "tool_call_id": tool_call.id,
        "tool_run_id": tool_run.id,
        "status": tool_run.status.value,
    }
    if tool_result is not None and tool_result.blocks:
        content_blocks = [dict(block) for block in tool_result.blocks]
        payload["content"] = content_blocks
    if tool_result is not None and tool_result.details is not None:
        payload["details"] = tool_result.details
    if tool_result is not None and tool_result.metadata:
        result_metadata = _session_tool_result_metadata(tool_result.metadata)
        if result_metadata:
            payload["metadata"] = result_metadata
    if tool_run.error is not None:
        payload["error"] = tool_run.error.to_storage()
        payload["content"] = [
            text_content_block(
                _tool_error_message_for_model(
                    tool_name=tool_call.name,
                    error=tool_run.error,
                ),
            ),
        ]
    elif tool_run.status in {ToolRunStatus.CANCELLED, ToolRunStatus.TIMED_OUT}:
        payload["content"] = [
            text_content_block(_terminal_tool_run_status_message(tool_run)),
        ]
    return payload


def resolve_background_tool_result_reference(
    *,
    execution_item_lookup: ExecutionStepItemLookupPort | None,
    run: OrchestrationRun,
    tool_run: ToolRun,
) -> dict[str, str]:
    if execution_item_lookup is None:
        raise OrchestrationValidationError(
            "Execution step item lookup is required to append background tool "
            "results.",
        )
    items = execution_item_lookup.find_execution_step_items_by_owner(
        ExecutionOwnerReference(owner_kind="tool_run", owner_id=tool_run.id),
    )
    item = next(
        (candidate for candidate in reversed(items) if candidate.turn_id == run.id),
        None,
    )
    if item is None:
        raise OrchestrationValidationError(
            "Execution step item for background tool run "
            f"'{tool_run.id}' was not found.",
        )
    summary = item.summary_payload if isinstance(item.summary_payload, dict) else {}
    tool_call_id = _non_empty_text(summary.get("tool_call_id")) or _non_empty_text(
        item.correlation_key,
    )
    tool_name = _non_empty_text(summary.get("tool_name"))
    if tool_call_id is None or tool_name is None:
        raise OrchestrationValidationError(
            "Execution step item for background tool run "
            f"'{tool_run.id}' is missing tool call reference metadata.",
        )
    return {"tool_call_id": tool_call_id, "tool_name": tool_name}


def _non_empty_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _tool_result_envelope_payload(tool_run: ToolRun) -> dict[str, object] | None:
    payload = getattr(tool_run, "result_envelope_payload", None)
    if isinstance(payload, dict) and payload:
        return dict(payload)
    return None


def _tool_result_payload_from_envelope(
    *,
    tool_call: ToolCallIntent,
    tool_run: ToolRun,
    envelope: dict[str, object],
) -> dict[str, object]:
    provider_payload = _dict_payload(envelope.get("provider_replay_payload"))
    payload: dict[str, object] = {
        "tool_name": tool_call.name,
        "tool_call_id": tool_call.id,
        "tool_run_id": tool_run.id,
        "status": _non_empty_text(envelope.get("status")) or tool_run.status.value,
    }
    if provider_payload:
        payload.update(provider_payload)
    if "content" not in payload and "blocks" not in payload:
        summary = _non_empty_text(envelope.get("summary"))
        if summary is not None:
            payload["content"] = [text_content_block(summary)]
    if tool_run.error is not None:
        payload["error"] = tool_run.error.to_storage()
        if "content" not in payload and "blocks" not in payload:
            payload["content"] = [text_content_block(tool_run.error.message)]
    metadata = _tool_result_envelope_session_metadata(envelope)
    if metadata:
        payload["metadata"] = metadata
    trace_payload = _dict_payload(envelope.get("trace_payload"))
    if trace_payload:
        payload["trace"] = trace_payload
    user_summary_payload = _dict_payload(envelope.get("user_summary_payload"))
    if user_summary_payload:
        payload["user_summary"] = user_summary_payload
    return {
        key: value
        for key, value in payload.items()
        if value not in (None, {}, [], ())
    }


def _tool_result_envelope_session_metadata(
    envelope: dict[str, object],
) -> dict[str, object]:
    metadata: dict[str, object] = {
        TOOL_RESULT_ENVELOPE_METADATA_KEY: dict(envelope),
    }
    artifact_refs = _list_of_dict_payloads(envelope.get("artifact_refs"))
    if artifact_refs:
        metadata["artifact_refs"] = artifact_refs
        artifact_ids = tuple(
            artifact_id
            for ref in artifact_refs
            if isinstance((artifact_id := ref.get("artifact_id")), str)
            and artifact_id.strip()
        )
        if artifact_ids:
            metadata["artifact_ids"] = list(dict.fromkeys(artifact_ids))
    read_handles = _list_of_dict_payloads(envelope.get("read_handles"))
    if read_handles:
        metadata["read_handles"] = read_handles
    warnings = _list_of_text(envelope.get("warnings"))
    if warnings:
        metadata["warnings"] = warnings
    evidence_refs = _list_of_text(envelope.get("evidence_refs"))
    if evidence_refs:
        metadata["evidence_refs"] = evidence_refs
    return metadata


def _dict_payload(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, dict) else {}


def _list_of_dict_payloads(value: object) -> list[dict[str, object]]:
    if not isinstance(value, (list, tuple)):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _list_of_text(value: object) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    result: list[str] = []
    for item in value:
        text = _non_empty_text(item)
        if text is not None:
            result.append(text)
    return result


def _session_tool_result_metadata(metadata: dict[str, Any]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in metadata.items():
        normalized_key = str(key)
        if not _keeps_session_tool_result_metadata_key(normalized_key):
            continue
        normalized_value = _json_safe_session_metadata(value)
        if normalized_value is not None:
            result[normalized_key] = normalized_value
    return result


def _tool_error_message_for_model(*, tool_name: str, error: Any) -> str:
    message = str(getattr(error, "message", "") or "").strip()
    if not message:
        message = "Tool run failed without an error message."
    guidance = _tool_error_recovery_guidance(tool_name=tool_name, error=error)
    if guidance is None:
        return message
    return f"{message}\n\nNext step: {guidance}"


def _tool_error_recovery_guidance(*, tool_name: str, error: Any) -> str | None:
    code = str(getattr(error, "code", "") or "").strip()
    details = getattr(error, "details", None)
    details = details if isinstance(details, dict) else {}
    recovery = details.get("browser_recovery")
    if isinstance(recovery, dict):
        reason = str(recovery.get("reason") or "").strip()
        recommended_tools = recovery.get("recommended_tools")
        tools = (
            ", ".join(str(item) for item in recommended_tools[:4])
            if isinstance(recommended_tools, list)
            else ""
        )
        if reason and tools:
            return f"{reason} Try {tools} before retrying {tool_name}."
        if reason:
            return reason
    message = str(getattr(error, "message", "") or "").lower()
    if "required" in message or code in {
        "browser_execution_failed",
        "browser_unsupported_action",
        "execution_failed",
    }:
        return (
            "Do not repeat the same failing tool call unchanged. Re-read the visible "
            "tool schema, correct the arguments, or choose another available tool."
        )
    return None


def _keeps_session_tool_result_metadata_key(key: str) -> bool:
    if key.startswith("browser_") or key.startswith("artifact_"):
        return True
    return key in {
        "artifact_ids",
        "family",
        "kind",
        "post_state_summary",
        "profile_name",
        "profile_source",
        "tool",
    }


def _json_safe_session_metadata(value: Any, *, depth: int = 0) -> object | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        return value[:512]
    if depth >= 2:
        return None
    if isinstance(value, (list, tuple)):
        items: list[object] = []
        for item in list(value)[:20]:
            normalized = _json_safe_session_metadata(item, depth=depth + 1)
            if normalized is not None:
                items.append(normalized)
        return items
    if isinstance(value, dict):
        result: dict[str, object] = {}
        for index, (item_key, item_value) in enumerate(value.items()):
            if index >= 40:
                break
            normalized_value = _json_safe_session_metadata(
                item_value,
                depth=depth + 1,
            )
            if normalized_value is not None:
                result[str(item_key)[:120]] = normalized_value
        return result
    return str(value)[:512]


def _terminal_tool_run_status_message(tool_run: ToolRun) -> str:
    if tool_run.status is ToolRunStatus.CANCELLED:
        return f"Tool run '{tool_run.tool_id}' was cancelled before completion."
    if tool_run.status is ToolRunStatus.TIMED_OUT:
        return f"Tool run '{tool_run.tool_id}' timed out before completion."
    return f"Tool run '{tool_run.tool_id}' ended with status '{tool_run.status.value}'."
