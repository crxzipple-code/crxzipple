from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field

from crxzipple.modules.llm.application import InvokeLlmInput, LlmApplicationService
from crxzipple.modules.llm.domain import ToolCallIntent
from crxzipple.modules.orchestration.application.prompt_assembler import (
    PromptAssembler,
)
from crxzipple.modules.orchestration.application.tool_resolver import (
    ResolvedToolSet,
    ToolResolver,
)
from crxzipple.modules.orchestration.domain import (
    OrchestrationRun,
    OrchestrationValidationError,
)
from crxzipple.modules.session.application import (
    AppendSessionMessageInput,
    SessionApplicationService,
)
from crxzipple.modules.session.domain import SessionMessageKind
from crxzipple.modules.tool.application import ExecuteToolInput, ToolApplicationService
from crxzipple.modules.tool.domain import ToolRun, ToolRunStatus


@dataclass(frozen=True, slots=True)
class EngineAdvanceOutcome:
    llm_id: str
    llm_invocation_id: str
    response_text: str | None = None
    user_message_id: str | None = None
    assistant_message_ids: tuple[str, ...] = field(default_factory=tuple)
    tool_result_message_ids: tuple[str, ...] = field(default_factory=tuple)
    tool_call_names: tuple[str, ...] = field(default_factory=tuple)
    pending_tool_run_ids: tuple[str, ...] = field(default_factory=tuple)
    pending_background_tools: tuple[dict[str, str], ...] = field(default_factory=tuple)
    continue_loop: bool = False


