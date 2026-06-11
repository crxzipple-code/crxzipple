from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

from crxzipple.modules.llm.domain import ToolCallIntent
from crxzipple.modules.orchestration.domain import (
    ExecutionOwnerReference,
    OrchestrationRun,
    OrchestrationValidationError,
)
from crxzipple.modules.orchestration.application.ports import SessionRecorderPort
from crxzipple.modules.session.application import (
    AppendSessionMessageInput,
    AppendSessionMessagesInput,
)
from crxzipple.modules.session.domain import SessionMessageKind
from crxzipple.modules.tool.domain import ToolRun, ToolRunStatus
from crxzipple.shared.content_blocks import (
    normalize_content_blocks,
    text_content_block,
)

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


@dataclass(slots=True)
class OrchestrationSessionRecorder:
    session_service: SessionRecorderPort
    execution_item_lookup: ExecutionStepItemLookupPort | None = None

    def ensure_inbound_message(
        self,
        run: OrchestrationRun,
        *,
        session_key: str,
    ) -> str | None:
        cached_message_id = run.metadata.get("user_message_id")
        if isinstance(cached_message_id, str) and cached_message_id.strip():
            return cached_message_id.strip()
        existing = self.session_service.get_message_by_source(
            session_key=session_key,
            session_id=run.active_session_id,
            source_kind="orchestration_run",
            source_id=run.id,
        )
        if existing is not None and existing.role == "user":
            return existing.id
        inbound_blocks = normalize_content_blocks(run.inbound_instruction.content)
        if not inbound_blocks:
            return None
        message = self.session_service.append_message(
            AppendSessionMessageInput(
                session_key=session_key,
                session_id=run.active_session_id,
                role="user",
                content_payload={"blocks": inbound_blocks},
                source_kind="orchestration_run",
                source_id=run.id,
                metadata={
                    "source": run.inbound_instruction.source,
                    "inbound_metadata": dict(run.inbound_instruction.metadata),
                },
            ),
        )
        return message.id

    def append_assistant_response_message(
        self,
        *,
        session_key: str,
        active_session_id: str,
        invocation_id: str,
        response_text: str | None,
        structured_output: object | None,
        finish_reason: str | None,
        usage_payload: dict[str, object] | None,
    ) -> tuple[str, ...]:
        if response_text is None and structured_output is None:
            return ()
        content_payload: dict[str, object] = {}
        if response_text is not None:
            content_payload["blocks"] = [text_content_block(response_text)]
            content_payload["text"] = response_text
        if structured_output is not None:
            content_payload["structured_output"] = structured_output
        if finish_reason is not None:
            content_payload["finish_reason"] = finish_reason
        if usage_payload is not None:
            content_payload["usage"] = usage_payload
        assistant_message = self.session_service.append_message(
            AppendSessionMessageInput(
                session_key=session_key,
                session_id=active_session_id,
                role="assistant",
                content_payload=content_payload,
                source_kind="llm_invocation",
                source_id=invocation_id,
            ),
        )
        return (assistant_message.id,)

    def append_tool_call_messages(
        self,
        *,
        session_key: str,
        active_session_id: str,
        invocation_id: str,
        response_text: str | None,
        tool_calls: tuple[ToolCallIntent, ...],
    ) -> tuple[str, ...]:
        inputs: list[AppendSessionMessageInput] = []
        if response_text is not None and response_text.strip():
            inputs.append(
                AppendSessionMessageInput(
                    session_key=session_key,
                    session_id=active_session_id,
                    role="assistant",
                    content_payload={
                        "blocks": [text_content_block(response_text)],
                        "text": response_text,
                        "finish_reason": "tool_calls",
                    },
                    source_kind="llm_invocation",
                    source_id=invocation_id,
                ),
            )
        for tool_call in tool_calls:
            inputs.append(
                AppendSessionMessageInput(
                    session_key=session_key,
                    session_id=active_session_id,
                    role="assistant",
                    content_payload={
                        "type": "function_call",
                        "call_id": tool_call.id,
                        "name": tool_call.name,
                        "arguments": dict(tool_call.arguments),
                    },
                    source_kind="llm_invocation",
                    source_id=invocation_id,
                    metadata={
                        "tool_call_id": tool_call.id,
                        "tool_name": tool_call.name,
                    },
                ),
            )
        messages = self.session_service.append_messages(
            AppendSessionMessagesInput(messages=tuple(inputs)),
        )
        return tuple(message.id for message in messages)

    def append_tool_result_message(
        self,
        *,
        session_key: str,
        active_session_id: str,
        tool_call: ToolCallIntent,
        tool_run: ToolRun,
        source_kind: str,
        source_id: str,
    ) -> str:
        message = self.session_service.append_message(
            self._tool_result_message_input(
                session_key=session_key,
                active_session_id=active_session_id,
                tool_call=tool_call,
                tool_run=tool_run,
                source_kind=source_kind,
                source_id=source_id,
            ),
        )
        return message.id

    def append_tool_result_messages(
        self,
        *,
        session_key: str,
        active_session_id: str,
        items: tuple[tuple[ToolCallIntent, ToolRun, str, str], ...],
    ) -> tuple[str, ...]:
        inputs = tuple(
            self._tool_result_message_input(
                session_key=session_key,
                active_session_id=active_session_id,
                tool_call=tool_call,
                tool_run=tool_run,
                source_kind=source_kind,
                source_id=source_id,
            )
            for tool_call, tool_run, source_kind, source_id in items
        )
        messages = self.session_service.append_messages(
            AppendSessionMessagesInput(messages=inputs),
        )
        return tuple(message.id for message in messages)

    def _tool_result_message_input(
        self,
        *,
        session_key: str,
        active_session_id: str,
        tool_call: ToolCallIntent,
        tool_run: ToolRun,
        source_kind: str,
        source_id: str,
        payload: dict[str, object] | None = None,
    ) -> AppendSessionMessageInput:
        content_payload = payload or self._tool_result_payload(
            tool_call=tool_call,
            tool_run=tool_run,
        )
        return AppendSessionMessageInput(
            session_key=session_key,
            session_id=active_session_id,
            role="tool",
            kind=SessionMessageKind.TOOL_RESULT,
            content_payload=content_payload,
            source_kind=source_kind,
            source_id=source_id,
            metadata={
                "tool_call_id": tool_call.id,
                "tool_name": tool_call.name,
            },
        )

    @staticmethod
    def _tool_result_payload(
        *,
        tool_call: ToolCallIntent,
        tool_run: ToolRun,
    ) -> dict[str, object]:
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
            payload["content"] = [text_content_block(tool_run.error.message)]
        elif tool_run.status in {ToolRunStatus.CANCELLED, ToolRunStatus.TIMED_OUT}:
            payload["content"] = [
                text_content_block(_terminal_tool_run_status_message(tool_run)),
            ]
        return payload

    def append_completed_background_tool_results(
        self,
        run: OrchestrationRun,
        *,
        tool_runs: tuple[ToolRun, ...],
    ) -> tuple[str, ...]:
        session_key = str(run.metadata.get("session_key", "")).strip()
        if not session_key:
            raise OrchestrationValidationError(
                "Orchestration run metadata.session_key is required to append tool results.",
            )
        if run.active_session_id is None or not run.active_session_id.strip():
            raise OrchestrationValidationError(
                "Orchestration run active_session_id is required to append tool results.",
            )
        message_ids: list[str] = []
        for tool_run in tool_runs:
            existing = self.session_service.get_message_by_source(
                session_key=session_key,
                session_id=run.active_session_id,
                source_kind="tool_run",
                source_id=tool_run.id,
            )
            if existing is not None:
                message_ids.append(existing.id)
                continue
            tool_metadata = self._background_tool_result_reference(
                run=run,
                tool_run=tool_run,
            )
            message_id = self.append_tool_result_message(
                session_key=session_key,
                active_session_id=run.active_session_id,
                tool_call=ToolCallIntent(
                    id=tool_metadata["tool_call_id"],
                    name=tool_metadata["tool_name"],
                    arguments={},
                ),
                tool_run=tool_run,
                source_kind="tool_run",
                source_id=tool_run.id,
            )
            message_ids.append(message_id)
        return tuple(message_ids)

    def _background_tool_result_reference(
        self,
        *,
        run: OrchestrationRun,
        tool_run: ToolRun,
    ) -> dict[str, str]:
        if self.execution_item_lookup is None:
            raise OrchestrationValidationError(
                "Execution step item lookup is required to append background tool "
                "results.",
            )
        items = self.execution_item_lookup.find_execution_step_items_by_owner(
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
