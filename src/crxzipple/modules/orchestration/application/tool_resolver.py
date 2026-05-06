from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from crxzipple.modules.access import AccessRequirementReadiness
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
    AccessReadinessPort,
    AuthorizationPort,
    ToolCatalogPort,
)
from crxzipple.modules.orchestration.application.prompting import (
    PromptMode,
    resolve_run_surface_policy,
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
class BlockedToolAccess:
    tool_id: str
    tool_name: str
    requirement_sets: tuple[tuple[AccessRequirementReadiness, ...], ...]

    def to_payload(self) -> dict[str, object]:
        set_payloads = tuple(
            {
                "ready": all(readiness.ready for readiness in requirement_set),
                "checks": [
                    readiness.to_payload()
                    for readiness in requirement_set
                ],
            }
            for requirement_set in self.requirement_sets
        )
        missing_checks = [
            readiness
            for requirement_set in self.requirement_sets
            for readiness in requirement_set
            if not readiness.ready
        ]
        return {
            "resource_type": "tool",
            "resource_id": self.tool_id,
            "display_name": self.tool_name,
            "ready": False,
            "setup_available": any(
                readiness.setup_available for readiness in missing_checks
            ),
            "requirement_sets": list(set_payloads),
        }


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
    blocked_access: tuple[BlockedToolAccess, ...] = ()

    @property
    def schemas(self) -> tuple[ToolSchema, ...]:
        return tuple(item.schema for item in self.tools)

    def by_name(self, name: str) -> ResolvedTool | None:
        for item in self.tools:
            if item.tool.id == name or item.schema.name == name:
                return item
        return None

    def blocked_access_by_name(self, name: str) -> BlockedToolAccess | None:
        for item in self.blocked_access:
            if item.tool_id == name:
                return item
        return None


@dataclass(slots=True)
class ToolResolver:
    tool_catalog: ToolCatalogPort
    authorization_port: AuthorizationPort
    access_port: AccessReadinessPort | None = None
    run_context_provider: Callable[[OrchestrationRun], dict[str, object]] | None = None
    default_remote_ask_effect_id: str = field(default="remote_tool_access")
    default_background_effect_id: str = field(default="background_execution")
    default_mutation_effect_id: str = field(default="state_mutation")
    default_confirmation_effect_id: str = field(default="sensitive_access")

    def resolve(self, run: OrchestrationRun) -> ResolvedToolSet:
        self.tool_catalog.ensure_local_system_tools_registered()
        context_attrs = self._context_attrs(run)
        resolved: list[ResolvedTool] = []
        blocked_access: list[BlockedToolAccess] = []
        for tool in self.tool_catalog.list_enabled_tools():
            target = self._preferred_target(tool)
            resource_attrs = self._resource_attrs(tool, target=target)
            if self._surface_is_blocked(
                run,
                tool=tool,
                target=target,
                context_attrs=context_attrs,
                resource_attrs=resource_attrs,
            ):
                continue
            access_block = self._access_block_for_tool(
                tool,
                context_attrs=context_attrs,
            )
            if access_block is not None:
                blocked_access.append(access_block)
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
            blocked_access=tuple(blocked_access),
        )

    def invocation_context_attrs(
        self,
        run: OrchestrationRun,
        *,
        session_key: str | None = None,
    ) -> dict[str, Any]:
        return self._context_attrs(run, session_key=session_key)

    def resource_attrs(
        self,
        tool: Tool,
        *,
        target: ToolExecutionTarget,
    ) -> dict[str, Any]:
        return self._resource_attrs(tool, target=target)

    def execution_decision(
        self,
        run: OrchestrationRun,
        *,
        tool: Tool,
        target: ToolExecutionTarget,
        context_attrs: dict[str, Any] | None = None,
        resource_attrs: dict[str, Any] | None = None,
    ) -> ToolExecutionDecision:
        resolved_resource_attrs = (
            resource_attrs
            if resource_attrs is not None
            else self._resource_attrs(tool, target=target)
        )
        resolved_context_attrs = (
            context_attrs
            if context_attrs is not None
            else self._context_attrs(
                run,
                session_key=str(run.metadata.get("session_key", "")).strip(),
            )
        )
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
                    attrs=resolved_resource_attrs,
                ),
                context=AuthorizationContext(
                    attrs=resolved_context_attrs,
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
        context_attrs: dict[str, Any],
        resource_attrs: dict[str, Any],
    ) -> bool:
        tool_access_decision = self._tool_access_override_decision(
            run,
            tool=tool,
            target=target,
            context_attrs=context_attrs,
            resource_attrs=resource_attrs,
        )
        if tool_access_decision == "deny":
            return True
        if (
            self._tool_run_override_decision(
                run,
                tool=tool,
                target=target,
                context_attrs=context_attrs,
                resource_attrs=resource_attrs,
            )
            == "deny"
        ):
            return True
        if self._has_explicit_effect_deny(
            run,
            tool=tool,
            target=target,
            context_attrs=context_attrs,
            resource_attrs=resource_attrs,
        ):
            return True
        return False

    def _access_block_for_tool(
        self,
        tool: Tool,
        *,
        context_attrs: dict[str, Any],
    ) -> BlockedToolAccess | None:
        if self.access_port is None:
            return None
        requirement_sets = tool.access_requirement_sets
        if not requirement_sets:
            return None
        workspace_dir_value = context_attrs.get("workspace_dir")
        workspace_dir = (
            workspace_dir_value.strip()
            if isinstance(workspace_dir_value, str) and workspace_dir_value.strip()
            else None
        )
        checked_sets: list[tuple[AccessRequirementReadiness, ...]] = []
        for requirement_set in requirement_sets:
            if not requirement_set:
                return None
            readiness = self.access_port.check_requirements(
                requirement_set,
                workspace_dir=workspace_dir,
            )
            checked_sets.append(tuple(readiness))
            if readiness and all(item.ready for item in readiness):
                return None
        return BlockedToolAccess(
            tool_id=tool.id,
            tool_name=tool.name,
            requirement_sets=tuple(checked_sets),
        )

    def _has_explicit_effect_deny(
        self,
        run: OrchestrationRun,
        *,
        tool: Tool,
        target: ToolExecutionTarget,
        context_attrs: dict[str, Any],
        resource_attrs: dict[str, Any],
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
                    context_attrs=context_attrs,
                    resource_attrs=resource_attrs,
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
        context_attrs: dict[str, Any],
        resource_attrs: dict[str, Any],
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
                    attrs=resource_attrs,
                ),
                context=AuthorizationContext(
                    attrs=context_attrs,
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
        context_attrs: dict[str, Any],
        resource_attrs: dict[str, Any],
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
                    attrs=resource_attrs,
                ),
                context=AuthorizationContext(
                    attrs={
                        **context_attrs,
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
        context_attrs: dict[str, Any],
        resource_attrs: dict[str, Any],
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
                    attrs=resource_attrs,
                ),
                context=AuthorizationContext(
                    attrs=context_attrs,
                ),
            ),
        )
        return self._decision_mode(decision)

    def _context_attrs(
        self,
        run: OrchestrationRun,
        *,
        session_key: str | None = None,
    ) -> dict[str, Any]:
        prompt_mode = self._prompt_mode(run)
        surface_policy = resolve_run_surface_policy(prompt_mode)
        attrs: dict[str, Any] = {
            "interface": run.inbound_instruction.source,
            "run_id": run.id,
            "agent_id": run.agent_id,
            "prompt_mode": prompt_mode.value,
            "run_mode": prompt_mode.value,
            "surface": surface_policy.surface,
            "surface_contract": surface_policy.surface_contract,
        }
        normalized_session_key = (session_key or "").strip()
        if normalized_session_key:
            attrs["session_key"] = normalized_session_key
        if self.run_context_provider is not None:
            attrs.update(self.run_context_provider(run))
        return attrs

    def _resource_attrs(
        self,
        tool: Tool,
        *,
        target: ToolExecutionTarget,
    ) -> dict[str, Any]:
        attrs: dict[str, Any] = {
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
                item.value for item in tool.execution_support.supported_strategies
            ],
            "supported_environments": [
                item.value for item in tool.execution_support.supported_environments
            ],
            "required_effect_ids": list(tool.required_effect_ids),
            "authorization_effect_ids": list(
                self._authorization_effect_ids(tool, target=target),
            ),
            "mode": target.mode.value,
            "strategy": target.strategy.value,
            "environment": target.environment.value,
            "tags": list(tool.tags),
        }
        scope_required = self._tag_value(tool.tags, "scope:")
        surface_modes = self._tag_values(tool.tags, "surface:")
        if scope_required is not None:
            attrs["scope_required"] = scope_required
        if surface_modes:
            attrs["supported_surfaces"] = list(surface_modes)
            attrs["surface_mode"] = surface_modes[0]
        return attrs

    @staticmethod
    def _prompt_mode(run: OrchestrationRun) -> PromptMode:
        prompt_flow_hint = run.metadata.get("prompt_flow_hint")
        if isinstance(prompt_flow_hint, dict):
            mode = prompt_flow_hint.get("mode")
            if isinstance(mode, str) and mode.strip():
                return ToolResolver._coerce_prompt_mode(mode)
        raw_mode = run.metadata.get("prompt_mode")
        if isinstance(raw_mode, str) and raw_mode.strip():
            return ToolResolver._coerce_prompt_mode(raw_mode)
        return PromptMode.NORMAL_TURN

    @staticmethod
    def _coerce_prompt_mode(raw_mode: str) -> PromptMode:
        normalized = raw_mode.strip().lower()
        try:
            return PromptMode(normalized)
        except ValueError:
            return PromptMode.NORMAL_TURN

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
    def _tag_value(tags: tuple[str, ...], prefix: str) -> str | None:
        for tag in tags:
            if tag.startswith(prefix):
                value = tag.removeprefix(prefix).strip()
                if value:
                    return value
        return None

    @staticmethod
    def _tag_values(tags: tuple[str, ...], prefix: str) -> tuple[str, ...]:
        values: list[str] = []
        for tag in tags:
            if not tag.startswith(prefix):
                continue
            value = tag.removeprefix(prefix).strip()
            if value:
                values.append(value)
        return tuple(dict.fromkeys(values))

    @staticmethod
    def _build_schema(tool: Tool) -> ToolSchema:
        properties: dict[str, object] = {}
        required: list[str] = []
        for parameter in tool.parameters:
            schema = ToolResolver._parameter_schema(parameter.data_type)
            schema["description"] = parameter.description
            properties[parameter.name] = schema
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

    @staticmethod
    def _parameter_schema(data_type: str) -> dict[str, object]:
        normalized = data_type.strip().lower()
        if normalized.startswith("array[") and normalized.endswith("]"):
            item_type = normalized[6:-1].strip() or "string"
            return {
                "type": "array",
                "items": ToolResolver._parameter_schema(item_type),
            }
        if normalized == "array":
            return {
                "type": "array",
                "items": {"type": "string"},
            }
        if normalized in {"string", "integer", "number", "boolean", "object", "null"}:
            return {"type": normalized}
        return {"type": "string"}
