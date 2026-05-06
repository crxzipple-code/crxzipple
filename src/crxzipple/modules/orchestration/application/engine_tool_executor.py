from __future__ import annotations

import asyncio
from contextlib import nullcontext
from dataclasses import dataclass, field

from crxzipple.modules.llm.domain import ToolCallIntent
from crxzipple.modules.orchestration.application.engine_session_recorder import (
    OrchestrationSessionRecorder,
)
from crxzipple.modules.orchestration.application.ports import (
    ToolExecutionPort,
)
from crxzipple.modules.orchestration.application.tool_resolver import (
    ResolvedTool,
    ResolvedToolSet,
    ToolResolver,
)
from crxzipple.modules.orchestration.domain import (
    OrchestrationRun,
    OrchestrationValidationError,
    PendingApprovalRequest,
)
from crxzipple.modules.tool.application import ExecuteToolInput
from crxzipple.modules.tool.domain import (
    ToolEnvironment,
    ToolExecutionContext,
    ToolExecutionStrategy,
    ToolExecutionTarget,
    ToolMode,
    ToolRun,
    ToolRunStatus,
)
from crxzipple.shared.runtime_metrics import (
    RuntimeMetricsRegistry,
    get_runtime_metrics_registry,
)


@dataclass(frozen=True, slots=True)
class ToolExecutionBatchOutcome:
    tool_call_message_ids: tuple[str, ...] = field(default_factory=tuple)
    inline_runs: tuple[tuple[str | None, ToolRun], ...] = field(default_factory=tuple)
    background_runs: tuple[tuple[ToolCallIntent, ToolRun], ...] = field(default_factory=tuple)
    pending_approval_request: PendingApprovalRequest | None = None
    yield_requested: bool = False
    yield_reason: str | None = None


@dataclass(frozen=True, slots=True)
class _PreparedToolExecution:
    tool_call: ToolCallIntent
    tool_id: str
    target: ToolExecutionTarget


@dataclass(frozen=True, slots=True)
class _ToolExecutionBatchContext:
    execution_context: ToolExecutionContext | None
    context_attrs: dict[str, object]
    resolved_by_name: dict[str, ResolvedTool]
    resource_attrs_by_tool_id: dict[str, dict[str, object]]


