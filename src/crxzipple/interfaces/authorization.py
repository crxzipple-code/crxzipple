from __future__ import annotations

from crxzipple.bootstrap import AppContainer
from crxzipple.modules.authorization.domain import (
    AuthorizationContext,
    AuthorizationRequest,
    AuthorizationResource,
    AuthorizationSubject,
)
from crxzipple.modules.llm.domain import LlmProfile
from crxzipple.modules.tool.domain import (
    Tool,
    ToolEnvironment,
    ToolExecutionStrategy,
    ToolMode,
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
) -> None:
    tool = container.tool_service.get_tool(tool_id)
    request = AuthorizationRequest(
        subject=subject or AuthorizationSubject(type="interface", id=interface_name),
        action="tool.run",
        resource=_tool_resource(tool, mode=mode, strategy=strategy, environment=environment),
        context=context or AuthorizationContext(attrs={"interface": interface_name}),
    )
    container.authorization_service.authorize(request)


def authorize_llm_action(
    container: AppContainer,
    *,
    llm_id: str,
    action: str,
    interface_name: str,
    subject: AuthorizationSubject | None = None,
    context: AuthorizationContext | None = None,
) -> None:
    profile = container.llm_service.get_profile(llm_id)
    request = AuthorizationRequest(
        subject=subject or AuthorizationSubject(type="interface", id=interface_name),
        action=action,
        resource=_llm_resource(profile),
        context=context or AuthorizationContext(attrs={"interface": interface_name}),
    )
    container.authorization_service.authorize(request)


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
            "mode": mode.value,
            "strategy": strategy.value,
            "environment": environment.value,
            "tags": list(tool.tags),
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
