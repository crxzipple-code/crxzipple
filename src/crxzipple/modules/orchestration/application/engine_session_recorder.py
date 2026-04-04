from __future__ import annotations

from dataclasses import dataclass

from crxzipple.modules.llm.domain import ToolCallIntent
from crxzipple.modules.orchestration.domain import (
    OrchestrationRun,
    OrchestrationValidationError,
)
from crxzipple.modules.session.application import (
    AppendSessionMessageInput,
    SessionApplicationService,
)
from crxzipple.modules.session.domain import SessionMessageKind
from crxzipple.modules.tool.domain import ToolRun
from crxzipple.shared.content_blocks import (
    normalize_content_blocks,
    text_content_block,
)


@dataclass(slots=True)
class OrchestrationSessionRecorder:
    session_service: SessionApplicationService

    def ensure_inbound_message(
        self,
        run: OrchestrationRun,
        *,
        session_key: str,
    ) -> str | None:
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
        message_ids: list[str] = []
        if response_text is not None and response_text.strip():
            message_ids.extend(
                self.append_assistant_response_message(
                    session_key=session_key,
                    active_session_id=active_session_id,
                    invocation_id=invocation_id,
                    response_text=response_text,
                    structured_output=None,
                    finish_reason="tool_calls",
                    usage_payload=None,
                ),
            )
        for tool_call in tool_calls:
            message = self.session_service.append_message(
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
            message_ids.append(message.id)
        return tuple(message_ids)

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
        if tool_run.error is not None:
            payload["error"] = tool_run.error.to_storage()
            payload["content"] = [text_content_block(tool_run.error.message)]
        message = self.session_service.append_message(
            AppendSessionMessageInput(
                session_key=session_key,
                session_id=active_session_id,
                role="tool",
                kind=SessionMessageKind.TOOL_RESULT,
                content_payload=payload,
                source_kind=source_kind,
                source_id=source_id,
                metadata={
                    "tool_call_id": tool_call.id,
                    "tool_name": tool_call.name,
                },
            ),
        )
        return message.id

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
        pending_mapping = self._pending_background_tool_mapping(run)
        message_ids: list[str] = []
        for tool_run in tool_runs:
            existing = self.session_service.get_message_by_source(
                session_key=session_key,
                session_id=run.active_session_id,
                source_kind="tool_run",
                source_id=tool_run.id,
            )
            if existing is not None:
                continue
            tool_metadata = pending_mapping.get(
                tool_run.id,
                {
                    "tool_call_id": tool_run.id,
                    "tool_name": tool_run.tool_id,
                },
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

    @staticmethod
    def _pending_background_tool_mapping(
        run: OrchestrationRun,
    ) -> dict[str, dict[str, str]]:
        raw_items = run.metadata.get("pending_background_tools")
        if not isinstance(raw_items, list):
            return {}
        mapping: dict[str, dict[str, str]] = {}
        for item in raw_items:
            if not isinstance(item, dict):
                continue
            tool_run_id = item.get("tool_run_id")
            tool_call_id = item.get("tool_call_id")
            tool_name = item.get("tool_name")
            if not isinstance(tool_run_id, str) or not tool_run_id.strip():
                continue
            if not isinstance(tool_call_id, str) or not tool_call_id.strip():
                continue
            if not isinstance(tool_name, str) or not tool_name.strip():
                continue
            mapping[tool_run_id] = {
                "tool_call_id": tool_call_id,
                "tool_name": tool_name,
            }
        return mapping
