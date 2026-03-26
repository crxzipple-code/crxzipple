from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from crxzipple.modules.llm.domain import ToolCallIntent
from crxzipple.modules.orchestration.application.engine_session_recorder import (
    OrchestrationSessionRecorder,
)
from crxzipple.modules.orchestration.application.ports import (
    MemoryPort,
    ToolExecutionPort,
)
from crxzipple.modules.orchestration.application.skill_requests import (
    is_skill_request_tool_name,
)
from crxzipple.modules.orchestration.application.tool_resolver import (
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
    ToolExecutionStrategy,
    ToolExecutionTarget,
    ToolMode,
    ToolRun,
    ToolRunStatus,
)


@dataclass(frozen=True, slots=True)
class ToolExecutionBatchOutcome:
    tool_call_message_ids: tuple[str, ...] = field(default_factory=tuple)
    inline_runs: tuple[tuple[str, ToolRun], ...] = field(default_factory=tuple)
    background_runs: tuple[tuple[ToolCallIntent, ToolRun], ...] = field(default_factory=tuple)
    pending_approval_request: PendingApprovalRequest | None = None


@dataclass(slots=True)
class OrchestrationEngineToolExecutor:
    session_recorder: OrchestrationSessionRecorder
    tool_resolver: ToolResolver
    tool_execution_port: ToolExecutionPort
    memory_port: MemoryPort | None = None

    def execute_tool_calls(
        self,
        run: OrchestrationRun,
        *,
        session_key: str,
        active_session_id: str,
        resolved_tools: ResolvedToolSet,
        tool_calls: tuple[ToolCallIntent, ...],
        append_tool_call_messages: bool,
    ) -> ToolExecutionBatchOutcome:
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
                    self.session_recorder.append_tool_call_messages(
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
            tool_run = asyncio.run(
                self.tool_execution_port.execute(
                    ExecuteToolInput(
                        tool_id=resolved_tool.tool.id,
                        arguments=self._execution_arguments(run, tool_call),
                        mode=resolved_tool.target.mode,
                        strategy=resolved_tool.target.strategy,
                        environment=resolved_tool.target.environment,
                    ),
                ),
            )
            if tool_run.status is ToolRunStatus.QUEUED:
                background_runs.append((tool_call, tool_run))
                continue
            message_id = self.session_recorder.append_tool_result_message(
                session_key=session_key,
                active_session_id=active_session_id,
                tool_call=tool_call,
                tool_run=tool_run,
                source_kind="tool_run",
                source_id=tool_run.id,
            )
            inline_runs.append((message_id, tool_run))
        return ToolExecutionBatchOutcome(
            tool_call_message_ids=tuple(tool_call_message_ids),
            inline_runs=tuple(inline_runs),
            background_runs=tuple(background_runs),
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

    def _execution_arguments(
        self,
        run: OrchestrationRun,
        tool_call: ToolCallIntent,
    ) -> dict[str, object]:
        execution_arguments = dict(tool_call.arguments)
        if self.memory_port is None or not self.memory_port.is_memory_tool_name(
            tool_call.name,
        ):
            return execution_arguments
        if run.agent_id is None or not run.agent_id.strip():
            raise OrchestrationValidationError(
                "Memory lookup tools require run.agent_id.",
            )
        return self.memory_port.inject_tool_context(
            execution_arguments,
            agent_id=run.agent_id,
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
