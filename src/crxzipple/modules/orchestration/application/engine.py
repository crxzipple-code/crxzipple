from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import dataclass, field, replace
from typing import Any

from crxzipple.core.logger import get_logger
from crxzipple.modules.llm.domain import (
    LlmMessage,
    LlmMessageRole,
    ToolSchema,
)
from crxzipple.modules.memory.application import MemoryRuntimePort
from crxzipple.modules.orchestration.application.ports import (
    ContextRenderSnapshotRecord,
    ContextRenderSnapshotPort,
    LlmPort,
    ToolExecutionPort,
)
from crxzipple.modules.orchestration.application.prompting import (
    ContextRenderReport,
    PromptReport,
)
from crxzipple.modules.orchestration.application.prompting import PromptMode
from crxzipple.modules.orchestration.application.prompt_surface import (
    PromptSurfaceBuilder,
    PromptSurface,
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
from crxzipple.shared.runtime_metrics import (
    RuntimeMetricsRegistry,
    get_runtime_metrics_registry,
)
from crxzipple.shared.content_blocks import text_content_block

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class EngineAdvanceOutcome:
    llm_id: str
    llm_invocation_id: str
    response_text: str | None = None
    user_message_id: str | None = None
    assistant_message_ids: tuple[str, ...] = field(default_factory=tuple)
    tool_result_message_ids: tuple[str, ...] = field(default_factory=tuple)
    inline_tool_run_ids: tuple[str, ...] = field(default_factory=tuple)
    tool_call_names: tuple[str, ...] = field(default_factory=tuple)
    pending_tool_run_ids: tuple[str, ...] = field(default_factory=tuple)
    pending_background_tools: tuple[dict[str, str], ...] = field(default_factory=tuple)
    pending_approval_request: PendingApprovalRequest | None = None
    prompt_report: PromptReport | None = None
    context_render_snapshot_id: str | None = None
    yield_requested: bool = False
    yield_reason: str | None = None
    continue_loop: bool = False


@dataclass(frozen=True, slots=True)
class PromptSurfacePreview:
    llm_id: str
    mode: PromptMode
    messages: tuple[LlmMessage, ...]
    tool_schemas: tuple[ToolSchema, ...] = field(default_factory=tuple)
    prompt_report: PromptReport | None = None


@dataclass(frozen=True, slots=True)
class _PromptSurface:
    prompt: PromptSurface
    resolved_tools: ResolvedToolSet


@dataclass(frozen=True, slots=True)
class _AdvanceContext:
    session_key: str
    user_message_id: str | None
    prompt: PromptSurface
    resolved_tools: ResolvedToolSet
    context_render_snapshot_id: str | None = None


@dataclass(slots=True)
class OrchestrationEngine:
    prompt_surface: PromptSurfaceBuilder
    session_recorder: OrchestrationSessionRecorder
    llm_port: LlmPort
    tool_resolver: ToolResolver
    tool_execution_port: ToolExecutionPort
    memory_port: MemoryRuntimePort | None = None
    context_snapshot_port: ContextRenderSnapshotPort | None = None
    detailed_phase_metrics_enabled: bool = False
    metrics: RuntimeMetricsRegistry = field(
        default_factory=get_runtime_metrics_registry,
    )
    llm_invoker: OrchestrationEngineLlmInvoker = field(init=False)
    tool_executor: OrchestrationEngineToolExecutor = field(init=False)

    def __post_init__(self) -> None:
        self.prompt_surface.detailed_phase_metrics_enabled = (
            self.detailed_phase_metrics_enabled
        )
        self.prompt_surface.metrics = self.metrics
        self.llm_invoker = OrchestrationEngineLlmInvoker(
            llm_port=self.llm_port,
            metrics=self.metrics,
        )
        self.tool_executor = OrchestrationEngineToolExecutor(
            session_recorder=self.session_recorder,
            tool_resolver=self.tool_resolver,
            tool_execution_port=self.tool_execution_port,
            detailed_phase_metrics_enabled=self.detailed_phase_metrics_enabled,
            metrics=self.metrics,
        )

    def preview_prompt(self, run: OrchestrationRun) -> PromptSurfacePreview:
        surface = self._build_prompt_surface(run)
        return PromptSurfacePreview(
            llm_id=surface.prompt.llm_id,
            mode=surface.prompt.mode,
            messages=surface.prompt.messages,
            tool_schemas=surface.prompt.tool_schemas,
            prompt_report=surface.prompt.report,
        )

    def advance_once(
        self,
        run: OrchestrationRun,
        *,
        on_llm_stream_update: Callable[[str, str, str | None], None] | None = None,
    ) -> EngineAdvanceOutcome:
        with self._timed_phase("build_context"):
            context = self._build_advance_context(run)
        with self._timed_phase("llm_invoke"):
            invocation = self.llm_invoker.invoke(
                llm_id=context.prompt.llm_id,
                messages=context.prompt.messages,
                tool_schemas=context.prompt.tool_schemas,
                require_tool_call=context.prompt.surface_policy.require_tool_call,
                on_llm_stream_update=on_llm_stream_update,
            )
        self._validate_invocation_result(invocation)

        assert invocation.result is not None
        if invocation.result.tool_calls:
            return self._advance_outcome_for_tool_calls(
                run,
                context=context,
                invocation=invocation,
            )
        return self._advance_outcome_for_message_only(
            context=context,
            invocation=invocation,
        )

    async def advance_once_async(
        self,
        run: OrchestrationRun,
        *,
        on_llm_stream_update: Callable[[str, str, str | None], None] | None = None,
    ) -> EngineAdvanceOutcome:
        with self._timed_phase("build_context"):
            context = await asyncio.to_thread(self._build_advance_context, run)
        with self._timed_phase("llm_invoke"):
            invocation = await self.llm_invoker.invoke_async(
                llm_id=context.prompt.llm_id,
                messages=context.prompt.messages,
                tool_schemas=context.prompt.tool_schemas,
                require_tool_call=context.prompt.surface_policy.require_tool_call,
                on_llm_stream_update=on_llm_stream_update,
            )
        self._validate_invocation_result(invocation)

        assert invocation.result is not None
        if invocation.result.tool_calls:
            return await self._advance_outcome_for_tool_calls_async(
                run,
                context=context,
                invocation=invocation,
            )
        return await asyncio.to_thread(
            self._advance_outcome_for_message_only,
            context=context,
            invocation=invocation,
        )

    def _build_advance_context(self, run: OrchestrationRun) -> _AdvanceContext:
        session_key = str(run.metadata.get("session_key", "")).strip()
        if not session_key:
            raise OrchestrationValidationError(
                "Orchestration run metadata.session_key is required for engine execution.",
            )
        if run.active_session_id is None or not run.active_session_id.strip():
            raise OrchestrationValidationError(
                "Orchestration run active_session_id is required for engine execution.",
            )

        with self._timed_phase("ensure_inbound_message", detailed=True):
            user_message_id = self.session_recorder.ensure_inbound_message(
                run,
                session_key=session_key,
            )
        with self._timed_phase("build_prompt_surface", detailed=True):
            surface = self._build_prompt_surface(run)
        with self._timed_phase("context_render_snapshot", detailed=True):
            context_render_snapshot = self._record_context_render_snapshot(
                run,
                surface.prompt,
            )
        prompt = self._prompt_with_context_render_report(
            surface.prompt,
            context_render_snapshot,
        )
        prompt = self._prompt_with_context_provider_mirror(
            prompt,
            context_render_snapshot,
        )
        prompt = self._prompt_with_context_workspace_body(
            prompt,
            context_render_snapshot,
        )
        prompt = self._prompt_with_context_artifact_mirror(
            prompt,
            context_render_snapshot,
        )
        resolved_tools = self._resolved_tools_for_prompt(
            surface.resolved_tools,
            prompt,
            context_render_snapshot,
        )
        context = _AdvanceContext(
            session_key=session_key,
            user_message_id=user_message_id,
            prompt=prompt,
            resolved_tools=resolved_tools,
            context_render_snapshot_id=(
                context_render_snapshot.snapshot_id
                if context_render_snapshot is not None
                else None
            ),
        )
        return context

    @staticmethod
    def _validate_invocation_result(invocation: Any) -> None:
        if invocation.result is None:
            if invocation.error is not None:
                raise OrchestrationValidationError(
                    "LLM invocation failed "
                    f"[{invocation.error.code}]: {invocation.error.message}",
                )
            raise OrchestrationValidationError(
                "LLM invocation completed without a result payload.",
            )

    def _advance_outcome_for_tool_calls(
        self,
        run: OrchestrationRun,
        *,
        context: _AdvanceContext,
        invocation: Any,
    ) -> EngineAdvanceOutcome:
        assert invocation.result is not None
        tool_calls = invocation.result.tool_calls
        tool_call_names = tuple(tool_call.name for tool_call in tool_calls)
        with self._timed_phase("tool_assistant_messages", detailed=True):
            assistant_message_ids = list(
                self._assistant_messages_for_tool_calls(
                    context=context,
                    invocation=invocation,
                )
            )
        with self._timed_phase("tool_execution"):
            execution_outcome = self.tool_executor.execute_tool_calls(
                run,
                session_key=context.session_key,
                active_session_id=context.prompt.active_session_id,
                resolved_tools=context.resolved_tools,
                tool_calls=tool_calls,
                append_tool_call_messages=context.prompt.surface_policy.record_tool_call_messages,
                append_tool_result_messages=context.prompt.surface_policy.record_tool_result_messages,
                extra_context_attrs=self._tool_execution_context_attrs(context.prompt),
            )
        assistant_message_ids.extend(execution_outcome.tool_call_message_ids)
        with self._timed_phase("tool_outcome_build", detailed=True):
            return self._advance_outcome_from_tool_execution(
                context=context,
                invocation=invocation,
                assistant_message_ids=assistant_message_ids,
                tool_call_names=tool_call_names,
                execution_outcome=execution_outcome,
            )

    async def _advance_outcome_for_tool_calls_async(
        self,
        run: OrchestrationRun,
        *,
        context: _AdvanceContext,
        invocation: Any,
    ) -> EngineAdvanceOutcome:
        assert invocation.result is not None
        tool_calls = invocation.result.tool_calls
        tool_call_names = tuple(tool_call.name for tool_call in tool_calls)
        with self._timed_phase("tool_assistant_messages", detailed=True):
            assistant_message_ids = list(
                await asyncio.to_thread(
                    self._assistant_messages_for_tool_calls,
                    context=context,
                    invocation=invocation,
                )
            )
        with self._timed_phase("tool_execution"):
            execution_outcome = await self.tool_executor.execute_tool_calls_async(
                run,
                session_key=context.session_key,
                active_session_id=context.prompt.active_session_id,
                resolved_tools=context.resolved_tools,
                tool_calls=tool_calls,
                append_tool_call_messages=context.prompt.surface_policy.record_tool_call_messages,
                append_tool_result_messages=context.prompt.surface_policy.record_tool_result_messages,
                extra_context_attrs=self._tool_execution_context_attrs(context.prompt),
            )
        assistant_message_ids.extend(execution_outcome.tool_call_message_ids)
        with self._timed_phase("tool_outcome_build", detailed=True):
            return self._advance_outcome_from_tool_execution(
                context=context,
                invocation=invocation,
                assistant_message_ids=assistant_message_ids,
                tool_call_names=tool_call_names,
                execution_outcome=execution_outcome,
            )

    def _advance_outcome_from_tool_execution(
        self,
        *,
        context: _AdvanceContext,
        invocation: Any,
        assistant_message_ids: list[str],
        tool_call_names: tuple[str, ...],
        execution_outcome: ToolExecutionBatchOutcome,
    ) -> EngineAdvanceOutcome:
        pending_background_tools = tuple(
            {
                "tool_run_id": tool_run.id,
                "tool_call_id": tool_call.id,
                "tool_name": tool_call.name,
            }
            for tool_call, tool_run in execution_outcome.background_runs
        )
        return self._build_outcome(
            context=context,
            invocation=invocation,
            assistant_message_ids=assistant_message_ids,
            tool_result_message_ids=tuple(
                message_id for message_id, _ in execution_outcome.inline_runs
            ),
            inline_tool_run_ids=tuple(
                tool_run.id for _, tool_run in execution_outcome.inline_runs
            ),
            tool_call_names=tool_call_names,
            pending_tool_run_ids=tuple(
                tool_run.id for _, tool_run in execution_outcome.background_runs
            ),
            pending_background_tools=pending_background_tools,
            pending_approval_request=execution_outcome.pending_approval_request,
            yield_requested=execution_outcome.yield_requested,
            yield_reason=execution_outcome.yield_reason,
            continue_loop=(
                context.prompt.surface_policy.auto_continue_inline_tools
                and execution_outcome.pending_approval_request is None
                and not pending_background_tools
                and not execution_outcome.yield_requested
            ),
        )

    @staticmethod
    def _tool_execution_context_attrs(prompt: PromptSurface) -> dict[str, object]:
        catalog = prompt.skills_catalog
        if catalog is None:
            return {}
        raw_names = catalog.metadata.get("available_skill_names")
        if not isinstance(raw_names, list):
            return {"available_skill_names": []}
        names: list[str] = []
        for name in raw_names:
            if not isinstance(name, str):
                continue
            normalized = name.strip()
            if normalized and normalized not in names:
                names.append(normalized)
        return {"available_skill_names": names}

    def _advance_outcome_for_message_only(
        self,
        *,
        context: _AdvanceContext,
        invocation: Any,
    ) -> EngineAdvanceOutcome:
        assert invocation.result is not None
        if not context.prompt.surface_policy.record_assistant_messages:
            return self._build_outcome(
                context=context,
                invocation=invocation,
            )
        with self._timed_phase("message_record", detailed=True):
            assistant_message_ids = self.session_recorder.append_assistant_response_message(
                session_key=context.session_key,
                active_session_id=context.prompt.active_session_id,
                invocation_id=invocation.id,
                response_text=invocation.result.text,
                structured_output=invocation.result.structured_output,
                finish_reason=invocation.result.finish_reason,
                usage_payload=(
                    invocation.result.usage.to_payload()
                    if invocation.result.usage is not None
                    else None
                ),
            )
        with self._timed_phase("message_outcome_build", detailed=True):
            return self._build_outcome(
                context=context,
                invocation=invocation,
                assistant_message_ids=assistant_message_ids,
            )

    def _assistant_messages_for_tool_calls(
        self,
        *,
        context: _AdvanceContext,
        invocation: Any,
    ) -> tuple[str, ...]:
        assert invocation.result is not None
        if not context.prompt.surface_policy.record_assistant_messages:
            return ()
        if invocation.result.text is None or not invocation.result.text.strip():
            return ()
        return self.session_recorder.append_assistant_response_message(
            session_key=context.session_key,
            active_session_id=context.prompt.active_session_id,
            invocation_id=invocation.id,
            response_text=invocation.result.text,
            structured_output=None,
            finish_reason="tool_calls",
            usage_payload=None,
        )

    def _build_outcome(
        self,
        *,
        context: _AdvanceContext,
        invocation: Any,
        assistant_message_ids: tuple[str, ...] | list[str] = (),
        tool_result_message_ids: tuple[str, ...] | list[str] = (),
        inline_tool_run_ids: tuple[str, ...] = (),
        tool_call_names: tuple[str, ...] = (),
        pending_tool_run_ids: tuple[str, ...] = (),
        pending_background_tools: tuple[dict[str, str], ...] = (),
        pending_approval_request: PendingApprovalRequest | None = None,
        yield_requested: bool = False,
        yield_reason: str | None = None,
        continue_loop: bool = False,
    ) -> EngineAdvanceOutcome:
        assert invocation.result is not None
        return EngineAdvanceOutcome(
            llm_id=context.prompt.llm_id,
            llm_invocation_id=invocation.id,
            response_text=invocation.result.text,
            user_message_id=context.user_message_id,
            assistant_message_ids=tuple(assistant_message_ids),
            tool_result_message_ids=tuple(tool_result_message_ids),
            inline_tool_run_ids=inline_tool_run_ids,
            tool_call_names=tool_call_names,
            pending_tool_run_ids=pending_tool_run_ids,
            pending_background_tools=pending_background_tools,
            pending_approval_request=pending_approval_request,
            prompt_report=context.prompt.report,
            context_render_snapshot_id=context.context_render_snapshot_id,
            yield_requested=yield_requested,
            yield_reason=yield_reason,
            continue_loop=continue_loop,
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
        with self._timed_phase("tool_resolve", detailed=True):
            resolved_tools = self.tool_resolver.resolve(run)
        with self._timed_phase("prompt_assemble", detailed=True):
            prompt = self.prompt_surface.build(
                run,
                resolved_tools=resolved_tools,
            )
        return _PromptSurface(
            prompt=prompt,
            resolved_tools=resolved_tools,
        )

    def _record_context_render_snapshot(
        self,
        run: OrchestrationRun,
        prompt: PromptSurface,
    ) -> ContextRenderSnapshotRecord | None:
        if self.context_snapshot_port is None:
            return None
        try:
            return self.context_snapshot_port.record_run_prompt_snapshot(
                run=run,
                prompt=prompt,
            )
        except Exception as exc:  # pragma: no cover - defensive runtime guard.
            logger.warning(
                "Failed to record context render snapshot for orchestration run %s: %s",
                run.id,
                exc,
            )
            return None

    @staticmethod
    def _prompt_with_context_render_report(
        prompt: PromptSurface,
        context_render_snapshot: ContextRenderSnapshotRecord | None,
    ) -> PromptSurface:
        if context_render_snapshot is None or prompt.report is None:
            return prompt
        return replace(
            prompt,
            report=replace(
                prompt.report,
                context_render=ContextRenderReport(
                    snapshot_id=context_render_snapshot.snapshot_id,
                    estimate=(
                        dict(context_render_snapshot.estimate)
                        if isinstance(context_render_snapshot.estimate, dict)
                        else {}
                    ),
                    included_node_ids=tuple(
                        context_render_snapshot.included_node_ids,
                    ),
                    mirrored_node_ids=tuple(
                        context_render_snapshot.mirrored_node_ids,
                    ),
                ),
            ),
        )

    @staticmethod
    def _prompt_with_context_provider_mirror(
        prompt: PromptSurface,
        context_render_snapshot: ContextRenderSnapshotRecord | None,
    ) -> PromptSurface:
        if context_render_snapshot is None or context_render_snapshot.tool_schemas is None:
            return replace(prompt, tool_schemas=())
        return replace(
            prompt,
            tool_schemas=context_render_snapshot.tool_schemas,
        )

    @staticmethod
    def _prompt_with_context_workspace_body(
        prompt: PromptSurface,
        context_render_snapshot: ContextRenderSnapshotRecord | None,
    ) -> PromptSurface:
        if context_render_snapshot is None:
            return prompt
        prompt_body = (context_render_snapshot.prompt_body or "").strip()
        if not prompt_body:
            return prompt
        context_message = LlmMessage(
            role=LlmMessageRole.SYSTEM,
            content=prompt_body,
            metadata={
                "prompt_block_kind": "context_workspace",
                "context_render_snapshot_id": context_render_snapshot.snapshot_id,
            },
        )
        return replace(
            prompt,
            messages=_insert_after_system_prefix(prompt.messages, context_message),
        )

    @staticmethod
    def _prompt_with_context_artifact_mirror(
        prompt: PromptSurface,
        context_render_snapshot: ContextRenderSnapshotRecord | None,
    ) -> PromptSurface:
        if context_render_snapshot is None:
            return prompt
        artifact_blocks = tuple(context_render_snapshot.artifact_content_blocks)
        if not artifact_blocks:
            return prompt
        artifact_message = LlmMessage(
            role=LlmMessageRole.USER,
            content=[
                text_content_block(
                    "Opened context artifact attachments for this turn:",
                ),
                *artifact_blocks,
            ],
            metadata={
                "prompt_block_kind": "context_artifacts",
                "context_render_snapshot_id": context_render_snapshot.snapshot_id,
            },
        )
        return replace(
            prompt,
            messages=prompt.messages + (artifact_message,),
        )

    @staticmethod
    def _resolved_tools_for_prompt(
        resolved_tools: ResolvedToolSet,
        prompt: PromptSurface,
        context_render_snapshot: ContextRenderSnapshotRecord | None,
    ) -> ResolvedToolSet:
        if context_render_snapshot is None or context_render_snapshot.tool_schemas is None:
            return ResolvedToolSet(
                tools=(),
                blocked_access=resolved_tools.blocked_access,
            )
        visible_tool_names = {
            schema.name for schema in prompt.tool_schemas if schema.name.strip()
        }
        return ResolvedToolSet(
            tools=tuple(
                item
                for item in resolved_tools.tools
                if item.schema.name in visible_tool_names
                or item.tool.id in visible_tool_names
            ),
            blocked_access=resolved_tools.blocked_access,
        )

    def _timed_phase(
        self,
        phase: str,
        *,
        detailed: bool = False,
    ):
        if detailed and not self.detailed_phase_metrics_enabled:
            return nullcontext()
        return self.metrics.timed(
            "orchestration.engine.phase_seconds",
            labels={"phase": phase},
        )


def _insert_after_system_prefix(
    messages: tuple[LlmMessage, ...],
    message: LlmMessage,
) -> tuple[LlmMessage, ...]:
    insert_at = 0
    for existing in messages:
        if existing.role is not LlmMessageRole.SYSTEM:
            break
        insert_at += 1
    return messages[:insert_at] + (message,) + messages[insert_at:]
