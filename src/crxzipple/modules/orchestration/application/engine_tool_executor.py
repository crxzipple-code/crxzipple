from __future__ import annotations

import asyncio
from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import dataclass, field, replace
import hashlib
import json
from urllib.parse import urlparse

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
    OrchestrationRunStatus,
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
class ToolRunLink:
    tool_call_id: str
    tool_name: str
    tool_run_id: str
    tool_id: str
    status: str
    mode: str
    strategy: str
    environment: str
    result_message_id: str | None = None
    background: bool = False
    tool_lifecycle: dict[str, object] = field(default_factory=dict)

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "tool_call_id": self.tool_call_id,
            "tool_name": self.tool_name,
            "tool_run_id": self.tool_run_id,
            "tool_id": self.tool_id,
            "status": self.status,
            "mode": self.mode,
            "strategy": self.strategy,
            "environment": self.environment,
            "result_message_id": self.result_message_id,
            "background": self.background,
        }
        if self.tool_lifecycle:
            payload["tool_lifecycle"] = dict(self.tool_lifecycle)
        return payload


@dataclass(frozen=True, slots=True)
class ToolExecutionBatchOutcome:
    tool_call_message_ids: tuple[str, ...] = field(default_factory=tuple)
    inline_runs: tuple[tuple[str | None, ToolRun], ...] = field(default_factory=tuple)
    background_runs: tuple[tuple[ToolCallIntent, ToolRun], ...] = field(default_factory=tuple)
    tool_run_links: tuple[ToolRunLink, ...] = field(default_factory=tuple)
    pending_approval_request: PendingApprovalRequest | None = None
    yield_requested: bool = False
    yield_reason: str | None = None


@dataclass(frozen=True, slots=True)
class _PreparedToolExecution:
    tool_call: ToolCallIntent
    tool_id: str
    target: ToolExecutionTarget
    resource_policy: _ToolResourcePolicy


