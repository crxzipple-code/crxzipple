from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import dataclass, field, replace

from crxzipple.modules.llm.domain import ToolCallIntent
from crxzipple.modules.orchestration.application.engine_session_recorder import (
    OrchestrationSessionRecorder,
)
from crxzipple.modules.orchestration.application.ports import ToolExecutionPort
from crxzipple.modules.orchestration.application.tool_dispatch_guard import (
    ToolDispatchGuard,
)
from crxzipple.modules.orchestration.application.tool_execution_records import (
    PreparedToolExecution,
    ToolExecutionBatchOutcome,
    ToolExecutionBatchState,
    ToolExecutionPlan,
)
from crxzipple.modules.orchestration.application.tool_execution_grouping import (
    group_prepared_tool_executions,
)
from crxzipple.modules.orchestration.application.tool_execution_result_recorder import (
    record_tool_execution_result,
)
from crxzipple.modules.orchestration.application.tool_probe_observation import (
    RunMetadataToolProbeObservationRecorder,
    ToolProbeObservationPort,
)
from crxzipple.modules.orchestration.application.tool_resolver import (
    ResolvedTool,
    ResolvedToolSet,
    ToolExecutionDecision,
    ToolResolver,
)
from crxzipple.modules.orchestration.application.tool_resource_policy import (
    ToolResourcePolicy,
    optional_context_text,
    tool_resource_policy,
)
from crxzipple.modules.orchestration.domain import (
    OrchestrationRun,
    OrchestrationValidationError,
    PendingApprovalRequest,
)
from crxzipple.modules.tool.application import ExecuteToolInput
from crxzipple.modules.tool.domain import ToolExecutionContext, ToolRun
from crxzipple.shared.runtime_metrics import (
    RuntimeMetricsRegistry,
    get_runtime_metrics_registry,
)


@dataclass(frozen=True, slots=True)
class ToolExecutionBatchContext:
    execution_context: ToolExecutionContext | None
    context_attrs: dict[str, object]
    resolved_by_name: dict[str, ResolvedTool]
    tool_surface_refs_by_name: dict[str, "ToolSurfaceFunctionRef"]
    resource_attrs_by_tool_id: dict[str, dict[str, object]]


@dataclass(frozen=True, slots=True)
class ToolSurfaceFunctionRef:
    tool_id: str
    name: str
    source_id: str | None = None
    group_key: str | None = None


