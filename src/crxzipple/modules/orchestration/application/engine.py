from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from crxzipple.modules.llm.application import InvokeLlmInput, StreamLlmInput
from crxzipple.modules.llm.domain import (
    LlmAdapterNotConfiguredError,
    LlmMessage,
    ToolCallIntent,
    ToolSchema,
)
from crxzipple.modules.orchestration.application.ports import (
    LlmPort,
    MemoryPort,
    ToolExecutionPort,
)
from crxzipple.modules.orchestration.application.prompting import PromptReport
from crxzipple.modules.orchestration.application.prompting import PromptMode
from crxzipple.modules.orchestration.application.skill_requests import (
    SkillRequestSurface,
    is_skill_request_tool_name,
)
from crxzipple.modules.orchestration.application.prompt_assembler import (
    PromptAssembler,
    PromptEnvelope,
)
from crxzipple.modules.orchestration.application.tool_resolver import ResolvedToolSet, ToolResolver
from crxzipple.modules.orchestration.domain import (
    OrchestrationRun,
    OrchestrationValidationError,
    PendingApprovalRequest,
)
from crxzipple.modules.session.application import (
    AppendSessionMessageInput,
    SessionApplicationService,
)
from crxzipple.modules.session.domain import SessionMessageKind
from crxzipple.modules.tool.application import ExecuteToolInput
from crxzipple.modules.tool.domain import (
    ToolEnvironment,
    ToolExecutionStrategy,
    ToolExecutionTarget,
    ToolMode,
    ToolRun,
    ToolRunStatus,
)
from crxzipple.shared.domain.effects import get_effect_descriptor


@dataclass(frozen=True, slots=True)
class WorkspaceContextDebugEntry:
    path: str
    chars: int


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
    pending_approval_request: PendingApprovalRequest | None = None
    prompt_report: PromptReport | None = None
    workspace_context_workspace: str | None = None
    workspace_context_files: tuple[WorkspaceContextDebugEntry, ...] = field(default_factory=tuple)
    continue_loop: bool = False