@dataclass(slots=True)
class OrchestrationEngine:
    prompt_assembler: PromptAssembler
    session_service: SessionApplicationService
    llm_service: LlmApplicationService
    tool_resolver: ToolResolver
    tool_service: ToolApplicationService

    def advance_once(self, run: OrchestrationRun) -> EngineAdvanceOutcome:
        session_key = str(run.metadata.get("session_key", "")).strip()
        if not session_key:
            raise OrchestrationValidationError(
                "Orchestration run metadata.session_key is required for engine execution.",
            )
        if run.active_session_id is None or not run.active_session_id.strip():
            raise OrchestrationValidationError(
                "Orchestration run active_session_id is required for engine execution.",
            )

        user_message_id = self._ensure_inbound_message(run, session_key=session_key)
        resolved_tools = self.tool_resolver.resolve(run)
        prompt = self.prompt_assembler.assemble(run)
        invocation = self.llm_service.invoke(
            InvokeLlmInput(
                llm_id=prompt.llm_id,
                messages=prompt.messages,
                tool_schemas=resolved_tools.schemas,
            ),
        )
        if invocation.result is None:
            if invocation.error is not None:
                raise OrchestrationValidationError(
                    "LLM invocation failed "
                    f"[{invocation.error.code}]: {invocation.error.message}",
                )
            raise OrchestrationValidationError(
                "LLM invocation completed without a result payload.",
            )

        tool_call_names = tuple(
            tool_call.name
            for tool_call in invocation.result.tool_calls
        )
        assistant_message_ids: list[str] = []
        tool_result_message_ids: list[str] = []
        pending_tool_run_ids: list[str] = []
        pending_background_tools: list[dict[str, str]] = []

        if tool_call_names:
            assistant_message_ids.extend(
                self._append_tool_call_messages(
                    session_key=session_key,
                    active_session_id=prompt.active_session_id,
                    invocation_id=invocation.id,
                    response_text=invocation.result.text,
                    tool_calls=invocation.result.tool_calls,
                ),
            )
            inline_tool_runs, background_tool_runs = self._execute_tool_calls(
                run,
                session_key=session_key,
                active_session_id=prompt.active_session_id,
                resolved_tools=resolved_tools,
                tool_calls=invocation.result.tool_calls,
            )
            tool_result_message_ids.extend(
                message_id
                for message_id, _ in inline_tool_runs
            )
            pending_tool_run_ids.extend(
                tool_run.id
                for _, tool_run in background_tool_runs
            )
            pending_background_tools.extend(
                {
                    "tool_run_id": tool_run.id,
                    "tool_call_id": tool_call.id,
                    "tool_name": tool_call.name,
                }
                for tool_call, tool_run in background_tool_runs
            )
        else:
            assistant_message_ids.extend(
                self._append_assistant_response_message(
                    session_key=session_key,
                    active_session_id=prompt.active_session_id,
                    invocation_id=invocation.id,
                    response_text=invocation.result.text,
                    structured_output=invocation.result.structured_output,
                    finish_reason=invocation.result.finish_reason,
                    usage_payload=(
                        invocation.result.usage.to_payload()
                        if invocation.result.usage is not None
                        else None
                    ),
                ),
            )

        return EngineAdvanceOutcome(
            llm_id=prompt.llm_id,
            llm_invocation_id=invocation.id,
            response_text=invocation.result.text,
            user_message_id=user_message_id,
            assistant_message_ids=tuple(assistant_message_ids),
            tool_result_message_ids=tuple(tool_result_message_ids),
            tool_call_names=tool_call_names,
            pending_tool_run_ids=tuple(pending_tool_run_ids),
            pending_background_tools=tuple(pending_background_tools),
            continue_loop=bool(tool_call_names) and not pending_tool_run_ids,
        )

    def _ensure_inbound_message(
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
        if run.inbound_instruction.content is None or not run.inbound_instruction.content.strip():
            return None
        message = self.session_service.append_message(
            AppendSessionMessageInput(
                session_key=session_key,
                session_id=run.active_session_id,
                role="user",
                content=run.inbound_instruction.content,
                source_kind="orchestration_run",
                source_id=run.id,
                metadata={
                    "source": run.inbound_instruction.source,
                    "inbound_metadata": dict(run.inbound_instruction.metadata),
                },
            ),
        )
        return message.id

    def _append_assistant_response_message(
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
                content=response_text,
                content_payload=content_payload,
                source_kind="llm_invocation",
                source_id=invocation_id,
            ),
        )
        return (assistant_message.id,)

    def _append_tool_call_messages(
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
                self._append_assistant_response_message(
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
                    metadata={"tool_call_id": tool_call.id},
                ),
            )
            message_ids.append(message.id)
        return tuple(message_ids)

    def _execute_tool_calls(
        self,
        run: OrchestrationRun,
        *,
        session_key: str,
        active_session_id: str,
        resolved_tools: ResolvedToolSet,
        tool_calls: tuple[ToolCallIntent, ...],
    ) -> tuple[list[tuple[str, ToolRun]], list[tuple[ToolCallIntent, ToolRun]]]:
        inline_runs: list[tuple[str, ToolRun]] = []
        background_runs: list[tuple[ToolCallIntent, ToolRun]] = []
        for tool_call in tool_calls:
            resolved_tool = resolved_tools.by_name(tool_call.name)
            if resolved_tool is None:
                raise OrchestrationValidationError(
                    f"Tool call '{tool_call.name}' is not available in this orchestration run.",
                )
            tool_run = asyncio.run(
                self.tool_service.execute(
                    ExecuteToolInput(
                        tool_id=resolved_tool.tool.id,
                        arguments=dict(tool_call.arguments),
                        mode=resolved_tool.target.mode,
                        strategy=resolved_tool.target.strategy,
                        environment=resolved_tool.target.environment,
                    ),
                ),
            )
            if tool_run.status is ToolRunStatus.QUEUED:
                background_runs.append((tool_call, tool_run))
                continue
            message_id = self._append_tool_result_message(
                session_key=session_key,
                active_session_id=active_session_id,
                tool_call=tool_call,
                tool_run=tool_run,
                source_kind="tool_run",
                source_id=tool_run.id,
            )
            inline_runs.append((message_id, tool_run))
        return inline_runs, background_runs

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
            message_id = self._append_tool_result_message(
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

    def _append_tool_result_message(
        self,
        *,
        session_key: str,
        active_session_id: str,
        tool_call: ToolCallIntent,
        tool_run: ToolRun,
        source_kind: str,
        source_id: str,
    ) -> str:
        payload: dict[str, object] = {
            "tool_name": tool_call.name,
            "tool_call_id": tool_call.id,
            "tool_run_id": tool_run.id,
            "status": tool_run.status.value,
        }
        content: str | None = None
        if tool_run.output_payload is not None:
            payload["output"] = tool_run.output_payload
            content = self._stringify_payload(tool_run.output_payload)
        if tool_run.error is not None:
            payload["error"] = tool_run.error.to_storage()
            content = self._stringify_payload(
                {
                    "message": tool_run.error.message,
                    "code": tool_run.error.code,
                    "details": dict(tool_run.error.details),
                },
            )
        message = self.session_service.append_message(
            AppendSessionMessageInput(
                session_key=session_key,
                session_id=active_session_id,
                role="tool",
                kind=SessionMessageKind.TOOL_RESULT,
                content=content,
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

    @staticmethod
    def _stringify_payload(payload: object) -> str:
        if isinstance(payload, str):
            return payload
        return json.dumps(payload, ensure_ascii=True, sort_keys=True)

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
