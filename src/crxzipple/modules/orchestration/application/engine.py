from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import dataclass, field, replace
from typing import Any

from crxzipple.modules.llm.application import provider_continuation_from_state
from crxzipple.modules.llm.domain import (
    ToolCallIntent,
)
from crxzipple.modules.llm.application.runtime_request import (
    runtime_request_context_from_metadata,
)
from crxzipple.modules.memory.application import MemoryRuntimePort
from crxzipple.modules.orchestration.application.ports import (
    RequestRenderSnapshotRecord,
    RequestRenderSnapshotPort,
    LlmPort,
    ToolExecutionPort,
)
from crxzipple.modules.orchestration.application.runtime_llm_request_draft import (
    RuntimeLlmRequestDraftCollector,
    RuntimeLlmRequestDraft,
)
from crxzipple.modules.llm.application.runtime_request_factory import (
    RuntimeLlmRequestBuilder,
)
from crxzipple.modules.orchestration.application.engine_session_recorder import (
    OrchestrationSessionRecorder,
    RuntimeResponseRecord,
)
from crxzipple.modules.orchestration.application.engine_llm_invoker import (
    OrchestrationEngineLlmInvoker,
)
from crxzipple.modules.orchestration.application.engine_tool_executor import (
    OrchestrationEngineToolExecutor,
    ToolExecutionBatchOutcome,
)
from crxzipple.modules.orchestration.application.engine_models import (
    AdvanceContext,
    EngineAdvanceOutcome,
    ResolvedRuntimeLlmRequestDraft,
    RuntimeLlmRequestPreview,
    snapshot_metadata_for_request,
)
from crxzipple.modules.orchestration.application.engine_outcomes import (
    build_engine_advance_outcome,
    build_tool_execution_advance_outcome,
    tool_call_intent_for_background_run,
    tool_execution_context_attrs,
)
from crxzipple.modules.orchestration.application.engine_runtime_helpers import (
    continuation_needs_follow_up,
    llm_request_options_from_run,
    provider_continuation_state_from_run,
    response_format_from_output_contract,
    tool_surface_snapshot_builder,
    unique_ids,
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

@dataclass(slots=True)
class OrchestrationEngine:
    runtime_request_drafts: RuntimeLlmRequestDraftCollector
    session_recorder: OrchestrationSessionRecorder
    llm_port: LlmPort
    tool_resolver: ToolResolver
    tool_execution_port: ToolExecutionPort
    request_render_snapshot_port: RequestRenderSnapshotPort
    memory_port: MemoryRuntimePort | None = None
    detailed_phase_metrics_enabled: bool = False
    metrics: RuntimeMetricsRegistry = field(
        default_factory=get_runtime_metrics_registry,
    )
    llm_invoker: OrchestrationEngineLlmInvoker = field(init=False)
    tool_executor: OrchestrationEngineToolExecutor = field(init=False)
    runtime_llm_request_builder: RuntimeLlmRequestBuilder = field(init=False)

    def __post_init__(self) -> None:
        self.runtime_request_drafts.detailed_phase_metrics_enabled = (
            self.detailed_phase_metrics_enabled
        )
        self.runtime_request_drafts.metrics = self.metrics
        self.llm_invoker = OrchestrationEngineLlmInvoker(
            llm_port=self.llm_port,
            metrics=self.metrics,
        )
        self.runtime_llm_request_builder = RuntimeLlmRequestBuilder(
            tool_surface_snapshot_builder=tool_surface_snapshot_builder(
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

    def preview_runtime_llm_request(self, run: OrchestrationRun) -> RuntimeLlmRequestPreview:
        surface = self._build_runtime_request_preview_draft(run)
        request_render_snapshot = self._runtime_request_preview_render_snapshot(
            run,
            surface.draft,
        )
        base_draft = self._draft_with_recorded_transcript_window(
            surface.draft,
            request_render_snapshot,
        )
        report_draft = self.runtime_llm_request_builder.draft_with_request_render_snapshot(
            base_draft,
            request_render_snapshot,
        )
        resolved_tools = self.runtime_llm_request_builder.resolved_tools_for_draft(
            surface.resolved_tools,
            base_draft,
            request_render_snapshot,
        )
        request_options = llm_request_options_from_run(run, draft=base_draft)
        provider_options = dict(request_options["provider_options"])
        snapshot_metadata = snapshot_metadata_for_request(
            request_render_snapshot,
            policy_payload=request_options["policy"].to_payload(),
        )
        request_envelope = self.runtime_llm_request_builder.request_envelope(
            draft=base_draft,
            request_render_snapshot=request_render_snapshot,
            resolved_tools=resolved_tools,
            snapshot_metadata=snapshot_metadata,
            run_id=run.id,
            agent_id=run.agent_id,
            persist_tool_surface_snapshot=False,
            provider_options=provider_options,
            reasoning_config=request_options["reasoning_config"],
            output_contract=request_options["output_contract"],
        )
        request_metadata = request_envelope.request_metadata()
        return RuntimeLlmRequestPreview(
            llm_id=request_envelope.llm_id,
            mode=base_draft.mode,
            messages=request_envelope.messages,
            input_items=tuple(
                item.to_payload() for item in request_envelope.transcript.items
            ),
            tool_schemas=request_envelope.tool_schemas,
            runtime_request_report=report_draft.report,
            request_render_snapshot_id=request_render_snapshot.snapshot_id,
            request_render_snapshot_metadata=dict(request_render_snapshot.metadata),
            request_render_snapshot=request_envelope.request_render_snapshot.to_payload(),
            tool_surface=request_envelope.tool_surface.to_payload(),
            runtime_context=runtime_request_context_from_metadata(request_metadata),
            provider_request_options={
                "response_format": response_format_from_output_contract(
                    request_envelope,
                ),
                "output_schema": request_envelope.output_contract.get(
                    "output_schema",
                ),
                "overrides": dict(request_envelope.provider_options),
                "request_metadata": request_metadata,
            },
        )

    def _runtime_request_preview_render_snapshot(
        self,
        run: OrchestrationRun,
        draft: RuntimeLlmRequestDraft,
    ) -> RequestRenderSnapshotRecord:
        recorded = self.request_render_snapshot_port.get_recorded_run_request_render_snapshot(
            run=run,
            draft=draft,
        )
        if recorded is not None:
            return recorded
        return self._preview_request_render_snapshot(run, draft)

    def advance_once(
        self,
        run: OrchestrationRun,
        *,
        on_llm_stream_update: Callable[[str, str, str | None], None] | None = None,
    ) -> EngineAdvanceOutcome:
        with self._timed_phase("build_context"):
            context = self._build_advance_context(run)
        with self._timed_phase("llm_invoke"):
            provider_continuation = self.llm_invoker.provider_continuation(
                request_envelope=context.request_envelope,
                continuation=provider_continuation_from_state(
                    provider_continuation_state_from_run(run),
                ),
            )
            invocation = self.llm_invoker.invoke(
                request_envelope=context.request_envelope,
                response_format=response_format_from_output_contract(
                    context.request_envelope,
                ),
                continuation=provider_continuation,
                on_llm_stream_update=on_llm_stream_update,
            )
        self._validate_invocation_result(invocation)
        response_record = self._record_llm_response_items(
            context=context,
            invocation=invocation,
        )

        assert invocation.result is not None
        tool_calls = response_record.tool_calls
        if tool_calls:
            return self._advance_outcome_for_tool_calls(
                run,
                context=context,
                invocation=invocation,
                session_item_ids=response_record.item_ids,
                assistant_progress_item_ids=response_record.assistant_progress_item_ids,
                tool_call_session_item_ids_by_call_id=(
                    response_record.tool_call_session_item_ids_by_call_id or {}
                ),
                tool_calls=tool_calls,
            )
        return self._advance_outcome_for_message_only(
            context=context,
            invocation=invocation,
            session_item_ids=response_record.item_ids,
            assistant_progress_item_ids=response_record.assistant_progress_item_ids,
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
            provider_continuation = self.llm_invoker.provider_continuation(
                request_envelope=context.request_envelope,
                continuation=provider_continuation_from_state(
                    provider_continuation_state_from_run(run),
                ),
            )
            invocation = await self.llm_invoker.invoke_async(
                request_envelope=context.request_envelope,
                response_format=response_format_from_output_contract(
                    context.request_envelope,
                ),
                continuation=provider_continuation,
                on_llm_stream_update=on_llm_stream_update,
            )
        self._validate_invocation_result(invocation)
        response_record = await asyncio.to_thread(
            self._record_llm_response_items,
            context=context,
            invocation=invocation,
        )

        assert invocation.result is not None
        tool_calls = response_record.tool_calls
        if tool_calls:
            return await self._advance_outcome_for_tool_calls_async(
                run,
                context=context,
                invocation=invocation,
                session_item_ids=response_record.item_ids,
                assistant_progress_item_ids=response_record.assistant_progress_item_ids,
                tool_call_session_item_ids_by_call_id=(
                    response_record.tool_call_session_item_ids_by_call_id or {}
                ),
                tool_calls=tool_calls,
            )
        return await asyncio.to_thread(
            self._advance_outcome_for_message_only,
            context=context,
            invocation=invocation,
            session_item_ids=response_record.item_ids,
            assistant_progress_item_ids=response_record.assistant_progress_item_ids,
        )

    def _build_advance_context(self, run: OrchestrationRun) -> AdvanceContext:
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
        with self._timed_phase("build_runtime_request_draft", detailed=True):
            surface = self._build_runtime_request_draft(run)
        with self._timed_phase("request_render_snapshot", detailed=True):
            request_render_snapshot = self._record_request_render_snapshot(
                run,
                surface.draft,
            )
        base_draft = surface.draft
        report_draft = self.runtime_llm_request_builder.draft_with_request_render_snapshot(
            base_draft,
            request_render_snapshot,
        )
        resolved_tools = self._resolve_tools_for_runtime_draft(
            run,
            base_resolved_tools=surface.resolved_tools,
            draft=base_draft,
            request_render_snapshot=request_render_snapshot,
        )
        request_options = llm_request_options_from_run(run, draft=base_draft)
        provider_options = dict(request_options["provider_options"])
        snapshot_metadata = snapshot_metadata_for_request(
            request_render_snapshot,
            policy_payload=request_options["policy"].to_payload(),
        )
        request_envelope = self.runtime_llm_request_builder.request_envelope(
            draft=base_draft,
            request_render_snapshot=request_render_snapshot,
            resolved_tools=resolved_tools,
            snapshot_metadata=snapshot_metadata,
            run_id=run.id,
            agent_id=run.agent_id,
            provider_options=provider_options,
            reasoning_config=request_options["reasoning_config"],
            output_contract=request_options["output_contract"],
        )
        context = AdvanceContext(
            run=run,
            session_key=session_key,
            user_session_item_id=inbound_record.user_session_item_id,
            draft=report_draft,
            resolved_tools=resolved_tools,
            request_envelope=request_envelope,
            request_render_snapshot_id=(
                request_render_snapshot.snapshot_id
                if request_render_snapshot is not None
                else None
            ),
            request_render_snapshot_metadata=(
                dict(request_render_snapshot.metadata)
                if request_render_snapshot is not None
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
        context: AdvanceContext,
        invocation: Any,
        session_item_ids: tuple[str, ...],
        assistant_progress_item_ids: tuple[str, ...],
        tool_call_session_item_ids_by_call_id: dict[str, str],
        tool_calls: tuple[ToolCallIntent, ...],
    ) -> EngineAdvanceOutcome:
        assert invocation.result is not None
        tool_call_names = tuple(tool_call.name for tool_call in tool_calls)
        extra_assistant_progress_item_ids: tuple[str, ...] = ()
        if not session_item_ids:
            with self._timed_phase("tool_assistant_items", detailed=True):
                extra_assistant_progress_item_ids = tuple(
                    self._assistant_items_for_tool_calls(
                        context=context,
                        invocation=invocation,
                    )
                )
        with self._timed_phase("tool_execution"):
            execution_outcome = self.tool_executor.execute_tool_calls(
                run,
                session_key=context.session_key,
                active_session_id=context.draft.active_session_id,
                resolved_tools=context.resolved_tools,
                tool_calls=tool_calls,
                append_tool_call_messages=context.draft.surface_policy.record_tool_call_messages,
                append_tool_call_session_items=not session_item_ids,
                tool_call_session_item_ids_by_call_id=tool_call_session_item_ids_by_call_id,
                append_tool_result_messages=context.draft.surface_policy.record_tool_result_messages,
                invocation_id=invocation.id,
                extra_context_attrs=tool_execution_context_attrs(context),
            )
        all_assistant_progress_item_ids = unique_ids(
            (*assistant_progress_item_ids, *extra_assistant_progress_item_ids),
        )
        outcome_session_item_ids = unique_ids(
            (
                *session_item_ids,
                *extra_assistant_progress_item_ids,
                *execution_outcome.tool_call_session_item_ids,
                *execution_outcome.tool_result_session_item_ids,
            ),
        )
        with self._timed_phase("tool_outcome_build", detailed=True):
            return build_tool_execution_advance_outcome(
                context=context,
                invocation=invocation,
                session_item_ids=outcome_session_item_ids,
                assistant_progress_item_ids=all_assistant_progress_item_ids,
                tool_call_session_item_ids=execution_outcome.tool_call_session_item_ids,
                tool_result_session_item_ids=execution_outcome.tool_result_session_item_ids,
                tool_call_names=tool_call_names,
                execution_outcome=execution_outcome,
            )

    async def _advance_outcome_for_tool_calls_async(
        self,
        run: OrchestrationRun,
        *,
        context: AdvanceContext,
        invocation: Any,
        session_item_ids: tuple[str, ...],
        assistant_progress_item_ids: tuple[str, ...],
        tool_call_session_item_ids_by_call_id: dict[str, str],
        tool_calls: tuple[ToolCallIntent, ...],
    ) -> EngineAdvanceOutcome:
        assert invocation.result is not None
        tool_call_names = tuple(tool_call.name for tool_call in tool_calls)
        extra_assistant_progress_item_ids: tuple[str, ...] = ()
        if not session_item_ids:
            with self._timed_phase("tool_assistant_items", detailed=True):
                extra_assistant_progress_item_ids = tuple(
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
                active_session_id=context.draft.active_session_id,
                resolved_tools=context.resolved_tools,
                tool_calls=tool_calls,
                append_tool_call_messages=context.draft.surface_policy.record_tool_call_messages,
                append_tool_call_session_items=not session_item_ids,
                tool_call_session_item_ids_by_call_id=tool_call_session_item_ids_by_call_id,
                append_tool_result_messages=context.draft.surface_policy.record_tool_result_messages,
                invocation_id=invocation.id,
                extra_context_attrs=tool_execution_context_attrs(context),
            )
        all_assistant_progress_item_ids = unique_ids(
            (*assistant_progress_item_ids, *extra_assistant_progress_item_ids),
        )
        outcome_session_item_ids = unique_ids(
            (
                *session_item_ids,
                *extra_assistant_progress_item_ids,
                *execution_outcome.tool_call_session_item_ids,
                *execution_outcome.tool_result_session_item_ids,
            ),
        )
        with self._timed_phase("tool_outcome_build", detailed=True):
            return build_tool_execution_advance_outcome(
                context=context,
                invocation=invocation,
                session_item_ids=outcome_session_item_ids,
                assistant_progress_item_ids=all_assistant_progress_item_ids,
                tool_call_session_item_ids=execution_outcome.tool_call_session_item_ids,
                tool_result_session_item_ids=execution_outcome.tool_result_session_item_ids,
                tool_call_names=tool_call_names,
                execution_outcome=execution_outcome,
            )

    def _advance_outcome_for_message_only(
        self,
        *,
        context: AdvanceContext,
        invocation: Any,
        session_item_ids: tuple[str, ...],
        assistant_progress_item_ids: tuple[str, ...],
    ) -> EngineAdvanceOutcome:
        assert invocation.result is not None
        if not context.draft.surface_policy.record_assistant_messages:
            return build_engine_advance_outcome(
                context=context,
                invocation=invocation,
                session_item_ids=session_item_ids,
                assistant_progress_item_ids=assistant_progress_item_ids,
                continue_loop=continuation_needs_follow_up(invocation),
            )
        if session_item_ids:
            return build_engine_advance_outcome(
                context=context,
                invocation=invocation,
                session_item_ids=session_item_ids,
                assistant_progress_item_ids=assistant_progress_item_ids,
                continue_loop=continuation_needs_follow_up(invocation),
            )
        with self._timed_phase("assistant_item_record", detailed=True):
            assistant_session_item_ids = self.session_recorder.append_assistant_response_item(
                session_key=context.session_key,
                active_session_id=context.draft.active_session_id,
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
            return build_engine_advance_outcome(
                context=context,
                invocation=invocation,
                session_item_ids=(
                    *session_item_ids,
                    *assistant_session_item_ids,
                ),
                assistant_progress_item_ids=assistant_progress_item_ids,
                continue_loop=continuation_needs_follow_up(invocation),
            )

    def _assistant_items_for_tool_calls(
        self,
        *,
        context: AdvanceContext,
        invocation: Any,
    ) -> tuple[str, ...]:
        assert invocation.result is not None
        if not context.draft.surface_policy.record_assistant_messages:
            return ()
        if invocation.result.text is None or not invocation.result.text.strip():
            return ()
        return self.session_recorder.append_assistant_response_message(
            session_key=context.session_key,
            active_session_id=context.draft.active_session_id,
            invocation_id=invocation.id,
            response_text=invocation.result.text,
            structured_output=None,
            finish_reason="tool_calls",
            usage_payload=None,
        )

    def _record_llm_response_items(
        self,
        *,
        context: AdvanceContext,
        invocation: Any,
    ) -> RuntimeResponseRecord:
        response_items = getattr(invocation, "response_items", None)
        if not isinstance(response_items, (list, tuple)) or not response_items:
            return RuntimeResponseRecord()
        return self.session_recorder.append_llm_response_items(
            session_key=context.session_key,
            active_session_id=context.draft.active_session_id,
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

    def _tool_call_intent_for_background_run(
        self,
        *,
        run: OrchestrationRun,
        tool_run: ToolRun,
    ) -> ToolCallIntent | None:
        return tool_call_intent_for_background_run(
            run=run,
            tool_run=tool_run,
            background_tool_result_reference=(
                self.session_recorder.background_tool_result_reference
            ),
        )

    def _build_runtime_request_draft(
        self,
        run: OrchestrationRun,
    ) -> ResolvedRuntimeLlmRequestDraft:
        with self._timed_phase("tool_resolve", detailed=True):
            resolved_tools = self.tool_resolver.resolve(run)
        with self._timed_phase("runtime_request_draft_collect", detailed=True):
            draft = self.runtime_request_drafts.build(
                run,
                resolved_tools=resolved_tools,
            )
        return ResolvedRuntimeLlmRequestDraft(
            draft=draft,
            resolved_tools=resolved_tools,
        )

    def _build_runtime_request_preview_draft(
        self,
        run: OrchestrationRun,
    ) -> ResolvedRuntimeLlmRequestDraft:
        with self._timed_phase("tool_schema_candidate_resolve", detailed=True):
            resolved_tools = self.tool_resolver.resolve_schema_candidates(run)
        with self._timed_phase("runtime_request_draft_collect", detailed=True):
            draft = self.runtime_request_drafts.build(
                run,
                resolved_tools=resolved_tools,
                validate_llm_access=False,
            )
        return ResolvedRuntimeLlmRequestDraft(
            draft=draft,
            resolved_tools=resolved_tools,
        )

    def _resolve_tools_for_runtime_draft(
        self,
        run: OrchestrationRun,
        *,
        base_resolved_tools: ResolvedToolSet,
        draft: RuntimeLlmRequestDraft,
        request_render_snapshot: RequestRenderSnapshotRecord | None,
    ) -> ResolvedToolSet:
        visible_tool_names = self.runtime_llm_request_builder.visible_tool_schema_names(
            request_render_snapshot,
        )
        if draft.surface_policy.surface == "interactive" and visible_tool_names:
            return self.tool_resolver.resolve_for_schema_names(
                run,
                visible_tool_names,
            )
        return self.runtime_llm_request_builder.resolved_tools_for_draft(
            base_resolved_tools,
            draft,
            request_render_snapshot,
        )

    def _record_request_render_snapshot(
        self,
        run: OrchestrationRun,
        draft: RuntimeLlmRequestDraft,
    ) -> RequestRenderSnapshotRecord:
        try:
            snapshot = self.request_render_snapshot_port.record_run_request_render_snapshot(
                run=run,
                draft=draft,
            )
        except Exception as exc:  # pragma: no cover - defensive runtime guard.
            raise OrchestrationValidationError(
                "Context Workspace request render snapshot failed for orchestration run "
                f"'{run.id}': {exc}",
            ) from exc
        if snapshot is None:
            raise OrchestrationValidationError(
                "Context Workspace request render snapshot did not return a snapshot for "
                f"orchestration run '{run.id}'.",
            )
        return snapshot

    def _preview_request_render_snapshot(
        self,
        run: OrchestrationRun,
        draft: RuntimeLlmRequestDraft,
    ) -> RequestRenderSnapshotRecord:
        try:
            snapshot = self.request_render_snapshot_port.preview_run_request_render_snapshot(
                run=run,
                draft=draft,
            )
        except Exception as exc:  # pragma: no cover - defensive runtime guard.
            raise OrchestrationValidationError(
                "Context Workspace request render snapshot preview failed for orchestration run "
                f"'{run.id}': {exc}",
            ) from exc
        if snapshot is None:
            raise OrchestrationValidationError(
                "Context Workspace request render snapshot preview did not return a snapshot for "
                f"orchestration run '{run.id}'.",
            )
        return snapshot

    @staticmethod
    def _draft_with_recorded_transcript_window(
        draft: RuntimeLlmRequestDraft,
        request_render_snapshot: RequestRenderSnapshotRecord,
    ) -> RuntimeLlmRequestDraft:
        raw_count = request_render_snapshot.metadata.get(
            "draft_input_message_count",
        )
        if isinstance(raw_count, bool):
            return draft
        if not isinstance(raw_count, int):
            return draft
        count = max(0, raw_count)
        if count >= len(draft.messages):
            return draft
        return replace(draft, messages=draft.messages[:count])

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
