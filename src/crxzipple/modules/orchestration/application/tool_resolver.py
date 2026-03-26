from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from crxzipple.modules.authorization.domain import (
    AuthorizationContext,
    AuthorizationDecision,
    AuthorizationRequest,
    AuthorizationResource,
    AuthorizationSubject,
    ToolExecutionAuthorizationRequest,
)
from crxzipple.modules.llm.domain import ToolSchema
from crxzipple.modules.orchestration.application.ports import (
    AuthorizationPort,
    ToolCatalogPort,
)
from crxzipple.modules.orchestration.domain import OrchestrationRun
from crxzipple.modules.tool.domain import (
    Tool,
    ToolEnvironment,
    ToolExecutionStrategy,
    ToolExecutionTarget,
    ToolMode,
)
from crxzipple.shared.domain.effects import get_effect_descriptor


@dataclass(frozen=True, slots=True)
class ResolvedTool:
    tool: Tool
    schema: ToolSchema
    target: ToolExecutionTarget


@dataclass(frozen=True, slots=True)
class AskableEffect:
    id: str
    label: str
    description: str
    tool_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ToolExecutionDecision:
    mode: str
    approval: AskableEffect | None = None


@dataclass(frozen=True, slots=True)
class ResolvedToolSet:
    tools: tuple[ResolvedTool, ...]

    @property
    def schemas(self) -> tuple[ToolSchema, ...]:
        return tuple(item.schema for item in self.tools)

    def by_name(self, name: str) -> ResolvedTool | None:
        for item in self.tools:
            if item.tool.id == name or item.schema.name == name:
                return item
        return None