@dataclass(frozen=True, slots=True)
class PromptPreview:
    llm_id: str
    mode: PromptMode
    messages: tuple[LlmMessage, ...]
    tool_schemas: tuple[ToolSchema, ...] = field(default_factory=tuple)
    prompt_report: PromptReport | None = None
    workspace_context_workspace: str | None = None
    workspace_context_files: tuple[WorkspaceContextDebugEntry, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class _PromptSurface:
    prompt: PromptEnvelope
    resolved_tools: ResolvedToolSet
    workspace_context_files: tuple[WorkspaceContextDebugEntry, ...]


@dataclass(frozen=True, slots=True)
class _ToolExecutionBatchOutcome:
    tool_call_message_ids: tuple[str, ...] = ()
    inline_runs: tuple[tuple[str, ToolRun], ...] = ()
    background_runs: tuple[tuple[ToolCallIntent, ToolRun], ...] = ()
    pending_approval_request: PendingApprovalRequest | None = None


@dataclass(slots=True)
class OrchestrationEngine:
    prompt_assembler: PromptAssembler
    session_service: SessionApplicationService
    llm_port: LlmPort
    tool_resolver: ToolResolver
    tool_execution_port: ToolExecutionPort
    memory_port: MemoryPort | None = None

    def preview_prompt(self, run: OrchestrationRun) -> PromptPreview:
        surface = self._build_prompt_surface(run)
        return PromptPreview(
            llm_id=surface.prompt.llm_id,
            mode=surface.prompt.mode,
            messages=surface.prompt.messages,
            tool_schemas=surface.prompt.tool_schemas,
            prompt_report=surface.prompt.report,
            workspace_context_workspace=surface.prompt.workspace_dir,
            workspace_context_files=surface.workspace_context_files,
        )

    def advance_once(
        self,
        run: OrchestrationRun,
        *,
        on_llm_stream_update: Callable[[str, str], None] | None = None,
    ) -> EngineAdvanceOutcome:
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
        surface = self._build_prompt_surface(run)
        resolved_tools = surface.resolved_tools
        prompt = surface.prompt
        prompt_mode = prompt.mode
        skill_request = prompt.skill_request
        workspace_context_files = surface.workspace_context_files
        invocation = self._invoke_llm(
            llm_id=prompt.llm_id,
            messages=prompt.messages,
            tool_schemas=prompt.tool_schemas,
            on_llm_stream_update=on_llm_stream_update,
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
            skill_request_call = (
                skill_request.extract_requested_skill(
                    invocation.result.tool_calls,
                )
                if skill_request is not None
                else None
            )
            if invocation.result.text is not None and invocation.result.text.strip():
                assistant_message_ids.extend(
                    self._append_assistant_response_message(
                        session_key=session_key,
                        active_session_id=prompt.active_session_id,
                        invocation_id=invocation.id,
                        response_text=invocation.result.text,
                        structured_output=None,
                        finish_reason="tool_calls",
                        usage_payload=None,
                    ),
                )
            if skill_request_call is not None:
                assistant_message_ids.extend(
                    self._append_tool_call_messages(
                        session_key=session_key,
                        active_session_id=prompt.active_session_id,
                        invocation_id=invocation.id,
                        response_text=None,
                        tool_calls=invocation.result.tool_calls,
                    ),
                )
                tool_result_message_ids.append(
                    self._append_skill_result_message(
                        session_key=session_key,
                        active_session_id=prompt.active_session_id,
                        tool_call_id=invocation.result.tool_calls[0].id,
                        skill=skill_request_call,
                        skill_request=skill_request,
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
                    prompt_report=prompt.report,
                    workspace_context_workspace=prompt.workspace_dir,
                    workspace_context_files=workspace_context_files,
                    continue_loop=True,
                )
            execution_outcome = self._execute_tool_calls(
                run,
                session_key=session_key,
                active_session_id=prompt.active_session_id,
                resolved_tools=resolved_tools,
                tool_calls=invocation.result.tool_calls,
                append_tool_call_messages=True,
            )
            assistant_message_ids.extend(execution_outcome.tool_call_message_ids)
            tool_result_message_ids.extend(
                message_id
                for message_id, _ in execution_outcome.inline_runs
            )
            pending_tool_run_ids.extend(
                tool_run.id
                for _, tool_run in execution_outcome.background_runs
            )
            pending_background_tools.extend(
                {
                    "tool_run_id": tool_run.id,
                    "tool_call_id": tool_call.id,
                    "tool_name": tool_call.name,
                }
                for tool_call, tool_run in execution_outcome.background_runs
            )
            if execution_outcome.pending_approval_request is not None:
                return EngineAdvanceOutcome(
                    llm_id=prompt.llm_id,
                    llm_invocation_id=invocation.id,
                    response_text=invocation.result.text,
                    user_message_id=user_message_id,
                    assistant_message_ids=tuple(assistant_message_ids),
                    tool_result_message_ids=tuple(tool_result_message_ids),
                    tool_call_names=tool_call_names,
                    pending_approval_request=execution_outcome.pending_approval_request,
                    prompt_report=prompt.report,
                    workspace_context_workspace=prompt.workspace_dir,
                    workspace_context_files=workspace_context_files,
                )
        else:
            if prompt_mode is PromptMode.MEMORY_FLUSH:
                return EngineAdvanceOutcome(
                    llm_id=prompt.llm_id,
                    llm_invocation_id=invocation.id,
                    response_text=invocation.result.text,
                    user_message_id=user_message_id,
                    tool_result_message_ids=tuple(tool_result_message_ids),
                    tool_call_names=tool_call_names,
                    prompt_report=prompt.report,
                    workspace_context_workspace=prompt.workspace_dir,
                    workspace_context_files=workspace_context_files,
                )
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
            prompt_report=prompt.report,
            workspace_context_workspace=prompt.workspace_dir,
            workspace_context_files=workspace_context_files,
            continue_loop=bool(tool_call_names) and not pending_tool_run_ids,
        )

    def _invoke_llm(
        self,
        *,
        llm_id: str,
        messages: tuple,
        tool_schemas: tuple,
        on_llm_stream_update: Callable[[str, str], None] | None = None,
    ):
        try:
            events = self.llm_port.stream_invoke(
                StreamLlmInput(
                    llm_id=llm_id,
                    messages=messages,
                    tool_schemas=tool_schemas,
                ),
            )
        except LlmAdapterNotConfiguredError:
            return self.llm_port.invoke(
                InvokeLlmInput(
                    llm_id=llm_id,
                    messages=messages,
                    tool_schemas=tool_schemas,
                ),
            )

        invocation_id: str | None = None
        streamed_text = ""
        for event in events:
            if event.invocation_id:
                invocation_id = event.invocation_id
            if event.type == "invocation_started":
                if invocation_id is not None and on_llm_stream_update is not None:
                    on_llm_stream_update(invocation_id, "")
                continue
            if event.type == "text_delta":
                delta = event.data.get("text")
                if delta is not None:
                    streamed_text += str(delta)
                    if invocation_id is not None and on_llm_stream_update is not None:
                        on_llm_stream_update(invocation_id, streamed_text)
                continue
            if event.type == "failed":
                error_payload = event.data.get("error")
                if isinstance(error_payload, dict):
                    message = str(error_payload.get("message") or "LLM stream failed.")
                    code = str(error_payload.get("code") or "stream_failed")
                    raise OrchestrationValidationError(
                        f"LLM invocation failed [{code}]: {message}",
                    )
                raise OrchestrationValidationError("LLM invocation failed [stream_failed].")

        if invocation_id is None:
            raise OrchestrationValidationError(
                "Streaming llm invocation ended before an invocation id was produced.",
            )
        return self.llm_port.get_invocation(invocation_id)

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
                    metadata={
                        "tool_call_id": tool_call.id,
                        "tool_name": tool_call.name,
                        "synthetic_skill_request": (
                            is_skill_request_tool_name(tool_call.name)
                        ),
                    },
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
        append_tool_call_messages: bool,
    ) -> _ToolExecutionBatchOutcome:
        tool_call_message_ids: list[str] = []
        inline_runs: list[tuple[str, ToolRun]] = []
        background_runs: list[tuple[ToolCallIntent, ToolRun]] = []
        for tool_call in tool_calls:
            if is_skill_request_tool_name(tool_call.name):
                raise OrchestrationValidationError(
                    "Skill request tool calls must be handled before tool execution.",
                )
            resolved_tool = resolved_tools.by_name(tool_call.name)
            if resolved_tool is None:
                raise OrchestrationValidationError(
                    f"Tool call '{tool_call.name}' is not available in this orchestration run.",
                )
            if append_tool_call_messages:
                tool_call_message_ids.extend(
                    self._append_tool_call_messages(
                        session_key=session_key,
                        active_session_id=active_session_id,
                        invocation_id="",
                        response_text=None,
                        tool_calls=(tool_call,),
                    ),
                )
            execution_decision = self.tool_resolver.execution_decision(
                run,
                tool=resolved_tool.tool,
                target=resolved_tool.target,
            )
            if execution_decision.mode == "blocked":
                raise OrchestrationValidationError(
                    f"Tool call '{tool_call.name}' is not allowed in this orchestration run.",
                )
            if execution_decision.mode == "approval_required":
                approval = execution_decision.approval
                if approval is None:
                    raise OrchestrationValidationError(
                        f"Tool call '{tool_call.name}' requires approval but no approval details were provided.",
                    )
                return _ToolExecutionBatchOutcome(
                    tool_call_message_ids=tuple(tool_call_message_ids),
                    inline_runs=tuple(inline_runs),
                    background_runs=tuple(background_runs),
                    pending_approval_request=PendingApprovalRequest(
                        request_id=tool_call.id,
                        effect_id=approval.id,
                        label=approval.label,
                        reason=(
                            f"Run {tool_call.name} with the current arguments to complete the next step."
                        ),
                        tool_ids=approval.tool_ids,
                        tool_name=tool_call.name,
                        tool_arguments=dict(tool_call.arguments),
                        execution_mode=resolved_tool.target.mode.value,
                        execution_strategy=resolved_tool.target.strategy.value,
                        execution_environment=resolved_tool.target.environment.value,
                    ),
                )
            execution_arguments = dict(tool_call.arguments)
            if self.memory_port is not None and self.memory_port.is_memory_tool_name(
                tool_call.name,
            ):
                if run.agent_id is None or not run.agent_id.strip():
                    raise OrchestrationValidationError(
                        "Memory lookup tools require run.agent_id.",
                    )
                execution_arguments = self.memory_port.inject_tool_context(
                    execution_arguments,
                    agent_id=run.agent_id,
                )
            tool_run = asyncio.run(
                self.tool_execution_port.execute(
                    ExecuteToolInput(
                        tool_id=resolved_tool.tool.id,
                        arguments=execution_arguments,
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
        return _ToolExecutionBatchOutcome(
            tool_call_message_ids=tuple(tool_call_message_ids),
            inline_runs=tuple(inline_runs),
            background_runs=tuple(background_runs),
        )

    def replay_approved_tool_call(
        self,
        run: OrchestrationRun,
        *,
        request: PendingApprovalRequest,
    ) -> _ToolExecutionBatchOutcome:
        if (
            request.tool_name is None
            or request.execution_mode is None
            or request.execution_strategy is None
            or request.execution_environment is None
        ):
            return _ToolExecutionBatchOutcome()
        session_key = str(run.metadata.get("session_key", "")).strip()
        if not session_key or run.active_session_id is None or not run.active_session_id.strip():
            raise OrchestrationValidationError(
                "Approved tool replay requires a bound session.",
            )
        resolved_tool = self.tool_resolver.resolve(run).by_name(request.tool_name)
        if resolved_tool is None:
            raise OrchestrationValidationError(
                f"Approved tool '{request.tool_name}' is not available after approval.",
            )
        target = self._target_from_approval_request(request)
        if not resolved_tool.tool.supports(target):
            raise OrchestrationValidationError(
                "Approved tool replay target is no longer supported for "
                f"'{request.tool_name}' "
                f"({target.mode.value}/{target.strategy.value}/{target.environment.value}).",
            )
        return self._execute_tool_calls(
            run,
            session_key=session_key,
            active_session_id=run.active_session_id,
            resolved_tools=ResolvedToolSet(
                tools=(
                    type(resolved_tool)(
                        tool=resolved_tool.tool,
                        schema=resolved_tool.schema,
                        target=target,
                    ),
                ),
            ),
            tool_calls=(
                ToolCallIntent(
                    id=request.request_id,
                    name=request.tool_name,
                    arguments=dict(request.tool_arguments),
                ),
            ),
            append_tool_call_messages=False,
        )

    @staticmethod
    def _target_from_approval_request(
        request: PendingApprovalRequest,
    ) -> ToolExecutionTarget:
        try:
            return ToolExecutionTarget(
                mode=ToolMode(str(request.execution_mode)),
                strategy=ToolExecutionStrategy(str(request.execution_strategy)),
                environment=ToolEnvironment(str(request.execution_environment)),
            )
        except ValueError as exc:
            raise OrchestrationValidationError(
                "Approved tool replay target is invalid or incomplete.",
            ) from exc

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

    def _append_skill_result_message(
        self,
        *,
        session_key: str,
        active_session_id: str,
        tool_call_id: str,
        skill,
        skill_request: SkillRequestSurface,
    ) -> str:
        content = skill_request.render_tool_result(skill)
        message = self.session_service.append_message(
            AppendSessionMessageInput(
                session_key=session_key,
                session_id=active_session_id,
                role="tool",
                kind=SessionMessageKind.TOOL_RESULT,
                content=content,
                content_payload={
                    "tool_name": skill_request.tool_name,
                    "tool_call_id": tool_call_id,
                    "skill_name": skill.name,
                    "skill_path": skill.path,
                    "skill_source": skill.source,
                },
                source_kind="skill_request",
                source_id=skill.name,
                metadata={
                    "tool_call_id": tool_call_id,
                    "tool_name": skill_request.tool_name,
                    "skill_name": skill.name,
                },
            ),
        )
        return message.id

    @staticmethod
    def _stringify_payload(payload: object) -> str:
        if isinstance(payload, str):
            return payload
        return json.dumps(payload, ensure_ascii=True, sort_keys=True)

    def _build_prompt_surface(
        self,
        run: OrchestrationRun,
    ) -> _PromptSurface:
        resolved_tools = self.tool_resolver.resolve(run)
        prompt = self.prompt_assembler.assemble(
            run,
            resolved_tools=resolved_tools,
        )
        workspace_context_files = tuple(
            WorkspaceContextDebugEntry(
                path=context_file.path,
                chars=len(context_file.content),
            )
            for context_file in prompt.context_files
        )
        return _PromptSurface(
            prompt=prompt,
            resolved_tools=resolved_tools,
            workspace_context_files=workspace_context_files,
        )

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
