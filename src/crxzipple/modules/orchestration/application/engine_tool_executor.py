from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, field

from crxzipple.modules.llm.domain import ToolCallIntent
from crxzipple.modules.orchestration.application.engine_session_recorder import (
    OrchestrationSessionRecorder,
)
from crxzipple.modules.orchestration.application.tool_execution_batch_runner import (
    ToolExecutionBatchRunner,
)
from crxzipple.modules.orchestration.application.tool_execution_records import (
    ToolExecutionBatchOutcome,
)
from crxzipple.modules.orchestration.application.ports import (
    ToolExecutionPort,
)
from crxzipple.modules.orchestration.application.tool_resolver import (
    ResolvedToolSet,
    ToolResolver,
)
from crxzipple.modules.orchestration.application.tool_probe_observation import (
    RunMetadataToolProbeObservationRecorder,
    ToolProbeObservationPort,
)
from crxzipple.modules.orchestration.domain import (
    OrchestrationRun,
    OrchestrationValidationError,
    PendingApprovalRequest,
)
from crxzipple.modules.tool.domain import (
    ToolEnvironment,
    ToolExecutionStrategy,
    ToolExecutionTarget,
    ToolMode,
)
from crxzipple.shared.runtime_metrics import (
    RuntimeMetricsRegistry,
    get_runtime_metrics_registry,
)


@dataclass(slots=True)
class OrchestrationEngineToolExecutor:
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

    def execute_tool_calls(
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
                    append_tool_call_session_items=append_tool_call_session_items,
                    tool_call_session_item_ids_by_call_id=(
                        tool_call_session_item_ids_by_call_id
                    ),
                    append_tool_result_messages=append_tool_result_messages,
                    invocation_id=invocation_id,
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
        append_tool_call_session_items: bool = False,
        tool_call_session_item_ids_by_call_id: dict[str, str] | None = None,
        append_tool_result_messages: bool = True,
        invocation_id: str | None = None,
        extra_context_attrs: dict[str, object] | None = None,
        require_running_run: bool = True,
    ) -> ToolExecutionBatchOutcome:
        return await ToolExecutionBatchRunner(
            session_recorder=self.session_recorder,
            tool_resolver=self.tool_resolver,
            tool_execution_port=self.tool_execution_port,
            run_dispatch_guard=self.run_dispatch_guard,
            probe_observation_recorder=self.probe_observation_recorder,
            detailed_phase_metrics_enabled=self.detailed_phase_metrics_enabled,
            metrics=self.metrics,
        ).execute(
            run,
            session_key=session_key,
            active_session_id=active_session_id,
            resolved_tools=resolved_tools,
            tool_calls=tool_calls,
            append_tool_call_messages=append_tool_call_messages,
            append_tool_call_session_items=append_tool_call_session_items,
            tool_call_session_item_ids_by_call_id=(
                tool_call_session_item_ids_by_call_id
            ),
            append_tool_result_messages=append_tool_result_messages,
            invocation_id=invocation_id,
            extra_context_attrs=extra_context_attrs,
            require_running_run=require_running_run,
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
            append_tool_call_session_items=True,
            require_running_run=False,
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