@dataclass(slots=True)
class OrchestrationEngineToolExecutor:
    session_recorder: OrchestrationSessionRecorder
    tool_resolver: ToolResolver
    tool_execution_port: ToolExecutionPort
    detailed_phase_metrics_enabled: bool = False
    metrics: RuntimeMetricsRegistry = field(
        default_factory=get_runtime_metrics_registry,
    )

    def execute_tool_calls(
        self,
        run: OrchestrationRun,
        *,
        session_key: str,
        active_session_id: str,
        resolved_tools: ResolvedToolSet,
        tool_calls: tuple[ToolCallIntent, ...],
        append_tool_call_messages: bool,
        append_tool_result_messages: bool = True,
        extra_context_attrs: dict[str, object] | None = None,
    ) -> ToolExecutionBatchOutcome:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(
                self.execute_tool_calls_async(
                    run,
                    session_key=session_key,
                    active_session_id=active_session_id,
                    resolved_tools=resolved_tools,
                    tool_calls=tool_calls,
                    append_tool_call_messages=append_tool_call_messages,
                    append_tool_result_messages=append_tool_result_messages,
                    extra_context_attrs=extra_context_attrs,
                ),
            )
        raise OrchestrationValidationError(
            "execute_tool_calls cannot be called from an active asyncio loop; "
            "use execute_tool_calls_async instead.",
        )

    async def execute_tool_calls_async(
        self,
        run: OrchestrationRun,
        *,
        session_key: str,
        active_session_id: str,
        resolved_tools: ResolvedToolSet,
        tool_calls: tuple[ToolCallIntent, ...],
        append_tool_call_messages: bool,
        append_tool_result_messages: bool = True,
        extra_context_attrs: dict[str, object] | None = None,
    ) -> ToolExecutionBatchOutcome:
        tool_call_message_ids: list[str] = []
        inline_runs: list[tuple[str | None, ToolRun]] = []
        background_runs: list[tuple[ToolCallIntent, ToolRun]] = []
        prepared_executions: list[_PreparedToolExecution] = []
        pending_tool_call_messages: list[ToolCallIntent] = []
        yield_requested = False
        yield_reason: str | None = None
        batch_context = self._batch_context(
            run,
            session_key=session_key,
            resolved_tools=resolved_tools,
            extra_context_attrs=extra_context_attrs,
        )

        async def _flush_tool_call_messages() -> None:
            if not pending_tool_call_messages:
                return
            tool_call_batch = tuple(pending_tool_call_messages)
            pending_tool_call_messages.clear()
            with self._timed_engine_phase(
                "tool_call_messages",
                detailed=True,
            ):
                tool_call_message_ids.extend(
                    await asyncio.to_thread(
                        self.session_recorder.append_tool_call_messages,
                        session_key=session_key,
                        active_session_id=active_session_id,
                        invocation_id="",
                        response_text=None,
                        tool_calls=tool_call_batch,
                    ),
                )

        async def _flush_prepared_executions() -> None:
            nonlocal yield_requested, yield_reason
            if not prepared_executions:
                return
            await _flush_tool_call_messages()
            prepared_batch = tuple(prepared_executions)
            prepared_executions.clear()
            self.metrics.increment_counter(
                "orchestration.tool.batch_count",
            )
            self.metrics.increment_counter(
                "orchestration.tool.requested_calls",
                amount=len(prepared_batch),
            )
            with self.metrics.active("orchestration.tool.active_batches"):
                with self.metrics.timed("orchestration.tool.batch_seconds"):
                    tool_runs = await self.tool_execution_port.execute_many(
                        tuple(
                            ExecuteToolInput(
                                tool_id=prepared.tool_id,
                                arguments=dict(prepared.tool_call.arguments),
                                mode=prepared.target.mode,
                                strategy=prepared.target.strategy,
                                environment=prepared.target.environment,
                                execution_context=batch_context.execution_context,
                            )
                            for prepared in prepared_batch
                        ),
                    )
            self.metrics.increment_counter(
                "orchestration.tool.completed_calls",
                amount=len(tool_runs),
            )
            result_message_items: list[tuple[ToolCallIntent, ToolRun, str, str]] = []
            result_message_positions: list[int] = []
            for prepared, tool_run in zip(prepared_batch, tool_runs):
                self.metrics.increment_counter(
                    "orchestration.tool.result_status",
                    labels={
                        "status": tool_run.status.value,
                        "mode": prepared.target.mode.value,
                        "environment": prepared.target.environment.value,
                    },
                )
                tool_call = prepared.tool_call
                if tool_run.status is ToolRunStatus.QUEUED:
                    background_runs.append((tool_call, tool_run))
                    continue
                message_id: str | None = None
                if append_tool_result_messages:
                    result_message_positions.append(len(inline_runs))
                    result_message_items.append(
                        (tool_call, tool_run, "tool_run", tool_run.id),
                    )
                inline_runs.append((message_id, tool_run))
                tool_run_yield_requested, tool_run_yield_reason = self._yield_control(
                    tool_run,
                )
                if tool_run_yield_requested:
                    yield_requested = True
                    if yield_reason is None and tool_run_yield_reason is not None:
                        yield_reason = tool_run_yield_reason
            if result_message_items:
                with self._timed_engine_phase(
                    "tool_result_messages",
                    detailed=True,
                ):
                    message_ids = await asyncio.to_thread(
                        self.session_recorder.append_tool_result_messages,
                        session_key=session_key,
                        active_session_id=active_session_id,
                        items=tuple(result_message_items),
                    )
                for position, message_id in zip(
                    result_message_positions,
                    message_ids,
                ):
                    _, tool_run = inline_runs[position]
                    inline_runs[position] = (message_id, tool_run)

        for tool_call in tool_calls:
            resolved_tool = batch_context.resolved_by_name.get(tool_call.name)
            if resolved_tool is None:
                blocked_access = resolved_tools.blocked_access_by_name(tool_call.name)
                if blocked_access is not None:
                    access_payload = blocked_access.to_payload()
                    raise OrchestrationValidationError(
                        f"Tool call '{tool_call.name}' access is not ready.",
                        code="access_not_ready",
                        details={
                            "resource_type": "tool",
                            "resource_id": blocked_access.tool_id,
                            "display_name": blocked_access.tool_name,
                            "access": access_payload,
                        },
                    )
                raise OrchestrationValidationError(
                    f"Tool call '{tool_call.name}' is not available in this orchestration run.",
                )
            if append_tool_call_messages:
                pending_tool_call_messages.append(tool_call)
            execution_decision = self.tool_resolver.execution_decision(
                run,
                tool=resolved_tool.tool,
                target=resolved_tool.target,
                context_attrs=batch_context.context_attrs,
                resource_attrs=self._resource_attrs_for(batch_context, resolved_tool),
            )
            if execution_decision.mode == "blocked":
                await _flush_tool_call_messages()
                await _flush_prepared_executions()
                raise OrchestrationValidationError(
                    f"Tool call '{tool_call.name}' is not allowed in this orchestration run.",
                )
            if execution_decision.mode == "approval_required":
                await _flush_tool_call_messages()
                await _flush_prepared_executions()
                approval = execution_decision.approval
                if approval is None:
                    raise OrchestrationValidationError(
                        f"Tool call '{tool_call.name}' requires approval but no approval details were provided.",
                    )
                return ToolExecutionBatchOutcome(
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
            prepared_executions.append(
                _PreparedToolExecution(
                    tool_call=tool_call,
                    tool_id=resolved_tool.tool.id,
                    target=resolved_tool.target,
                ),
            )
        await _flush_prepared_executions()
        await _flush_tool_call_messages()
        return ToolExecutionBatchOutcome(
            tool_call_message_ids=tuple(tool_call_message_ids),
            inline_runs=tuple(inline_runs),
            background_runs=tuple(background_runs),
            yield_requested=yield_requested,
            yield_reason=yield_reason,
        )

    def _resource_attrs_for(
        self,
        batch_context: _ToolExecutionBatchContext,
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

    def _batch_context(
        self,
        run: OrchestrationRun,
        *,
        session_key: str,
        resolved_tools: ResolvedToolSet,
        extra_context_attrs: dict[str, object] | None = None,
    ) -> _ToolExecutionBatchContext:
        attrs = self.tool_resolver.invocation_context_attrs(
            run,
            session_key=session_key,
        )
        if extra_context_attrs:
            attrs = {
                **extra_context_attrs,
                **attrs,
            }
        resolved_by_name: dict[str, ResolvedTool] = {}
        for resolved_tool in resolved_tools.tools:
            resolved_by_name[resolved_tool.tool.id] = resolved_tool
            resolved_by_name[resolved_tool.schema.name] = resolved_tool
        return _ToolExecutionBatchContext(
            execution_context=ToolExecutionContext(attrs=attrs) if attrs else None,
            context_attrs=attrs,
            resolved_by_name=resolved_by_name,
            resource_attrs_by_tool_id={},
        )

    def replay_approved_tool_call(
        self,
        run: OrchestrationRun,
        *,
        request: PendingApprovalRequest,
    ) -> ToolExecutionBatchOutcome:
        if (
            request.tool_name is None
            or request.execution_mode is None
            or request.execution_strategy is None
            or request.execution_environment is None
        ):
            return ToolExecutionBatchOutcome()
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
        return self.execute_tool_calls(
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


    def _invocation_context(
        self,
        run: OrchestrationRun,
        *,
        session_key: str,
    ) -> ToolExecutionContext | None:
        attrs = self.tool_resolver.invocation_context_attrs(
            run,
            session_key=session_key,
        )
        if not attrs:
            return None
        return ToolExecutionContext(attrs=attrs)

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

    @staticmethod
    def _yield_control(tool_run: ToolRun) -> tuple[bool, str | None]:
        tool_result = tool_run.result
        if tool_result is None:
            return False, None
        payload = tool_result.metadata.get("session_control")
        if not isinstance(payload, dict):
            return False, None
        if payload.get("yield") is not True:
            return False, None
        reason = payload.get("reason")
        if isinstance(reason, str):
            normalized_reason = reason.strip()
            if normalized_reason:
                return True, normalized_reason
        return True, None

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