@dataclass(slots=True)
class ToolResolver:
    tool_catalog: ToolCatalogPort
    authorization_port: AuthorizationPort
    tool_availability_filter: Callable[[OrchestrationRun, Tool], bool] | None = None
    default_remote_ask_effect_id: str = field(default="remote_tool_access")
    default_background_effect_id: str = field(default="background_execution")
    default_mutation_effect_id: str = field(default="state_mutation")
    default_confirmation_effect_id: str = field(default="sensitive_access")

    def resolve(self, run: OrchestrationRun) -> ResolvedToolSet:
        self.tool_catalog.ensure_local_system_tools_registered()
        resolved: list[ResolvedTool] = []
        for tool in self.tool_catalog.list_enabled_tools():
            if self.tool_availability_filter is not None and not self.tool_availability_filter(
                run,
                tool,
            ):
                continue
            target = self._preferred_target(tool)
            if self._surface_is_blocked(run, tool=tool, target=target):
                continue
            resolved.append(
                ResolvedTool(
                    tool=tool,
                    schema=self._build_schema(tool),
                    target=target,
                ),
            )
        return ResolvedToolSet(
            tools=tuple(resolved),
        )

    def execution_decision(
        self,
        run: OrchestrationRun,
        *,
        tool: Tool,
        target: ToolExecutionTarget,
    ) -> ToolExecutionDecision:
        authorization_effect_ids = self._authorization_effect_ids(tool, target=target)
        decision = self.authorization_port.check_tool_execution(
            ToolExecutionAuthorizationRequest(
                subject=AuthorizationSubject(
                    type="interface",
                    id=run.inbound_instruction.source,
                    attrs={"run_id": run.id},
                ),
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
                        "required_effect_ids": list(tool.required_effect_ids),
                        "authorization_effect_ids": list(authorization_effect_ids),
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
                        "session_key": str(run.metadata.get("session_key", "")).strip(),
                        "agent_id": run.agent_id,
                        "prompt_mode": self._prompt_mode(run),
                    },
                ),
                required_effect_ids=authorization_effect_ids,
            ),
        )
        if decision.allowed:
            return ToolExecutionDecision(mode="allow")
        if decision.code.value == "approval_required":
            missing_effect_ids = tuple(
                effect_id
                for effect_id in decision.details.get("missing_effect_ids", [])
                if isinstance(effect_id, str) and effect_id.strip()
            )
            askable = self._askable_effect(effect_ids=missing_effect_ids, tool=tool)
            if askable is None:
                return ToolExecutionDecision(mode="blocked")
            return ToolExecutionDecision(
                mode="approval_required",
                approval=askable,
            )
        return ToolExecutionDecision(mode="blocked")

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

    def _surface_is_blocked(
        self,
        run: OrchestrationRun,
        *,
        tool: Tool,
        target: ToolExecutionTarget,
    ) -> bool:
        tool_access_decision = self._tool_access_override_decision(
            run,
            tool=tool,
            target=target,
        )
        if tool_access_decision == "deny":
            return True
        if self._tool_run_override_decision(run, tool=tool, target=target) == "deny":
            return True
        if self._has_explicit_effect_deny(
            run,
            tool=tool,
            target=target,
        ):
            return True
        return False

    def _has_explicit_effect_deny(
        self,
        run: OrchestrationRun,
        *,
        tool: Tool,
        target: ToolExecutionTarget,
    ) -> bool:
        effect_ids = list(tool.required_effect_ids)
        if tool.execution_policy.requires_confirmation:
            effect_ids.append(self.default_confirmation_effect_id)
        if not tool.required_effect_ids and tool.execution_policy.mutates_state:
            effect_ids.append(self.default_mutation_effect_id)
        if target.mode == ToolMode.BACKGROUND:
            effect_ids.append(self.default_background_effect_id)
        if not tool.required_effect_ids and target.environment is ToolEnvironment.REMOTE:
            effect_ids.append(self.default_remote_ask_effect_id)
        for effect_id in dict.fromkeys(effect_ids):
            if (
                self._effect_access_override_decision(
                    run,
                    tool=tool,
                    target=target,
                    effect_id=effect_id,
                )
                == "deny"
            ):
                return True
        return False

    @staticmethod
    def _askable_effect(
        *,
        effect_ids: tuple[str, ...],
        tool: Tool,
    ) -> AskableEffect | None:
        if not effect_ids:
            return None
        primary = get_effect_descriptor(effect_ids[0])
        return AskableEffect(
            id=primary.id,
            label=primary.label,
            description=primary.description,
            tool_ids=(tool.id,),
        )

    def _tool_run_override_decision(
        self,
        run: OrchestrationRun,
        *,
        tool: Tool,
        target: ToolExecutionTarget,
    ) -> str:
        if not self.authorization_port.is_enabled():
            return "no_match"
        decision = self._check_authorization(
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
                        "required_effect_ids": list(tool.required_effect_ids),
                        "authorization_effect_ids": list(
                            self._authorization_effect_ids(tool, target=target),
                        ),
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
                        "prompt_mode": self._prompt_mode(run),
                    },
                ),
            ),
        )
        return self._decision_mode(decision)

    def _effect_access_override_decision(
        self,
        run: OrchestrationRun,
        *,
        tool: Tool,
        target: ToolExecutionTarget,
        effect_id: str,
    ) -> str:
        if not self.authorization_port.is_enabled():
            return "no_match"
        decision = self._check_authorization(
            AuthorizationRequest(
                subject=AuthorizationSubject(
                    type="interface",
                    id=run.inbound_instruction.source,
                    attrs={"run_id": run.id},
                ),
                action="tool.access_effect",
                resource=AuthorizationResource(
                    kind="tool",
                    id=tool.id,
                    attrs={
                        "authorization_effect_ids": list(
                            self._authorization_effect_ids(tool, target=target),
                        ),
                        "required_effect_ids": list(tool.required_effect_ids),
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
                        "prompt_mode": self._prompt_mode(run),
                        "requested_effect_id": effect_id,
                    },
                ),
            ),
        )
        return self._decision_mode(decision)

    def _tool_access_override_decision(
        self,
        run: OrchestrationRun,
        *,
        tool: Tool,
        target: ToolExecutionTarget,
    ) -> str:
        if not self.authorization_port.is_enabled():
            return "no_match"
        decision = self._check_authorization(
            AuthorizationRequest(
                subject=AuthorizationSubject(
                    type="interface",
                    id=run.inbound_instruction.source,
                    attrs={"run_id": run.id},
                ),
                action="tool.access_tool",
                resource=AuthorizationResource(
                    kind="tool",
                    id=tool.id,
                    attrs={
                        "authorization_effect_ids": list(
                            self._authorization_effect_ids(tool, target=target),
                        ),
                        "required_effect_ids": list(tool.required_effect_ids),
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
                        "prompt_mode": self._prompt_mode(run),
                    },
                ),
            ),
        )
        return self._decision_mode(decision)

    @staticmethod
    def _prompt_mode(run: OrchestrationRun) -> str:
        prompt_flow_hint = run.metadata.get("prompt_flow_hint")
        if isinstance(prompt_flow_hint, dict):
            mode = prompt_flow_hint.get("mode")
            if isinstance(mode, str) and mode.strip():
                return mode.strip().lower()
        raw_mode = run.metadata.get("prompt_mode")
        if isinstance(raw_mode, str) and raw_mode.strip():
            return raw_mode.strip().lower()
        return "normal_turn"

    def _check_authorization(
        self,
        request: AuthorizationRequest,
    ) -> AuthorizationDecision:
        return self.authorization_port.check(request)

    @staticmethod
    def _decision_mode(decision: AuthorizationDecision) -> str:
        if decision.allowed:
            return "allow"
        if decision.matched_policy_ids:
            return "deny"
        return "no_match"

    def _authorization_effect_ids(
        self,
        tool: Tool,
        *,
        target: ToolExecutionTarget,
    ) -> tuple[str, ...]:
        effect_ids: list[str] = list(tool.required_effect_ids)
        if tool.execution_policy.requires_confirmation:
            effect_ids.append(self.default_confirmation_effect_id)
        if tool.execution_policy.mutates_state:
            effect_ids.append(self.default_mutation_effect_id)
        if target.mode == ToolMode.BACKGROUND:
            effect_ids.append(self.default_background_effect_id)
        if not tool.required_effect_ids and target.environment is ToolEnvironment.REMOTE:
            effect_ids.append(self.default_remote_ask_effect_id)
        return tuple(dict.fromkeys(effect_id for effect_id in effect_ids if effect_id))

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
