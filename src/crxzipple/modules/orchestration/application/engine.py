from __future__ import annotations
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from crxzipple.modules.llm.domain import (
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
from crxzipple.modules.orchestration.application.skill_requests import SkillRequestSurface
from crxzipple.modules.orchestration.application.prompt_assembler import (
    PromptAssembler,
    PromptEnvelope,
)
from crxzipple.modules.orchestration.application.engine_session_recorder import (
    OrchestrationSessionRecorder,
)
from crxzipple.modules.orchestration.application.engine_llm_invoker import (
    OrchestrationEngineLlmInvoker,
)
from crxzipple.modules.orchestration.application.engine_tool_executor import (
    OrchestrationEngineToolExecutor,
    ToolExecutionBatchOutcome,
)
from crxzipple.modules.orchestration.application.tool_resolver import ResolvedToolSet, ToolResolver
from crxzipple.modules.orchestration.domain import (
    OrchestrationRun,
    OrchestrationValidationError,
    PendingApprovalRequest,
)
from crxzipple.modules.tool.domain import (
    ToolRun,
)


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


@dataclass(slots=True)
class OrchestrationEngine:
    prompt_assembler: PromptAssembler
    session_recorder: OrchestrationSessionRecorder
    llm_port: LlmPort
    tool_resolver: ToolResolver
    tool_execution_port: ToolExecutionPort
    memory_port: MemoryPort | None = None
    llm_invoker: OrchestrationEngineLlmInvoker = field(init=False)
    tool_executor: OrchestrationEngineToolExecutor = field(init=False)

    def __post_init__(self) -> None:
        self.llm_invoker = OrchestrationEngineLlmInvoker(
            llm_port=self.llm_port,
        )
        self.tool_executor = OrchestrationEngineToolExecutor(
            session_recorder=self.session_recorder,
            tool_resolver=self.tool_resolver,
            tool_execution_port=self.tool_execution_port,
            memory_port=self.memory_port,
        )

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

        user_message_id = self.session_recorder.ensure_inbound_message(
            run,
            session_key=session_key,
        )
        surface = self._build_prompt_surface(run)
        resolved_tools = surface.resolved_tools
        prompt = surface.prompt
        prompt_mode = prompt.mode
        skill_request = prompt.skill_request
        workspace_context_files = surface.workspace_context_files
        invocation = self.llm_invoker.invoke(
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
                    self.session_recorder.append_assistant_response_message(
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
                    self.session_recorder.append_tool_call_messages(
                        session_key=session_key,
                        active_session_id=prompt.active_session_id,
                        invocation_id=invocation.id,
                        response_text=None,
                        tool_calls=invocation.result.tool_calls,
                    ),
                )
                tool_result_message_ids.append(
                    self.session_recorder.append_skill_result_message(
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
            execution_outcome = self.tool_executor.execute_tool_calls(
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
                self.session_recorder.append_assistant_response_message(
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

    def replay_approved_tool_call(
        self,
        run: OrchestrationRun,
        *,
        request: PendingApprovalRequest,
    ) -> ToolExecutionBatchOutcome:
        return self.tool_executor.replay_approved_tool_call(
            run,
            request=request,
        )

    def append_completed_background_tool_results(
        self,
        run: OrchestrationRun,
        *,
        tool_runs: tuple[ToolRun, ...],
    ) -> tuple[str, ...]:
        return self.session_recorder.append_completed_background_tool_results(
            run,
            tool_runs=tool_runs,
        )

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
