from __future__ import annotations

from dataclasses import dataclass

from crxzipple.modules.authorization.application import AuthorizationApplicationService
from crxzipple.modules.authorization.domain import (
    AuthorizationContext,
    AuthorizationRequest,
    AuthorizationResource,
    AuthorizationSubject,
)
from crxzipple.modules.llm.domain import ToolSchema
from crxzipple.modules.orchestration.domain import OrchestrationRun
from crxzipple.modules.tool.application import ToolApplicationService
from crxzipple.modules.tool.domain import (
    Tool,
    ToolEnvironment,
    ToolExecutionStrategy,
    ToolExecutionTarget,
    ToolMode,
)


@dataclass(frozen=True, slots=True)
class ResolvedTool:
    tool: Tool
    schema: ToolSchema
    target: ToolExecutionTarget


@dataclass(frozen=True, slots=True)
class ResolvedToolSet:
    tools: tuple[ResolvedTool, ...]

    @property
    def schemas(self) -> tuple[ToolSchema, ...]:
        return tuple(item.schema for item in self.tools)

    def by_name(self, name: str) -> ResolvedTool | None:
        for item in self.tools:
            if item.tool.id == name:
                return item
        return None


@dataclass(slots=True)
class ToolResolver:
    tool_service: ToolApplicationService
    authorization_service: AuthorizationApplicationService

    def resolve(self, run: OrchestrationRun) -> ResolvedToolSet:
        resolved: list[ResolvedTool] = []
        for tool in self.tool_service.list_enabled_tools():
            if tool.execution_policy.requires_confirmation:
                continue
            target = self._preferred_target(tool)
            if not self._is_authorized(run, tool=tool, target=target):
                continue
            resolved.append(
                ResolvedTool(
                    tool=tool,
                    schema=self._build_schema(tool),
                    target=target,
                ),
            )
        return ResolvedToolSet(tools=tuple(resolved))

    @staticmethod
    def _preferred_target(tool: Tool) -> ToolExecutionTarget:
        supported = tool.execution_support
        mode = (
            ToolMode.INLINE
            if ToolMode.INLINE in supported.supported_modes
            else supported.supported_modes[0]
        )
        strategy = (
            ToolExecutionStrategy.ASYNC
            if ToolExecutionStrategy.ASYNC in supported.supported_strategies
            else supported.supported_strategies[0]
        )
        environment = (
            ToolEnvironment.LOCAL
            if ToolEnvironment.LOCAL in supported.supported_environments
            else supported.supported_environments[0]
        )
        return ToolExecutionTarget(
            mode=mode,
            strategy=strategy,
            environment=environment,
        )

    def _is_authorized(
        self,
        run: OrchestrationRun,
        *,
        tool: Tool,
        target: ToolExecutionTarget,
    ) -> bool:
        decision = self.authorization_service.check(
            AuthorizationRequest(
                subject=AuthorizationSubject(
                    type="interface",
                    id=run.inbound_instruction.source,
                    attrs={"run_id": run.id},
                ),
                action="tool.run",
                resource=AuthorizationResource(
                    kind="tool",
                    id=tool.id,
                    attrs={
                        "tool_kind": tool.kind.value,
                        "source_kind": tool.source_kind.value,
                        "runtime_key": tool.runtime_key,
                        "enabled": tool.enabled,
                        "requires_confirmation": tool.execution_policy.requires_confirmation,
                        "mutates_state": tool.execution_policy.mutates_state,
                        "supported_modes": [
                            item.value for item in tool.execution_support.supported_modes
                        ],
                        "supported_strategies": [
                            item.value
                            for item in tool.execution_support.supported_strategies
                        ],
                        "supported_environments": [
                            item.value
                            for item in tool.execution_support.supported_environments
                        ],
                        "mode": target.mode.value,
                        "strategy": target.strategy.value,
                        "environment": target.environment.value,
                        "tags": list(tool.tags),
                    },
                ),
                context=AuthorizationContext(
                    attrs={
                        "interface": run.inbound_instruction.source,
                        "run_id": run.id,
                        "agent_id": run.agent_id,
                    },
                ),
            ),
        )
        return decision.allowed

    @staticmethod
    def _build_schema(tool: Tool) -> ToolSchema:
        properties: dict[str, object] = {}
        required: list[str] = []
        for parameter in tool.parameters:
            properties[parameter.name] = {
                "type": parameter.data_type,
                "description": parameter.description,
            }
            if parameter.required:
                required.append(parameter.name)
        input_schema: dict[str, object] = {
            "type": "object",
            "properties": properties,
            "additionalProperties": True,
        }
        if required:
            input_schema["required"] = required
        return ToolSchema(
            name=tool.id,
            description=tool.description,
            input_schema=input_schema,
        )