@dataclass(frozen=True, slots=True)
class _ToolResourcePolicy:
    supports_parallel: bool
    mutates_state: bool
    execution_lane: str
    resource_scope: str | None = None
    resource_key: str | None = None
    serial_group_key: str | None = None

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "supports_parallel": self.supports_parallel,
            "mutates_state": self.mutates_state,
            "execution_lane": self.execution_lane,
        }
        if self.resource_scope is not None:
            payload["resource_scope"] = self.resource_scope
        if self.resource_key is not None:
            payload["resource_key"] = self.resource_key
        if self.serial_group_key is not None:
            payload["serial_group_key"] = self.serial_group_key
        return payload


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
    run_dispatch_guard: Callable[[OrchestrationRun], bool] | None = None
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
        require_running_run: bool = True,
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
                    require_running_run=require_running_run,
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
        require_running_run: bool = True,
    ) -> ToolExecutionBatchOutcome:
        tool_call_message_ids: list[str] = []
        inline_runs: list[tuple[str | None, ToolRun]] = []
        background_runs: list[tuple[ToolCallIntent, ToolRun]] = []
        tool_run_links: list[ToolRunLink] = []
        prepared_executions: list[_PreparedToolExecution] = []
        pending_tool_call_messages: list[ToolCallIntent] = []
        yield_requested = False
        yield_reason: str | None = None
        stop_remaining_batches = False
        batch_context = self._batch_context(
            run,
            session_key=session_key,
            active_session_id=active_session_id,
            resolved_tools=resolved_tools,
            extra_context_attrs=extra_context_attrs,
        )

        async def _append_tool_call_messages(
            tool_call_batch: tuple[ToolCallIntent, ...],
        ) -> None:
            if not tool_call_batch:
                return
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

        async def _flush_tool_call_messages() -> None:
            if not pending_tool_call_messages:
                return
            tool_call_batch = tuple(pending_tool_call_messages)
            pending_tool_call_messages.clear()
            await _append_tool_call_messages(tool_call_batch)

        async def _flush_tool_call_messages_for(
            tool_calls_to_flush: tuple[ToolCallIntent, ...],
        ) -> None:
            if not pending_tool_call_messages or not tool_calls_to_flush:
                return
            flush_ids = {tool_call.id for tool_call in tool_calls_to_flush}
            tool_call_batch = tuple(
                tool_call
                for tool_call in pending_tool_call_messages
                if tool_call.id in flush_ids
            )
            if not tool_call_batch:
                return
            pending_tool_call_messages[:] = [
                tool_call
                for tool_call in pending_tool_call_messages
                if tool_call.id not in flush_ids
            ]
            await _append_tool_call_messages(tool_call_batch)

        def _request_yield(reason: str | None) -> None:
            nonlocal yield_requested, yield_reason
            yield_requested = True
            if yield_reason is None and reason is not None:
                yield_reason = reason

        def _stop_remaining_batches() -> None:
            nonlocal stop_remaining_batches
            stop_remaining_batches = True

        def _batch_outcome(
            *,
            pending_approval_request: PendingApprovalRequest | None = None,
        ) -> ToolExecutionBatchOutcome:
            return ToolExecutionBatchOutcome(
                tool_call_message_ids=tuple(tool_call_message_ids),
                inline_runs=tuple(inline_runs),
                background_runs=tuple(background_runs),
                tool_run_links=tuple(tool_run_links),
                pending_approval_request=pending_approval_request,
                yield_requested=yield_requested,
                yield_reason=yield_reason,
            )

        async def _flush_tool_result_messages(
            result_message_items: list[tuple[ToolCallIntent, ToolRun, str, str]],
            result_message_positions: list[int],
            result_link_positions: list[int],
        ) -> None:
            if not result_message_items:
                return
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
            for position, message_id in zip(result_link_positions, message_ids):
                tool_run_links[position] = replace(
                    tool_run_links[position],
                    result_message_id=message_id,
                )

        async def _flush_prepared_executions() -> None:
            if not prepared_executions:
                return
            if not self._run_accepts_tool_dispatch(
                run,
                require_running_run=require_running_run,
            ):
                prepared_executions.clear()
                pending_tool_call_messages.clear()
                self.metrics.increment_counter(
                    "orchestration.tool.dispatch_skipped",
                    labels={"reason": "run_not_running"},
                )
                return
            prepared_batch = tuple(prepared_executions)
            prepared_executions.clear()
            self.metrics.increment_counter(
                "orchestration.tool.requested_calls",
                amount=len(prepared_batch),
            )

            for execution_batch in self._execution_groups(prepared_batch):
                if yield_requested or stop_remaining_batches:
                    break
                if not self._run_accepts_tool_dispatch(
                    run,
                    require_running_run=require_running_run,
                ):
                    pending_tool_call_messages.clear()
                    self.metrics.increment_counter(
                        "orchestration.tool.dispatch_skipped",
                        labels={"reason": "run_not_running"},
                    )
                    break
                await _flush_tool_call_messages_for(
                    tuple(prepared.tool_call for prepared in execution_batch),
                )
                if not self._run_accepts_tool_dispatch(
                    run,
                    require_running_run=require_running_run,
                ):
                    pending_tool_call_messages.clear()
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
                result_message_positions: list[int] = []
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
                    tool_call = prepared.tool_call
                    if tool_run.status is ToolRunStatus.QUEUED:
                        background_runs.append((tool_call, tool_run))
                        tool_run_links.append(
                            self._tool_run_link(
                                prepared,
                                tool_run,
                                background=True,
                            ),
                        )
                        continue
                    message_id: str | None = None
                    if append_tool_result_messages:
                        result_message_positions.append(len(inline_runs))
                        result_link_positions.append(len(tool_run_links))
                        result_message_items.append(
                            (tool_call, tool_run, "tool_run", tool_run.id),
                        )
                    inline_runs.append((message_id, tool_run))
                    tool_run_links.append(
                        self._tool_run_link(
                            prepared,
                            tool_run,
                            background=False,
                        ),
                    )
                    tool_run_yield_requested, tool_run_yield_reason = self._yield_control(
                        tool_run,
                    )
                    if tool_run_yield_requested:
                        _request_yield(tool_run_yield_reason)
                    elif self._terminal_plan_stops_remaining_batches(tool_run):
                        _stop_remaining_batches()
                await _flush_tool_result_messages(
                    result_message_items,
                    result_message_positions,
                    result_link_positions,
                )
            if yield_requested or stop_remaining_batches:
                pending_tool_call_messages.clear()

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
                if yield_requested:
                    return _batch_outcome()
                raise OrchestrationValidationError(
                    f"Tool call '{tool_call.name}' is not allowed in this orchestration run.",
                )
            if execution_decision.mode == "approval_required":
                await _flush_prepared_executions()
                if yield_requested:
                    return _batch_outcome()
                if append_tool_call_messages:
                    pending_tool_call_messages.append(tool_call)
                await _flush_tool_call_messages()
                approval = execution_decision.approval
                if approval is None:
                    raise OrchestrationValidationError(
                        f"Tool call '{tool_call.name}' requires approval but no approval details were provided.",
                    )
                return _batch_outcome(
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
            if append_tool_call_messages:
                pending_tool_call_messages.append(tool_call)
            _record_tool_probe_observation(
                run,
                tool_id=resolved_tool.tool.id,
                tool_call=tool_call,
            )
            prepared_executions.append(
                _PreparedToolExecution(
                    tool_call=tool_call,
                    tool_id=resolved_tool.tool.id,
                    target=resolved_tool.target,
                    resource_policy=self._resource_policy(
                        resolved_tool,
                        tool_call=tool_call,
                        batch_context=batch_context,
                    ),
                ),
            )
        await _flush_prepared_executions()
        if not yield_requested and not stop_remaining_batches:
            await _flush_tool_call_messages()
        return _batch_outcome()

    def _run_accepts_tool_dispatch(
        self,
        run: OrchestrationRun,
        *,
        require_running_run: bool,
    ) -> bool:
        if require_running_run and run.status is not OrchestrationRunStatus.RUNNING:
            return False
        if run.status in {
            OrchestrationRunStatus.COMPLETED,
            OrchestrationRunStatus.FAILED,
            OrchestrationRunStatus.CANCELLED,
        }:
            return False
        if self.run_dispatch_guard is None:
            return True
        return bool(self.run_dispatch_guard(run))

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

    @staticmethod
    def _execution_groups(
        prepared_batch: tuple[_PreparedToolExecution, ...],
    ) -> tuple[tuple[_PreparedToolExecution, ...], ...]:
        groups: list[tuple[_PreparedToolExecution, ...]] = []
        current: list[_PreparedToolExecution] = []
        for prepared in prepared_batch:
            if _is_terminal_plan_control_tool(prepared):
                if current:
                    groups.append(tuple(current))
                    current = []
                groups.append((prepared,))
                continue
            if current and any(
                _resource_policies_conflict(
                    prepared.resource_policy,
                    item.resource_policy,
                )
                for item in current
            ):
                groups.append(tuple(current))
                current = [prepared]
                continue
            current.append(prepared)
        if current:
            groups.append(tuple(current))
        return tuple(groups)

    @staticmethod
    def _resource_policy(
        resolved_tool: ResolvedTool,
        *,
        tool_call: ToolCallIntent,
        batch_context: _ToolExecutionBatchContext,
    ) -> _ToolResourcePolicy:
        policy = resolved_tool.tool.execution_policy
        resource_scope = _optional_context_text(policy.resource_scope)
        serial_group_key = _optional_context_text(policy.serial_group_key)
        execution_lane = (
            "serial"
            if serial_group_key is not None or not policy.supports_parallel
            else "parallel"
        )
        return _ToolResourcePolicy(
            supports_parallel=bool(policy.supports_parallel),
            mutates_state=bool(policy.mutates_state),
            execution_lane=execution_lane,
            resource_scope=resource_scope,
            resource_key=_resource_key(
                resource_scope,
                arguments=tool_call.arguments,
                context_attrs=batch_context.context_attrs,
                tool_id=resolved_tool.tool.id,
            ),
            serial_group_key=serial_group_key,
        )

    def _batch_context(
        self,
        run: OrchestrationRun,
        *,
        session_key: str,
        active_session_id: str,
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
        normalized_active_session_id = active_session_id.strip()
        if normalized_active_session_id:
            attrs["active_session_id"] = normalized_active_session_id
        trace_id = _optional_context_text(run.metadata.get("trace_id")) or run.id
        if trace_id:
            attrs["trace_id"] = trace_id
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

    @staticmethod
    def _tool_run_metadata(
        run: OrchestrationRun,
        *,
        session_key: str,
        active_session_id: str,
        prepared: _PreparedToolExecution,
        batch_context: _ToolExecutionBatchContext,
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
        workspace_dir = batch_context.context_attrs.get("workspace_dir")
        if isinstance(workspace_dir, str) and workspace_dir.strip():
            metadata["workspace_dir"] = workspace_dir
        resource_policy_payload = prepared.resource_policy.to_payload()
        if resource_policy_payload:
            metadata["tool_resource_policy"] = resource_policy_payload
        return metadata

    @staticmethod
    def _tool_run_link(
        prepared: _PreparedToolExecution,
        tool_run: ToolRun,
        *,
        background: bool,
    ) -> ToolRunLink:
        return ToolRunLink(
            tool_call_id=prepared.tool_call.id,
            tool_name=prepared.tool_call.name,
            tool_run_id=tool_run.id,
            tool_id=prepared.tool_id,
            status=tool_run.status.value,
            mode=prepared.target.mode.value,
            strategy=prepared.target.strategy.value,
            environment=prepared.target.environment.value,
            background=background,
            tool_lifecycle=_tool_lifecycle_from_tool_run(tool_run),
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
            require_running_run=False,
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

    @staticmethod
    def _terminal_plan_stops_remaining_batches(tool_run: ToolRun) -> bool:
        tool_result = tool_run.result
        if tool_result is None:
            return False
        if tool_result.metadata.get("terminal_plan") is not True:
            return False
        tool_name = tool_result.metadata.get("tool")
        if isinstance(tool_name, str) and tool_name.strip() != "context_tree.update_plan":
            return False
        return True

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


def _tool_lifecycle_from_tool_run(tool_run: ToolRun) -> dict[str, object]:
    payload: dict[str, object] = {}
    for source in _tool_lifecycle_sources(tool_run):
        for key in (
            "superseded",
            "superseded_by_tool_call_id",
            "replaced_by_tool_call_id",
            "replacement_tool_call_id",
            "supersedes_tool_call_id",
            "supersedes_tool_run_id",
            "supersedes_result_message_id",
            "lifecycle_status",
            "evidence_lifecycle_status",
            "evidence_lifecycle",
        ):
            if key in source:
                payload[key] = source[key]
    return payload


def _tool_lifecycle_sources(tool_run: ToolRun) -> tuple[dict[str, object], ...]:
    sources: list[dict[str, object]] = []
    if isinstance(tool_run.metadata, dict):
        sources.append(tool_run.metadata)
    result_payload = tool_run.result_payload
    if isinstance(result_payload, dict):
        for key in ("metadata", "details", "tool_lifecycle", "evidence_lifecycle"):
            value = result_payload.get(key)
            if isinstance(value, dict):
                sources.append(value)
        metadata = result_payload.get("metadata")
        if isinstance(metadata, dict):
            browser_evidence = metadata.get("browser_evidence")
            if isinstance(browser_evidence, dict):
                sources.append(browser_evidence)
    return tuple(sources)


def _is_terminal_plan_control_tool(prepared: _PreparedToolExecution) -> bool:
    return (
        prepared.tool_call.name == "context_tree.update_plan"
        or prepared.tool_id == "context_tree.update_plan"
    )


def _resource_policies_conflict(
    left: _ToolResourcePolicy,
    right: _ToolResourcePolicy,
) -> bool:
    if (
        left.execution_lane != "serial"
        and right.execution_lane != "serial"
        and left.supports_parallel
        and right.supports_parallel
    ):
        return False
    if left.resource_scope == "browser.target" and right.resource_scope == "browser.target":
        return _browser_target_resources_conflict(
            left.resource_key,
            right.resource_key,
        )
    if left.resource_key is not None and right.resource_key is not None:
        return left.resource_key == right.resource_key
    return True


def _resource_key(
    resource_scope: str | None,
    *,
    arguments: dict[str, object],
    context_attrs: dict[str, object],
    tool_id: str,
) -> str | None:
    if resource_scope is None:
        return None
    if resource_scope == "browser.target":
        return _browser_target_resource_key(arguments, context_attrs)
    return f"{resource_scope}:{tool_id}"


def _browser_target_resource_key(
    arguments: dict[str, object],
    context_attrs: dict[str, object],
) -> str:
    allocation = (
        _optional_context_text(arguments.get("allocation_id"))
        or _optional_context_text(arguments.get("lease_id"))
        or _optional_context_text(arguments.get("browser_allocation_id"))
        or _optional_context_text(context_attrs.get("browser_allocation_id"))
        or _optional_context_text(context_attrs.get("browser_lease_id"))
    )
    target = (
        _optional_context_text(arguments.get("target_id"))
        or _optional_context_text(arguments.get("targetId"))
        or _optional_context_text(context_attrs.get("browser_target_id"))
        or "*"
    )
    if allocation is not None:
        return f"browser.target:allocation={allocation};target={target}"
    profile = (
        _optional_context_text(arguments.get("profile"))
        or _optional_context_text(context_attrs.get("browser_profile"))
        or _optional_context_text(context_attrs.get("default_browser_profile"))
        or "*"
    )
    return f"browser.target:profile={profile};target={target}"


def _browser_target_resources_conflict(left_key: str | None, right_key: str | None) -> bool:
    left = _browser_target_resource_parts(left_key)
    right = _browser_target_resource_parts(right_key)
    if not left or not right:
        return True
    left_allocation = left.get("allocation")
    right_allocation = right.get("allocation")
    if left_allocation is not None or right_allocation is not None:
        if left_allocation is None or right_allocation is None:
            return True
        if left_allocation != right_allocation:
            return False
    else:
        left_profile = left.get("profile") or "*"
        right_profile = right.get("profile") or "*"
        if left_profile != "*" and right_profile != "*" and left_profile != right_profile:
            return False
    left_target = left.get("target") or "*"
    right_target = right.get("target") or "*"
    return left_target == "*" or right_target == "*" or left_target == right_target


def _browser_target_resource_parts(resource_key: str | None) -> dict[str, str]:
    if resource_key is None or not resource_key.startswith("browser.target:"):
        return {}
    parts: dict[str, str] = {}
    raw = resource_key.removeprefix("browser.target:")
    for item in raw.split(";"):
        key, separator, value = item.partition("=")
        if separator and key.strip() and value.strip():
            parts[key.strip()] = value.strip()
    return parts


def _record_tool_probe_observation(
    run: OrchestrationRun,
    *,
    tool_id: str,
    tool_call: ToolCallIntent,
) -> None:
    target = _normalized_probe_target(tool_id=tool_id, arguments=tool_call.arguments)
    if target is None:
        return
    payload = run.metadata.get("repeated_probe_observation")
    if not isinstance(payload, dict):
        payload = {
            "targets": {},
            "repeated": [],
            "repeated_count": 0,
        }
    targets = payload.get("targets")
    if not isinstance(targets, dict):
        targets = {}
    target_key = str(target["key"])
    entry = targets.get(target_key)
    next_step = _total_probe_count(targets) + 1
    if not isinstance(entry, dict):
        entry = {
            **target,
            "count": 0,
            "first_seen_step": next_step,
            "last_seen_step": next_step,
            "tool_call_ids": [],
        }
    count = int(entry.get("count") or 0) + 1
    entry["count"] = count
    entry["last_seen_step"] = next_step
    tool_call_ids = entry.get("tool_call_ids")
    if not isinstance(tool_call_ids, list):
        tool_call_ids = []
    if tool_call.id not in tool_call_ids:
        tool_call_ids.append(tool_call.id)
    entry["tool_call_ids"] = tool_call_ids[-8:]
    targets[target_key] = entry
    repeated_entries = [
        dict(value)
        for value in targets.values()
        if isinstance(value, dict) and int(value.get("count") or 0) >= 3
    ]
    repeated_entries.sort(
        key=lambda item: (
            -int(item.get("count") or 0),
            str(item.get("key") or ""),
        ),
    )
    payload["targets"] = targets
    payload["repeated"] = repeated_entries[:20]
    payload["repeated_count"] = len(repeated_entries)
    run.metadata["repeated_probe_observation"] = payload


def _normalized_probe_target(
    *,
    tool_id: str,
    arguments: dict[str, object],
) -> dict[str, object] | None:
    url = _first_text_argument(
        arguments,
        ("url", "href", "uri", "endpoint", "request_url", "requestUrl"),
    )
    if url is not None:
        url_target = _normalized_url_probe_target(tool_id=tool_id, value=url)
        if url_target is not None:
            return url_target
    command = _first_text_argument(arguments, ("command", "cmd"))
    if command is not None:
        fingerprint = _command_fingerprint(command)
        return {
            "key": f"{tool_id}:command:{fingerprint}",
            "kind": "command",
            "tool_id": tool_id,
            "command_fingerprint": fingerprint,
        }
    if arguments:
        fingerprint = _json_fingerprint(arguments)
        return {
            "key": f"{tool_id}:args:{fingerprint}",
            "kind": "arguments",
            "tool_id": tool_id,
            "argument_fingerprint": fingerprint,
        }
    return {
        "key": f"{tool_id}:no_args",
        "kind": "no_args",
        "tool_id": tool_id,
    }


def _normalized_url_probe_target(
    *,
    tool_id: str,
    value: str,
) -> dict[str, object] | None:
    normalized = value.strip()
    if not normalized:
        return None
    parsed = urlparse(normalized)
    domain = (parsed.netloc or "").lower()
    path = parsed.path or normalized
    if not domain and normalized.startswith("/"):
        path = normalized.split("?", 1)[0] or "/"
    elif not domain and "://" not in normalized:
        path = normalized.split("?", 1)[0] or normalized
    path = path or "/"
    key_target = f"{domain}{path}" if domain else path
    return {
        "key": f"{tool_id}:url:{key_target}",
        "kind": "url",
        "tool_id": tool_id,
        "domain": domain,
        "path": path,
        "normalized_url": key_target,
    }


def _first_text_argument(
    arguments: dict[str, object],
    keys: tuple[str, ...],
) -> str | None:
    for key in keys:
        value = arguments.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _command_fingerprint(command: str) -> str:
    normalized = " ".join(command.strip().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def _json_fingerprint(arguments: dict[str, object]) -> str:
    try:
        payload = json.dumps(arguments, ensure_ascii=True, sort_keys=True)
    except TypeError:
        payload = repr(sorted(arguments.items()))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _total_probe_count(targets: dict[object, object]) -> int:
    total = 0
    for value in targets.values():
        if isinstance(value, dict):
            total += int(value.get("count") or 0)
    return total


def _optional_context_text(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None