@dataclass(slots=True)
class ToolExecutionBatchRunner:
    session_recorder: OrchestrationSessionRecorder
    tool_resolver: ToolResolver
    tool_execution_port: ToolExecutionPort
    run_dispatch_guard: Callable[[OrchestrationRun], bool] | None = None
    probe_observation_recorder: ToolProbeObservationPort = field(
        default_factory=RunMetadataToolProbeObservationRecorder,
    )
    detailed_phase_metrics_enabled: bool = False
    metrics: RuntimeMetricsRegistry = field(
        default_factory=get_runtime_metrics_registry,
    )

    async def execute(
        self,
        run: OrchestrationRun,
        *,
        session_key: str,
        active_session_id: str,
        resolved_tools: ResolvedToolSet,
        tool_calls: tuple[ToolCallIntent, ...],
        append_tool_call_messages: bool,
        append_tool_call_session_items: bool = False,
        tool_call_session_item_ids_by_call_id: dict[str, str] | None = None,
        append_tool_result_messages: bool = True,
        invocation_id: str | None = None,
        extra_context_attrs: dict[str, object] | None = None,
        require_running_run: bool = True,
    ) -> ToolExecutionBatchOutcome:
        state = ToolExecutionBatchState.from_tool_call_session_item_ids(
            tool_call_session_item_ids_by_call_id,
        )
        batch_context = self._batch_context(
            run,
            session_key=session_key,
            active_session_id=active_session_id,
            resolved_tools=resolved_tools,
            extra_context_attrs=extra_context_attrs,
        )
        dispatch_guard = self._dispatch_guard()

        async def _append_tool_call_messages(
            tool_call_batch: tuple[ToolCallIntent, ...],
        ) -> None:
            await self._append_tool_call_session_records(
                state,
                session_key=session_key,
                active_session_id=active_session_id,
                invocation_id=invocation_id,
                append_tool_call_session_items=append_tool_call_session_items,
                tool_call_batch=tool_call_batch,
            )

        async def _flush_tool_call_messages() -> None:
            if not state.pending_tool_call_messages:
                return
            tool_call_batch = tuple(state.pending_tool_call_messages)
            state.pending_tool_call_messages.clear()
            await _append_tool_call_messages(tool_call_batch)

        async def _flush_tool_call_messages_for(
            tool_calls_to_flush: tuple[ToolCallIntent, ...],
        ) -> None:
            if not state.pending_tool_call_messages or not tool_calls_to_flush:
                return
            flush_ids = {tool_call.id for tool_call in tool_calls_to_flush}
            tool_call_batch = tuple(
                tool_call
                for tool_call in state.pending_tool_call_messages
                if tool_call.id in flush_ids
            )
            if not tool_call_batch:
                return
            state.pending_tool_call_messages[:] = [
                tool_call
                for tool_call in state.pending_tool_call_messages
                if tool_call.id not in flush_ids
            ]
            await _append_tool_call_messages(tool_call_batch)

        async def _flush_tool_result_messages(
            result_message_items: list[tuple[ToolCallIntent, ToolRun, str, str]],
            result_link_positions: list[int],
        ) -> None:
            await self._append_tool_result_session_records(
                state,
                session_key=session_key,
                active_session_id=active_session_id,
                result_message_items=result_message_items,
                result_link_positions=result_link_positions,
            )

        async def _flush_prepared_executions() -> None:
            if not state.prepared_executions:
                return
            if not dispatch_guard.accepts(
                run,
                require_running_run=require_running_run,
            ):
                state.clear_pending_dispatch()
                self.metrics.increment_counter(
                    "orchestration.tool.dispatch_skipped",
                    labels={"reason": "run_not_running"},
                )
                return
            prepared_batch = tuple(state.prepared_executions)
            state.prepared_executions.clear()
            self.metrics.increment_counter(
                "orchestration.tool.requested_calls",
                amount=len(prepared_batch),
            )

            for execution_batch in group_prepared_tool_executions(prepared_batch):
                if state.yield_requested or state.stop_remaining_batches:
                    break
                if not dispatch_guard.accepts(
                    run,
                    require_running_run=require_running_run,
                ):
                    state.pending_tool_call_messages.clear()
                    self.metrics.increment_counter(
                        "orchestration.tool.dispatch_skipped",
                        labels={"reason": "run_not_running"},
                    )
                    break
                await _flush_tool_call_messages_for(
                    tuple(prepared.tool_call for prepared in execution_batch),
                )
                if not dispatch_guard.accepts(
                    run,
                    require_running_run=require_running_run,
                ):
                    state.pending_tool_call_messages.clear()
                    self.metrics.increment_counter(
                        "orchestration.tool.dispatch_skipped",
                        labels={"reason": "run_not_running"},
                    )
                    break
                self.metrics.increment_counter(
                    "orchestration.tool.batch_count",
                )
                with self.metrics.active("orchestration.tool.active_batches"):
                    with self.metrics.timed("orchestration.tool.batch_seconds"):
                        tool_runs = await self.tool_execution_port.execute_many(
                            tuple(
                                ExecuteToolInput(
                                    tool_id=prepared.tool_id,
                                    arguments=dict(prepared.tool_call.arguments),
                                    call_id=prepared.tool_call.id,
                                    tool_surface_id=optional_context_text(
                                        batch_context.context_attrs.get(
                                            "tool_surface_id",
                                        ),
                                    ),
                                    metadata=self._tool_run_metadata(
                                        run,
                                        session_key=session_key,
                                        active_session_id=active_session_id,
                                        prepared=prepared,
                                        batch_context=batch_context,
                                    ),
                                    mode=prepared.target.mode,
                                    strategy=prepared.target.strategy,
                                    environment=prepared.target.environment,
                                    execution_context=batch_context.execution_context,
                                )
                                for prepared in execution_batch
                            ),
                        )
                self.metrics.increment_counter(
                    "orchestration.tool.completed_calls",
                    amount=len(tool_runs),
                )
                result_message_items: list[tuple[ToolCallIntent, ToolRun, str, str]] = []
                result_link_positions: list[int] = []
                for prepared, tool_run in zip(execution_batch, tool_runs):
                    self.metrics.increment_counter(
                        "orchestration.tool.result_status",
                        labels={
                            "status": tool_run.status.value,
                            "mode": prepared.target.mode.value,
                            "environment": prepared.target.environment.value,
                        },
                    )
                    record = record_tool_execution_result(
                        state,
                        prepared,
                        tool_run,
                        append_tool_result_messages=append_tool_result_messages,
                    )
                    if record.result_message_item is not None:
                        result_message_items.append(record.result_message_item)
                    if record.result_link_position is not None:
                        result_link_positions.append(record.result_link_position)
                await _flush_tool_result_messages(
                    result_message_items,
                    result_link_positions,
                )
            if state.yield_requested or state.stop_remaining_batches:
                state.pending_tool_call_messages.clear()

        for tool_call in tool_calls:
            resolved_tool = self._resolved_tool_for_call(
                tool_call,
                batch_context=batch_context,
                resolved_tools=resolved_tools,
            )
            execution_decision = self.tool_resolver.execution_decision(
                run,
                tool=resolved_tool.tool,
                target=resolved_tool.target,
                context_attrs=batch_context.context_attrs,
                resource_attrs=self._resource_attrs_for(batch_context, resolved_tool),
                arguments=tool_call.arguments,
            )
            if execution_decision.mode == "blocked":
                await _flush_prepared_executions()
                if state.yield_requested:
                    return state.outcome()
                raise OrchestrationValidationError(
                    f"Tool call '{tool_call.name}' is not allowed in this orchestration run.",
                )
            if execution_decision.mode == "approval_required":
                await _flush_prepared_executions()
                if state.yield_requested:
                    return state.outcome()
                if append_tool_call_messages or append_tool_call_session_items:
                    state.pending_tool_call_messages.append(tool_call)
                await _flush_tool_call_messages()
                return state.outcome(
                    pending_approval_request=self._pending_approval_request(
                        tool_call,
                        resolved_tool=resolved_tool,
                        execution_decision=execution_decision,
                    ),
                )
            if append_tool_call_messages or append_tool_call_session_items:
                state.pending_tool_call_messages.append(tool_call)
            self.probe_observation_recorder.record_tool_call(
                run,
                tool_id=resolved_tool.tool.id,
                tool_call=tool_call,
            )
            prepared = self._prepared_execution(
                tool_call,
                resolved_tool=resolved_tool,
                batch_context=batch_context,
            )
            if prepared.plan is not None:
                state.tool_execution_plans.append(prepared.plan)
            state.prepared_executions.append(prepared)
        await _flush_prepared_executions()
        if not state.yield_requested and not state.stop_remaining_batches:
            await _flush_tool_call_messages()
        return state.outcome()

    async def _append_tool_call_session_records(
        self,
        state: ToolExecutionBatchState,
        *,
        session_key: str,
        active_session_id: str,
        invocation_id: str | None,
        append_tool_call_session_items: bool,
        tool_call_batch: tuple[ToolCallIntent, ...],
    ) -> None:
        if not tool_call_batch:
            return
        with self._timed_engine_phase(
            "tool_call_messages",
            detailed=True,
        ):
            record = await asyncio.to_thread(
                self.session_recorder.append_tool_call_records,
                session_key=session_key,
                active_session_id=active_session_id,
                invocation_id=invocation_id or "",
                response_text=None,
                tool_calls=tool_call_batch,
                append_session_items=append_tool_call_session_items,
            )
        state.tool_call_session_item_ids.extend(record.item_ids)
        for tool_call, item_id in zip(tool_call_batch, record.item_ids):
            if item_id:
                state.tool_call_session_item_id_by_call_id[tool_call.id] = item_id

    @staticmethod
    def _pending_approval_request(
        tool_call: ToolCallIntent,
        *,
        resolved_tool: ResolvedTool,
        execution_decision: ToolExecutionDecision,
    ) -> PendingApprovalRequest:
        approval = execution_decision.approval
        if approval is None:
            raise OrchestrationValidationError(
                f"Tool call '{tool_call.name}' requires approval but no approval details were provided.",
            )
        return PendingApprovalRequest(
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
        )

    async def _append_tool_result_session_records(
        self,
        state: ToolExecutionBatchState,
        *,
        session_key: str,
        active_session_id: str,
        result_message_items: list[tuple[ToolCallIntent, ToolRun, str, str]],
        result_link_positions: list[int],
    ) -> None:
        if not result_message_items:
            return
        with self._timed_engine_phase(
            "tool_result_messages",
            detailed=True,
        ):
            record = await asyncio.to_thread(
                self.session_recorder.append_tool_result_records,
                session_key=session_key,
                active_session_id=active_session_id,
                items=tuple(result_message_items),
            )
        item_ids = record.item_ids
        state.tool_result_session_item_ids.extend(item_ids)
        for item_position, position in enumerate(result_link_positions):
            result_session_item_id = None
            if item_position < len(item_ids):
                result_session_item_id = item_ids[item_position]
            state.tool_run_links[position] = replace(
                state.tool_run_links[position],
                result_session_item_id=result_session_item_id,
            )

    def _dispatch_guard(self) -> ToolDispatchGuard:
        return ToolDispatchGuard(external_guard=self.run_dispatch_guard)

    def _resource_attrs_for(
        self,
        batch_context: ToolExecutionBatchContext,
        resolved_tool: ResolvedTool,
    ) -> dict[str, object]:
        cached = batch_context.resource_attrs_by_tool_id.get(resolved_tool.tool.id)
        if cached is not None:
            return cached
        attrs = self.tool_resolver.resource_attrs(
            resolved_tool.tool,
            target=resolved_tool.target,
        )
        batch_context.resource_attrs_by_tool_id[resolved_tool.tool.id] = attrs
        return attrs

    @staticmethod
    def _resource_policy(
        resolved_tool: ResolvedTool,
        *,
        tool_call: ToolCallIntent,
        batch_context: ToolExecutionBatchContext,
    ) -> ToolResourcePolicy:
        return tool_resource_policy(
            resolved_tool,
            tool_call=tool_call,
            context_attrs=batch_context.context_attrs,
        )

    def _resolved_tool_for_call(
        self,
        tool_call: ToolCallIntent,
        *,
        batch_context: ToolExecutionBatchContext,
        resolved_tools: ResolvedToolSet,
    ) -> ResolvedTool:
        surface_ref = self._tool_surface_ref_for(batch_context, tool_call)
        if surface_ref is None and batch_context.tool_surface_refs_by_name:
            raise OrchestrationValidationError(
                f"Tool call '{tool_call.name}' is not visible in the request ToolSurface.",
                code="tool_surface_not_visible",
                details={
                    "resource_type": "tool_surface",
                    "tool_surface_id": optional_context_text(
                        batch_context.context_attrs.get("tool_surface_id"),
                    ),
                    "tool_call_id": tool_call.id,
                    "tool_name": tool_call.name,
                    "visible_tool_names": sorted(
                        {
                            ref.name
                            for ref in batch_context.tool_surface_refs_by_name.values()
                        },
                    ),
                },
            )
        resolved_tool = batch_context.resolved_by_name.get(tool_call.name)
        if resolved_tool is None:
            blocked_access = resolved_tools.blocked_access_by_name(tool_call.name)
            if blocked_access is not None:
                raise OrchestrationValidationError(
                    f"Tool call '{tool_call.name}' access is not ready.",
                    code="access_not_ready",
                    details={
                        "resource_type": "tool",
                        "resource_id": blocked_access.tool_id,
                        "display_name": blocked_access.tool_name,
                        "access": blocked_access.to_payload(),
                    },
                )
            raise OrchestrationValidationError(
                f"Tool call '{tool_call.name}' is not available in this orchestration run.",
            )
        if surface_ref is not None and surface_ref.tool_id != resolved_tool.tool.id:
            raise OrchestrationValidationError(
                f"Tool call '{tool_call.name}' does not match the request ToolSurface.",
                code="tool_surface_mismatch",
                details={
                    "resource_type": "tool_surface",
                    "tool_surface_id": optional_context_text(
                        batch_context.context_attrs.get("tool_surface_id"),
                    ),
                    "tool_call_id": tool_call.id,
                    "tool_name": tool_call.name,
                    "surface_tool_id": surface_ref.tool_id,
                    "resolved_tool_id": resolved_tool.tool.id,
                },
            )
        return resolved_tool

    def _prepared_execution(
        self,
        tool_call: ToolCallIntent,
        *,
        resolved_tool: ResolvedTool,
        batch_context: ToolExecutionBatchContext,
    ) -> PreparedToolExecution:
        prepared = PreparedToolExecution(
            tool_call=tool_call,
            tool_id=resolved_tool.tool.id,
            target=resolved_tool.target,
            tool_surface_id=optional_context_text(
                batch_context.context_attrs.get("tool_surface_id"),
            ),
            resource_policy=self._resource_policy(
                resolved_tool,
                tool_call=tool_call,
                batch_context=batch_context,
            ),
        )
        return replace(prepared, plan=ToolExecutionPlan.from_execution(prepared))

    def _batch_context(
        self,
        run: OrchestrationRun,
        *,
        session_key: str,
        active_session_id: str,
        resolved_tools: ResolvedToolSet,
        extra_context_attrs: dict[str, object] | None = None,
    ) -> ToolExecutionBatchContext:
        attrs = self.tool_resolver.invocation_context_attrs(
            run,
            session_key=session_key,
        )
        if extra_context_attrs:
            attrs = {
                **extra_context_attrs,
                **attrs,
            }
        normalized_active_session_id = active_session_id.strip()
        if normalized_active_session_id:
            attrs["active_session_id"] = normalized_active_session_id
        trace_id = optional_context_text(run.metadata.get("trace_id")) or run.id
        if trace_id:
            attrs["trace_id"] = trace_id
        resolved_by_name: dict[str, ResolvedTool] = {}
        for resolved_tool in resolved_tools.tools:
            resolved_by_name[resolved_tool.tool.id] = resolved_tool
            resolved_by_name[resolved_tool.schema.name] = resolved_tool
        return ToolExecutionBatchContext(
            execution_context=ToolExecutionContext(attrs=attrs) if attrs else None,
            context_attrs=attrs,
            resolved_by_name=resolved_by_name,
            tool_surface_refs_by_name=_tool_surface_refs_by_name(
                attrs.get("tool_surface_functions"),
            ),
            resource_attrs_by_tool_id={},
        )

    @staticmethod
    def _tool_surface_ref_for(
        batch_context: ToolExecutionBatchContext,
        tool_call: ToolCallIntent,
    ) -> ToolSurfaceFunctionRef | None:
        return batch_context.tool_surface_refs_by_name.get(tool_call.name)

    @staticmethod
    def _tool_run_metadata(
        run: OrchestrationRun,
        *,
        session_key: str,
        active_session_id: str,
        prepared: PreparedToolExecution,
        batch_context: ToolExecutionBatchContext,
    ) -> dict[str, object]:
        metadata: dict[str, object] = {
            "source": "orchestration",
            "orchestration_run_id": run.id,
            "session_key": session_key,
            "active_session_id": active_session_id,
            "tool_call_id": prepared.tool_call.id,
            "tool_name": prepared.tool_call.name,
            "queue_policy": run.queue_policy.value,
            "priority": run.priority,
        }
        if run.agent_id is not None:
            metadata["agent_id"] = run.agent_id
        if run.lane_key is not None:
            metadata["lane_key"] = run.lane_key
        if run.lane_lock_key is not None:
            metadata["lane_lock_key"] = run.lane_lock_key
        for key in (
            "tool_surface_id",
            "tool_surface_snapshot_id",
            "request_render_snapshot_id",
        ):
            value = optional_context_text(batch_context.context_attrs.get(key))
            if value is not None:
                metadata[key] = value
        workspace_dir = batch_context.context_attrs.get("workspace_dir")
        if isinstance(workspace_dir, str) and workspace_dir.strip():
            metadata["workspace_dir"] = workspace_dir
        resource_policy_payload = prepared.resource_policy.to_payload()
        if resource_policy_payload:
            metadata["tool_resource_policy"] = resource_policy_payload
        if prepared.plan is not None:
            metadata["tool_execution_plan"] = prepared.plan.to_payload()
        return metadata

    def _timed_engine_phase(
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


def _tool_surface_refs_by_name(value: object) -> dict[str, ToolSurfaceFunctionRef]:
    if not isinstance(value, (list, tuple)):
        return {}
    refs: dict[str, ToolSurfaceFunctionRef] = {}
    for item in value:
        if not isinstance(item, dict):
            continue
        tool_id = optional_context_text(item.get("tool_id"))
        name = optional_context_text(item.get("name"))
        if tool_id is None or name is None:
            continue
        ref = ToolSurfaceFunctionRef(
            tool_id=tool_id,
            name=name,
            source_id=optional_context_text(item.get("source_id")),
            group_key=optional_context_text(item.get("group_key")),
        )
        refs[tool_id] = ref
        refs[name] = ref
    return refs


__all__ = [
    "ToolExecutionBatchContext",
    "ToolExecutionBatchRunner",
    "ToolExecutionBatchState",
    "ToolSurfaceFunctionRef",
]
