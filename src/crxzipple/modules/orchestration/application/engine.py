from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import dataclass, field, replace
from typing import Any

from crxzipple.modules.llm.domain import (
    LlmApiFamily,
    LlmMessage,
    LlmProviderContinuation,
    ToolCallIntent,
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
    PromptReport,
)
from crxzipple.modules.orchestration.application.prompting import PromptMode
from crxzipple.modules.orchestration.application.prompt_input import (
    RunPromptInputCollector,
    RunPromptInput,
)
from crxzipple.modules.orchestration.application.provider_request import (
    LlmRequestEnvelope,
    ProviderPromptRequestBuilder,
    build_llm_request_metadata,
)
from crxzipple.modules.orchestration.application.llm_request_policy import (
    EffectiveLlmRequestPolicy,
    resolve_effective_llm_request_policy,
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

@dataclass(frozen=True, slots=True)
class EngineAdvanceOutcome:
    llm_id: str
    llm_invocation_id: str
    llm_response_item_ids: tuple[str, ...] = field(default_factory=tuple)
    response_text: str | None = None
    user_session_item_id: str | None = None
    session_item_ids: tuple[str, ...] = field(default_factory=tuple)
    assistant_progress_item_ids: tuple[str, ...] = field(default_factory=tuple)
    tool_call_session_item_ids: tuple[str, ...] = field(default_factory=tuple)
    tool_result_session_item_ids: tuple[str, ...] = field(default_factory=tuple)
    completed_inline_tool_run_ids: tuple[str, ...] = field(default_factory=tuple)
    tool_call_names: tuple[str, ...] = field(default_factory=tuple)
    tool_run_links: tuple[dict[str, object], ...] = field(default_factory=tuple)
    pending_tool_run_ids: tuple[str, ...] = field(default_factory=tuple)
    pending_approval_request: PendingApprovalRequest | None = None
    prompt_report: PromptReport | None = None
    context_render_snapshot_id: str | None = None
    llm_request_metadata: dict[str, object] = field(default_factory=dict)
    yield_requested: bool = False
    yield_reason: str | None = None
    continue_loop: bool = False
    continuation_reason: str | None = None
    continuation_end_turn: bool | None = None
    provider_continuation_state: dict[str, object] = field(default_factory=dict)
    loop_diagnostic: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RunPromptInputPreview:
    llm_id: str
    mode: PromptMode
    messages: tuple[LlmMessage, ...]
    tool_schemas: tuple[ToolSchema, ...] = field(default_factory=tuple)
    prompt_report: PromptReport | None = None
    context_render_snapshot_id: str | None = None
    context_render_metadata: dict[str, object] = field(default_factory=dict)
    provider_attachments: dict[str, object] = field(default_factory=dict)
    context_surface: dict[str, object] = field(default_factory=dict)
    tool_surface: dict[str, object] = field(default_factory=dict)
    provider_request_options: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class _ResolvedRunPromptInput:
    prompt: RunPromptInput
    resolved_tools: ResolvedToolSet


@dataclass(frozen=True, slots=True)
class _AdvanceContext:
    session_key: str
    user_session_item_id: str | None
    prompt: RunPromptInput
    resolved_tools: ResolvedToolSet
    request_envelope: LlmRequestEnvelope
    context_render_snapshot_id: str | None = None
    context_render_snapshot_metadata: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class OrchestrationEngine:
    prompt_inputs: RunPromptInputCollector
    session_recorder: OrchestrationSessionRecorder
    llm_port: LlmPort
    tool_resolver: ToolResolver
    tool_execution_port: ToolExecutionPort
    context_snapshot_port: ContextRenderSnapshotPort
    memory_port: MemoryRuntimePort | None = None
    detailed_phase_metrics_enabled: bool = False
    metrics: RuntimeMetricsRegistry = field(
        default_factory=get_runtime_metrics_registry,
    )
    llm_invoker: OrchestrationEngineLlmInvoker = field(init=False)
    tool_executor: OrchestrationEngineToolExecutor = field(init=False)
    provider_request_builder: ProviderPromptRequestBuilder = field(init=False)

    def __post_init__(self) -> None:
        self.prompt_inputs.detailed_phase_metrics_enabled = (
            self.detailed_phase_metrics_enabled
        )
        self.prompt_inputs.metrics = self.metrics
        self.llm_invoker = OrchestrationEngineLlmInvoker(
            llm_port=self.llm_port,
            metrics=self.metrics,
        )
        self.provider_request_builder = ProviderPromptRequestBuilder(
            tool_surface_snapshot_builder=_tool_surface_snapshot_builder(
                self.tool_execution_port,
            ),
        )
        self.tool_executor = OrchestrationEngineToolExecutor(
            session_recorder=self.session_recorder,
            tool_resolver=self.tool_resolver,
            tool_execution_port=self.tool_execution_port,
            detailed_phase_metrics_enabled=self.detailed_phase_metrics_enabled,
            metrics=self.metrics,
        )

    def preview_prompt(self, run: OrchestrationRun) -> RunPromptInputPreview:
        surface = self._build_prompt_input(run)
        context_render_snapshot = self._prompt_preview_context_render_snapshot(
            run,
            surface.prompt,
        )
        base_prompt = self._prompt_with_recorded_transcript_window(
            surface.prompt,
            context_render_snapshot,
        )
        prompt = self.provider_request_builder.prompt_with_context_snapshot(
            base_prompt,
            context_render_snapshot,
        )
        provider_options = self.llm_invoker.request_overrides(
            llm_id=prompt.llm_id,
            tool_schemas=prompt.tool_schemas,
            require_tool_call=prompt.surface_policy.require_tool_call,
        )
        request_options = _llm_request_options_from_run(run, prompt=base_prompt)
        provider_options.update(request_options["provider_options"])
        _merge_reasoning_config_into_provider_options(
            provider_options,
            request_options["reasoning_config"],
        )
        snapshot_metadata = {
            **dict(context_render_snapshot.metadata),
            "llm_request_policy": request_options["policy"].to_payload(),
        }
        request_envelope = self.provider_request_builder.request_envelope(
            prompt=base_prompt,
            context_render_snapshot=context_render_snapshot,
            resolved_tools=surface.resolved_tools,
            snapshot_metadata=snapshot_metadata,
            run_id=run.id,
            agent_id=run.agent_id,
            persist_tool_surface_snapshot=False,
            provider_options=provider_options,
            reasoning_config=request_options["reasoning_config"],
            output_contract=request_options["output_contract"],
        )
        request_metadata = _llm_request_metadata_from_envelope(request_envelope)
        return RunPromptInputPreview(
            llm_id=request_envelope.llm_id,
            mode=prompt.mode,
            messages=request_envelope.messages,
            tool_schemas=request_envelope.tool_schemas,
            prompt_report=prompt.report,
            context_render_snapshot_id=context_render_snapshot.snapshot_id,
            context_render_metadata=dict(context_render_snapshot.metadata),
            provider_attachments=dict(context_render_snapshot.provider_attachments),
            context_surface=request_envelope.context_surface.to_payload(),
            tool_surface=request_envelope.tool_surface.to_payload(),
            provider_request_options={
                "response_format": _response_format_from_output_contract(
                    request_envelope,
                ),
                "output_schema": request_envelope.output_contract.get(
                    "output_schema",
                ),
                "overrides": dict(request_envelope.provider_options),
                "request_metadata": request_metadata,
            },
        )

    def _prompt_preview_context_render_snapshot(
        self,
        run: OrchestrationRun,
        prompt: RunPromptInput,
    ) -> ContextRenderSnapshotRecord:
        recorded = self.context_snapshot_port.get_recorded_run_prompt_snapshot(
            run=run,
            prompt=prompt,
        )
        if recorded is not None:
            return recorded
        return self._preview_context_render_snapshot(run, prompt)

    @staticmethod
    def _prompt_with_recorded_transcript_window(
        prompt: RunPromptInput,
        context_render_snapshot: ContextRenderSnapshotRecord,
    ) -> RunPromptInput:
        raw_count = context_render_snapshot.metadata.get(
            "direct_transcript_message_count",
        )
        if isinstance(raw_count, bool):
            return prompt
        if not isinstance(raw_count, int):
            return prompt
        count = max(0, raw_count)
        if count >= len(prompt.messages):
            return prompt
        return replace(prompt, messages=prompt.messages[:count])

    def advance_once(
        self,
        run: OrchestrationRun,
        *,
        on_llm_stream_update: Callable[[str, str, str | None], None] | None = None,
    ) -> EngineAdvanceOutcome:
        with self._timed_phase("build_context"):
            context = self._build_advance_context(run)
        with self._timed_phase("llm_invoke"):
            provider_continuation = _provider_continuation_for_prompt(run, context.prompt)
            invocation = self.llm_invoker.invoke(
                llm_id=context.request_envelope.llm_id,
                messages=context.request_envelope.messages,
                tool_schemas=context.request_envelope.tool_schemas,
                response_format=_response_format_from_output_contract(
                    context.request_envelope,
                ),
                request_overrides=context.request_envelope.provider_options,
                continuation=provider_continuation,
                require_tool_call=context.prompt.surface_policy.require_tool_call,
                request_metadata=_llm_request_metadata_from_envelope(
                    context.request_envelope,
                ),
                on_llm_stream_update=on_llm_stream_update,
            )
        self._validate_invocation_result(invocation)
        session_item_ids = self._record_llm_response_items(
            context=context,
            invocation=invocation,
        )

        assert invocation.result is not None
        tool_calls = _local_tool_calls_from_invocation(invocation)
        if tool_calls:
            return self._advance_outcome_for_tool_calls(
                run,
                context=context,
                invocation=invocation,
                session_item_ids=session_item_ids,
                tool_calls=tool_calls,
            )
        return self._advance_outcome_for_message_only(
            context=context,
            invocation=invocation,
            session_item_ids=session_item_ids,
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
            provider_continuation = _provider_continuation_for_prompt(run, context.prompt)
            invocation = await self.llm_invoker.invoke_async(
                llm_id=context.request_envelope.llm_id,
                messages=context.request_envelope.messages,
                tool_schemas=context.request_envelope.tool_schemas,
                response_format=_response_format_from_output_contract(
                    context.request_envelope,
                ),
                request_overrides=context.request_envelope.provider_options,
                continuation=provider_continuation,
                require_tool_call=context.prompt.surface_policy.require_tool_call,
                request_metadata=_llm_request_metadata_from_envelope(
                    context.request_envelope,
                ),
                on_llm_stream_update=on_llm_stream_update,
            )
        self._validate_invocation_result(invocation)
        session_item_ids = await asyncio.to_thread(
            self._record_llm_response_items,
            context=context,
            invocation=invocation,
        )

        assert invocation.result is not None
        tool_calls = _local_tool_calls_from_invocation(invocation)
        if tool_calls:
            return await self._advance_outcome_for_tool_calls_async(
                run,
                context=context,
                invocation=invocation,
                session_item_ids=session_item_ids,
                tool_calls=tool_calls,
            )
        return await asyncio.to_thread(
            self._advance_outcome_for_message_only,
            context=context,
            invocation=invocation,
            session_item_ids=session_item_ids,
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
            inbound_record = self.session_recorder.ensure_inbound_message(
                run,
                session_key=session_key,
            )
        with self._timed_phase("build_prompt_input", detailed=True):
            surface = self._build_prompt_input(run)
        with self._timed_phase("context_render_snapshot", detailed=True):
            context_render_snapshot = self._record_context_render_snapshot(
                run,
                surface.prompt,
            )
        prompt = self.provider_request_builder.prompt_with_context_snapshot(
            surface.prompt,
            context_render_snapshot,
        )
        resolved_tools = self.provider_request_builder.resolved_tools_for_prompt(
            surface.resolved_tools,
            prompt,
            context_render_snapshot,
        )
        provider_options = self.llm_invoker.request_overrides(
            llm_id=prompt.llm_id,
            tool_schemas=prompt.tool_schemas,
            require_tool_call=prompt.surface_policy.require_tool_call,
        )
        request_options = _llm_request_options_from_run(run, prompt=surface.prompt)
        provider_options.update(request_options["provider_options"])
        snapshot_metadata = (
            dict(context_render_snapshot.metadata)
            if context_render_snapshot is not None
            else {}
        )
        snapshot_metadata["llm_request_policy"] = request_options["policy"].to_payload()
        _merge_reasoning_config_into_provider_options(
            provider_options,
            request_options["reasoning_config"],
        )
        provider_continuation = _provider_continuation_for_prompt(run, prompt)
        request_envelope = self.provider_request_builder.request_envelope(
            prompt=surface.prompt,
            context_render_snapshot=context_render_snapshot,
            resolved_tools=surface.resolved_tools,
            snapshot_metadata=snapshot_metadata,
            run_id=run.id,
            agent_id=run.agent_id,
            provider_options=provider_options,
            reasoning_config=request_options["reasoning_config"],
            output_contract=request_options["output_contract"],
            include_context_messages=provider_continuation is None,
        )
        context = _AdvanceContext(
            session_key=session_key,
            user_session_item_id=inbound_record.user_session_item_id,
            prompt=prompt,
            resolved_tools=resolved_tools,
            request_envelope=request_envelope,
            context_render_snapshot_id=(
                context_render_snapshot.snapshot_id
                if context_render_snapshot is not None
                else None
            ),
            context_render_snapshot_metadata=(
                dict(context_render_snapshot.metadata)
                if context_render_snapshot is not None
                else {}
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
        session_item_ids: tuple[str, ...],
        tool_calls: tuple[ToolCallIntent, ...],
    ) -> EngineAdvanceOutcome:
        assert invocation.result is not None
        tool_call_names = tuple(tool_call.name for tool_call in tool_calls)
        with self._timed_phase("tool_assistant_items", detailed=True):
            assistant_progress_item_ids = list(
                self._assistant_items_for_tool_calls(
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
                append_tool_call_session_items=not session_item_ids,
                append_tool_result_messages=context.prompt.surface_policy.record_tool_result_messages,
                invocation_id=invocation.id,
                extra_context_attrs=self._tool_execution_context_attrs(context),
            )
        outcome_session_item_ids = (
            *session_item_ids,
            *assistant_progress_item_ids,
            *execution_outcome.tool_call_session_item_ids,
            *execution_outcome.tool_result_session_item_ids,
        )
        with self._timed_phase("tool_outcome_build", detailed=True):
            return self._advance_outcome_from_tool_execution(
                context=context,
                invocation=invocation,
                session_item_ids=outcome_session_item_ids,
                assistant_progress_item_ids=tuple(assistant_progress_item_ids),
                tool_call_session_item_ids=execution_outcome.tool_call_session_item_ids,
                tool_result_session_item_ids=execution_outcome.tool_result_session_item_ids,
                tool_call_names=tool_call_names,
                execution_outcome=execution_outcome,
            )

    async def _advance_outcome_for_tool_calls_async(
        self,
        run: OrchestrationRun,
        *,
        context: _AdvanceContext,
        invocation: Any,
        session_item_ids: tuple[str, ...],
        tool_calls: tuple[ToolCallIntent, ...],
    ) -> EngineAdvanceOutcome:
        assert invocation.result is not None
        tool_call_names = tuple(tool_call.name for tool_call in tool_calls)
        with self._timed_phase("tool_assistant_items", detailed=True):
            assistant_progress_item_ids = list(
                await asyncio.to_thread(
                    self._assistant_items_for_tool_calls,
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
                append_tool_call_session_items=not session_item_ids,
                append_tool_result_messages=context.prompt.surface_policy.record_tool_result_messages,
                invocation_id=invocation.id,
                extra_context_attrs=self._tool_execution_context_attrs(context),
            )
        outcome_session_item_ids = (
            *session_item_ids,
            *assistant_progress_item_ids,
            *execution_outcome.tool_call_session_item_ids,
            *execution_outcome.tool_result_session_item_ids,
        )
        with self._timed_phase("tool_outcome_build", detailed=True):
            return self._advance_outcome_from_tool_execution(
                context=context,
                invocation=invocation,
                session_item_ids=outcome_session_item_ids,
                assistant_progress_item_ids=tuple(assistant_progress_item_ids),
                tool_call_session_item_ids=execution_outcome.tool_call_session_item_ids,
                tool_result_session_item_ids=execution_outcome.tool_result_session_item_ids,
                tool_call_names=tool_call_names,
                execution_outcome=execution_outcome,
            )

    def _advance_outcome_from_tool_execution(
        self,
        *,
        context: _AdvanceContext,
        invocation: Any,
        session_item_ids: tuple[str, ...],
        assistant_progress_item_ids: tuple[str, ...],
        tool_call_session_item_ids: tuple[str, ...],
        tool_result_session_item_ids: tuple[str, ...],
        tool_call_names: tuple[str, ...],
        execution_outcome: ToolExecutionBatchOutcome,
    ) -> EngineAdvanceOutcome:
        return self._build_outcome(
            context=context,
            invocation=invocation,
            session_item_ids=session_item_ids,
            assistant_progress_item_ids=assistant_progress_item_ids,
            tool_call_session_item_ids=tool_call_session_item_ids,
            tool_result_session_item_ids=tool_result_session_item_ids,
            completed_inline_tool_run_ids=tuple(
                tool_run.id for tool_run in execution_outcome.inline_runs
            ),
            tool_call_names=tool_call_names,
            tool_run_links=tuple(
                dict(link.to_payload()) for link in execution_outcome.tool_run_links
            ),
            pending_tool_run_ids=tuple(
                tool_run.id for _, tool_run in execution_outcome.background_runs
            ),
            pending_approval_request=execution_outcome.pending_approval_request,
            yield_requested=execution_outcome.yield_requested,
            yield_reason=execution_outcome.yield_reason,
            continue_loop=(
                context.prompt.surface_policy.auto_continue_inline_tools
                and execution_outcome.pending_approval_request is None
                and not execution_outcome.background_runs
                and not execution_outcome.yield_requested
            ),
        )

    @staticmethod
    def _tool_execution_context_attrs(context: _AdvanceContext) -> dict[str, object]:
        prompt = context.prompt
        attrs: dict[str, object] = {}
        for key in (
            "tool_surface_id",
            "tool_surface_snapshot_id",
            "context_render_snapshot_id",
        ):
            value = context.request_envelope.metadata.get(key)
            if isinstance(value, str) and value.strip():
                attrs[key] = value.strip()
        tool_surface_functions = [
            {
                "tool_id": function.tool_id,
                "name": function.name,
                "source_id": function.source_id,
                "group_key": function.group_key,
            }
            for function in context.request_envelope.tool_surface.functions
        ]
        if tool_surface_functions:
            attrs["tool_surface_functions"] = tool_surface_functions
        catalog = prompt.skills_catalog
        if catalog is None:
            return attrs
        raw_names = catalog.metadata.get("available_skill_names")
        if not isinstance(raw_names, list):
            return {**attrs, "available_skill_names": []}
        names: list[str] = []
        for name in raw_names:
            if not isinstance(name, str):
                continue
            normalized = name.strip()
            if normalized and normalized not in names:
                names.append(normalized)
        return {**attrs, "available_skill_names": names}

    def _advance_outcome_for_message_only(
        self,
        *,
        context: _AdvanceContext,
        invocation: Any,
        session_item_ids: tuple[str, ...],
    ) -> EngineAdvanceOutcome:
        assert invocation.result is not None
        if not context.prompt.surface_policy.record_assistant_messages:
            return self._build_outcome(
                context=context,
                invocation=invocation,
                session_item_ids=session_item_ids,
                continue_loop=_continuation_needs_follow_up(invocation),
            )
        if session_item_ids:
            return self._build_outcome(
                context=context,
                invocation=invocation,
                session_item_ids=session_item_ids,
                continue_loop=_continuation_needs_follow_up(invocation),
            )
        with self._timed_phase("assistant_item_record", detailed=True):
            assistant_session_item_ids = self.session_recorder.append_assistant_response_item(
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
                session_item_ids=(
                    *session_item_ids,
                    *assistant_session_item_ids,
                ),
                continue_loop=_continuation_needs_follow_up(invocation),
            )

    def _assistant_items_for_tool_calls(
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
        session_item_ids: tuple[str, ...] = (),
        assistant_progress_item_ids: tuple[str, ...] | list[str] = (),
        tool_call_session_item_ids: tuple[str, ...] | list[str] = (),
        tool_result_session_item_ids: tuple[str, ...] | list[str] = (),
        completed_inline_tool_run_ids: tuple[str, ...] = (),
        tool_call_names: tuple[str, ...] = (),
        tool_run_links: tuple[dict[str, object], ...] = (),
        pending_tool_run_ids: tuple[str, ...] = (),
        pending_approval_request: PendingApprovalRequest | None = None,
        yield_requested: bool = False,
        yield_reason: str | None = None,
        continue_loop: bool = False,
    ) -> EngineAdvanceOutcome:
        assert invocation.result is not None
        return EngineAdvanceOutcome(
            llm_id=context.prompt.llm_id,
            llm_invocation_id=invocation.id,
            llm_response_item_ids=_llm_response_item_ids(invocation),
            response_text=invocation.result.text,
            user_session_item_id=context.user_session_item_id,
            session_item_ids=tuple(session_item_ids),
            assistant_progress_item_ids=tuple(assistant_progress_item_ids),
            tool_call_session_item_ids=tuple(tool_call_session_item_ids),
            tool_result_session_item_ids=tuple(tool_result_session_item_ids),
            completed_inline_tool_run_ids=completed_inline_tool_run_ids,
            tool_call_names=tool_call_names,
            tool_run_links=tool_run_links,
            pending_tool_run_ids=pending_tool_run_ids,
            pending_approval_request=pending_approval_request,
            prompt_report=context.prompt.report,
            context_render_snapshot_id=context.context_render_snapshot_id,
            llm_request_metadata=_llm_request_metadata(context),
            yield_requested=yield_requested,
            yield_reason=yield_reason,
            continue_loop=continue_loop,
            continuation_reason=_continuation_reason(invocation),
            continuation_end_turn=_continuation_end_turn(invocation),
            provider_continuation_state=_provider_continuation_state(invocation),
            loop_diagnostic=_terminal_loop_diagnostic(invocation),
        )

    def _record_llm_response_items(
        self,
        *,
        context: _AdvanceContext,
        invocation: Any,
    ) -> tuple[str, ...]:
        response_items = getattr(invocation, "response_items", None)
        if not isinstance(response_items, (list, tuple)) or not response_items:
            return ()
        return self.session_recorder.append_llm_response_items(
            session_key=context.session_key,
            active_session_id=context.prompt.active_session_id,
            invocation_id=invocation.id,
            response_items=tuple(response_items),
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

    def _build_prompt_input(
        self,
        run: OrchestrationRun,
    ) -> _ResolvedRunPromptInput:
        with self._timed_phase("tool_resolve", detailed=True):
            resolved_tools = self.tool_resolver.resolve(run)
        with self._timed_phase("prompt_input_collect", detailed=True):
            prompt = self.prompt_inputs.build(
                run,
                resolved_tools=resolved_tools,
            )
        return _ResolvedRunPromptInput(
            prompt=prompt,
            resolved_tools=resolved_tools,
        )

    def _record_context_render_snapshot(
        self,
        run: OrchestrationRun,
        prompt: RunPromptInput,
    ) -> ContextRenderSnapshotRecord:
        try:
            snapshot = self.context_snapshot_port.record_run_prompt_snapshot(
                run=run,
                prompt=prompt,
            )
        except Exception as exc:  # pragma: no cover - defensive runtime guard.
            raise OrchestrationValidationError(
                "Context Workspace prompt render failed for orchestration run "
                f"'{run.id}': {exc}",
            ) from exc
        if snapshot is None:
            raise OrchestrationValidationError(
                "Context Workspace prompt render did not return a snapshot for "
                f"orchestration run '{run.id}'.",
            )
        return snapshot

    def _preview_context_render_snapshot(
        self,
        run: OrchestrationRun,
        prompt: RunPromptInput,
    ) -> ContextRenderSnapshotRecord:
        try:
            snapshot = self.context_snapshot_port.preview_run_prompt_snapshot(
                run=run,
                prompt=prompt,
            )
        except Exception as exc:  # pragma: no cover - defensive runtime guard.
            raise OrchestrationValidationError(
                "Context Workspace prompt preview failed for orchestration run "
                f"'{run.id}': {exc}",
            ) from exc
        if snapshot is None:
            raise OrchestrationValidationError(
                "Context Workspace prompt preview did not return a render record for "
                f"orchestration run '{run.id}'.",
            )
        return snapshot

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


def _llm_request_metadata(context: _AdvanceContext) -> dict[str, object]:
    return _llm_request_metadata_from_envelope(context.request_envelope)


def _llm_request_metadata_from_envelope(
    request_envelope: LlmRequestEnvelope,
) -> dict[str, object]:
    metadata = dict(request_envelope.metadata)
    if request_envelope.context_surface.snapshot_id:
        metadata["context_surface"] = request_envelope.context_surface.to_payload()
    if request_envelope.tool_surface.id:
        metadata["tool_surface"] = request_envelope.tool_surface.to_payload()
    if request_envelope.reasoning_config:
        metadata["reasoning_config"] = dict(request_envelope.reasoning_config)
    if request_envelope.output_contract:
        metadata["output_contract"] = dict(request_envelope.output_contract)
    if request_envelope.provider_options:
        metadata["provider_options"] = dict(request_envelope.provider_options)
    if request_envelope.blocked_tool_access:
        metadata["blocked_tool_access"] = [
            dict(item) for item in request_envelope.blocked_tool_access
        ]
    return metadata


def _response_format_from_output_contract(
    request_envelope: LlmRequestEnvelope,
) -> dict[str, object] | None:
    response_format = request_envelope.output_contract.get("response_format")
    return dict(response_format) if isinstance(response_format, dict) else None


def _llm_request_options_from_run_metadata(
    run: OrchestrationRun,
) -> dict[str, dict[str, object]]:
    raw_options = run.metadata.get("llm_request_options")
    if not isinstance(raw_options, dict):
        return {
            "provider_options": {},
            "reasoning_config": {},
            "output_contract": {},
        }
    provider_options = _dict_option(raw_options.get("provider_options"))
    reasoning_config = _dict_option(raw_options.get("reasoning_config"))
    output_contract = _dict_option(raw_options.get("output_contract"))
    response_format = _dict_option(raw_options.get("response_format"))
    if response_format:
        output_contract["response_format"] = response_format
    output_schema = _dict_option(raw_options.get("output_schema"))
    if output_schema:
        output_contract["output_schema"] = output_schema
    return {
        "provider_options": provider_options,
        "reasoning_config": reasoning_config,
        "output_contract": output_contract,
    }


def _llm_request_options_from_run(
    run: OrchestrationRun,
    *,
    prompt: RunPromptInput,
) -> dict[str, object]:
    policy = resolve_effective_llm_request_policy(
        run,
        llm_capabilities=prompt.llm_capabilities,
        llm_api_family=prompt.llm_api_family,
        runtime_defaults=prompt.runtime_llm_defaults,
        llm_defaults=prompt.llm_defaults,
        agent_llm_policy=prompt.llm_policy,
    )
    return _llm_request_options_from_policy(policy)


def _llm_request_options_from_policy(
    policy: EffectiveLlmRequestPolicy,
) -> dict[str, object]:
    return {
        "provider_options": dict(policy.provider_options),
        "reasoning_config": dict(policy.reasoning_config),
        "output_contract": dict(policy.output_contract),
        "policy": policy,
    }


def _merge_reasoning_config_into_provider_options(
    provider_options: dict[str, object],
    reasoning_config: object,
) -> None:
    if not isinstance(reasoning_config, dict) or not reasoning_config:
        return
    existing = provider_options.get("reasoning")
    reasoning = dict(existing) if isinstance(existing, dict) else {}
    reasoning.update(reasoning_config)
    provider_options["reasoning"] = reasoning


def _dict_option(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, dict) else {}


def _tool_surface_snapshot_builder(tool_execution_port: object) -> Callable[..., object] | None:
    builder = getattr(tool_execution_port, "build_tool_surface", None)
    return builder if callable(builder) else None


def _legacy_llm_request_metadata(context: _AdvanceContext) -> dict[str, object]:
    return build_llm_request_metadata(
        prompt=context.prompt,
        context_render_snapshot_id=context.context_render_snapshot_id,
        snapshot_metadata=context.context_render_snapshot_metadata,
    )


def _llm_response_item_ids(invocation: Any) -> tuple[str, ...]:
    response_items = getattr(invocation, "response_items", None)
    if not isinstance(response_items, (list, tuple)) or not response_items:
        return ()
    item_ids: list[str] = []
    for item in response_items:
        item_id = getattr(item, "id", None)
        if isinstance(item_id, str) and item_id.strip():
            normalized = item_id.strip()
            if normalized not in item_ids:
                item_ids.append(normalized)
    return tuple(item_ids)


def _local_tool_calls_from_invocation(invocation: Any) -> tuple[ToolCallIntent, ...]:
    response_items = getattr(invocation, "response_items", None)
    if isinstance(response_items, (list, tuple)) and response_items:
        tool_calls: list[ToolCallIntent] = []
        for item in response_items:
            if _enum_value(getattr(item, "kind", None)) != "tool_call":
                continue
            content = getattr(item, "content_payload", None)
            if not isinstance(content, dict):
                content = {}
            tool_name = str(
                content.get("tool_name") or getattr(item, "tool_name", None) or "",
            ).strip()
            if not tool_name:
                continue
            call_id = str(
                content.get("call_id")
                or getattr(item, "call_id", None)
                or getattr(item, "provider_item_id", None)
                or getattr(item, "id", "")
                or "tool_call",
            )
            arguments = content.get("arguments")
            tool_calls.append(
                ToolCallIntent(
                    id=call_id,
                    name=tool_name,
                    arguments=dict(arguments) if isinstance(arguments, dict) else {},
                ),
            )
        return tuple(tool_calls)
    return ()


def _continuation_needs_follow_up(invocation: Any) -> bool:
    continuation = getattr(invocation, "continuation", None)
    return bool(getattr(continuation, "needs_follow_up", False))


def _continuation_reason(invocation: Any) -> str | None:
    continuation = getattr(invocation, "continuation", None)
    reason = getattr(continuation, "reason", None)
    text = _enum_value(reason)
    return text if text != "-" else None


def _continuation_end_turn(invocation: Any) -> bool | None:
    continuation = getattr(invocation, "continuation", None)
    value = getattr(continuation, "end_turn", None)
    return value if isinstance(value, bool) else None


def _provider_continuation_from_run(
    run: OrchestrationRun,
) -> LlmProviderContinuation | None:
    raw_state = run.metadata.get("provider_continuation_state")
    if not isinstance(raw_state, dict):
        return None
    if raw_state.get("mode") != "provider_native":
        return None
    previous_response_id = _optional_text(raw_state.get("previous_response_id"))
    if previous_response_id is None:
        return None
    return LlmProviderContinuation(
        mode="provider_native",
        previous_response_id=previous_response_id,
        previous_invocation_id=_optional_text(raw_state.get("previous_invocation_id")),
        provider_family=_optional_text(raw_state.get("provider_family")),
    )


def _provider_continuation_for_prompt(
    run: OrchestrationRun,
    prompt: RunPromptInput,
) -> LlmProviderContinuation | None:
    if not _llm_api_family_supports_provider_continuation(prompt.llm_api_family):
        return None
    return _provider_continuation_from_run(run)


def _llm_api_family_supports_provider_continuation(api_family: str | None) -> bool:
    if api_family is None:
        return False
    return api_family.strip() in {
        LlmApiFamily.OPENAI_RESPONSES.value,
        LlmApiFamily.OPENAI_CODEX_RESPONSES.value,
    }


def _provider_continuation_state(invocation: Any) -> dict[str, object]:
    previous_response_id = _optional_text(getattr(invocation, "provider_request_id", None))
    if previous_response_id is None:
        return {}
    preview = getattr(invocation, "provider_request_payload_preview", None)
    if not isinstance(preview, dict):
        return {}
    api_family = _optional_text(preview.get("api_family"))
    if api_family not in {"openai_responses", "openai_codex_responses"}:
        return {}
    return {
        "mode": "provider_native",
        "provider_family": api_family,
        "previous_response_id": previous_response_id,
        "previous_invocation_id": getattr(invocation, "id", ""),
        "last_request_had_previous_response_id": bool(
            preview.get("has_previous_response_id"),
        ),
    }


def _terminal_loop_diagnostic(invocation: Any) -> dict[str, object]:
    if _continuation_needs_follow_up(invocation):
        return {}
    response_items = getattr(invocation, "response_items", None)
    if not isinstance(response_items, (list, tuple)) or not response_items:
        return {}
    item_kinds = tuple(_enum_value(getattr(item, "kind", None)) for item in response_items)
    item_phases = tuple(_enum_value(getattr(item, "phase", None)) for item in response_items)
    if "tool_call" in item_kinds or "provider_external_item" in item_kinds:
        return {}
    has_final_answer = any(
        kind == "assistant_message" and phase == "final_answer"
        for kind, phase in zip(item_kinds, item_phases, strict=False)
    )
    if has_final_answer:
        return {}
    commentary_or_reasoning_only = all(
        kind == "reasoning"
        or (kind == "assistant_message" and phase == "commentary")
        for kind, phase in zip(item_kinds, item_phases, strict=False)
    )
    if not commentary_or_reasoning_only:
        return {}
    return {
        "code": "llm_incomplete_terminal_response",
        "reason": "commentary_or_reasoning_without_final_answer_or_follow_up",
        "item_kinds": list(item_kinds),
        "item_phases": list(item_phases),
    }


def _enum_value(value: Any) -> str:
    raw_value = getattr(value, "value", value)
    text = str(raw_value or "").strip()
    return text or "-"


def _optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None
