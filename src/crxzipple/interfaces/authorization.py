from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from crxzipple.interfaces.runtime_container import AppContainer, AppKey
from crxzipple.modules.authorization.domain import (
    AuthorizationContext,
    AuthorizationRequest,
    AuthorizationResource,
    AuthorizationSubject,
)
from crxzipple.modules.llm.domain import LlmProfile
from crxzipple.modules.tool.application.authorization_context import (
    tool_invocation_authorization_context_attrs,
)
from crxzipple.modules.tool.domain import (
    Tool,
    ToolEnvironment,
    ToolExecutionStrategy,
    ToolMode,
    ToolNotFoundError,
)


def authorize_tool_run(
    container: AppContainer,
    *,
    tool_id: str,
    mode: ToolMode,
    strategy: ToolExecutionStrategy,
    environment: ToolEnvironment,
    interface_name: str,
    subject: AuthorizationSubject | None = None,
    context: AuthorizationContext | None = None,
    arguments: Mapping[str, Any] | None = None,
) -> None:
    try:
        tool = container.require(AppKey.TOOL_QUERY_SERVICE).get_tool(tool_id)
    except ToolNotFoundError:
        return
    context_attrs = dict(context.attrs) if context is not None else {}
    context_attrs.setdefault("interface", interface_name)
    context_attrs = tool_invocation_authorization_context_attrs(
        tool,
        base_attrs=context_attrs,
        arguments=arguments,
    )
    request = AuthorizationRequest(
        subject=subject or AuthorizationSubject(type="interface", id=interface_name),
        action="tool.run",
        resource=_tool_resource(tool, mode=mode, strategy=strategy, environment=environment),
        context=AuthorizationContext(attrs=context_attrs),
    )
    container.require(AppKey.AUTHORIZATION_SERVICE).authorize(request)


def authorize_llm_action(
    container: AppContainer,
    *,
    llm_id: str,
    action: str,
    interface_name: str,
    subject: AuthorizationSubject | None = None,
    context: AuthorizationContext | None = None,
) -> None:
    profile = container.require(AppKey.LLM_SERVICE).get_profile(llm_id)
    request = AuthorizationRequest(
        subject=subject or AuthorizationSubject(type="interface", id=interface_name),
        action=action,
        resource=_llm_resource(profile),
        context=context or AuthorizationContext(attrs={"interface": interface_name}),
    )
    container.require(AppKey.AUTHORIZATION_SERVICE).authorize(request)


def _tool_resource(
    tool: Tool,
    *,
    mode: ToolMode,
    strategy: ToolExecutionStrategy,
    environment: ToolEnvironment,
) -> AuthorizationResource:
    return AuthorizationResource(
        kind="tool",
        id=tool.id,
        attrs={
            "tool_kind": tool.kind.value,
            "definition_origin": tool.definition_origin.value,
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
            "mode": mode.value,
            "strategy": strategy.value,
            "environment": environment.value,
            "tags": list(tool.tags),
            "source_id": tool.source_id,
            "capability_ids": list(tool.capability_ids),
            "required_effect_ids": list(tool.required_effect_ids),
            "authorization_effect_ids": list(tool.required_effect_ids),
        },
    )


def _llm_resource(profile: LlmProfile) -> AuthorizationResource:
    return AuthorizationResource(
        kind="llm_profile",
        id=profile.id,
        attrs={
            "provider": profile.provider.value,
            "api_family": profile.api_family.value,
            "model_name": profile.model_name,
            "model_family": profile.model_family.value,
            "capabilities": [item.value for item in profile.capabilities],
            "enabled": profile.enabled,
            "source_kind": profile.source_kind.value,
        },
    )
