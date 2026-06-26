from __future__ import annotations

from typing import Any, Protocol

from crxzipple.modules.agent.application.resolution_access import (
    resolve_access_grants,
)
from crxzipple.modules.agent.application.resolution_authorization_query import (
    resolve_authorization_grants,
)
from crxzipple.modules.agent.application.resolution_llm import (
    resolve_llm_routes,
)
from crxzipple.modules.agent.application.resolution_models import (
    AgentProfileResolution,
    AgentResolutionSummary,
    AgentResolutionTrace,
    AgentValidationIssue,
)
from crxzipple.modules.agent.application.resolution_tools import (
    resolve_tools,
)


class AgentProfileQueryPort(Protocol):
    def get_profile(self, profile_id: str) -> Any: ...


class LlmProfileQueryPort(Protocol):
    def list_profiles(self) -> list[Any]: ...


class ToolCatalogQueryPort(Protocol):
    def list_tools(self) -> list[Any]: ...


class AccessReadinessQueryPort(Protocol):
    def check_requirement(
        self,
        requirement: str,
        *,
        workspace_dir: str | None = None,
    ) -> Any: ...

    def check_credential_binding(
        self,
        binding: str,
        *,
        workspace_dir: str | None = None,
        allow_literal: bool = False,
    ) -> Any: ...


class AuthorizationPolicyQueryPort(Protocol):
    def list_policies(self) -> list[Any]: ...


class AgentProfileResolutionQueryService:
    def __init__(
        self,
        *,
        agent_profiles: AgentProfileQueryPort,
        llm_profiles: LlmProfileQueryPort | None = None,
        tool_catalog: ToolCatalogQueryPort | None = None,
        access_readiness: AccessReadinessQueryPort | None = None,
        authorization_policies: AuthorizationPolicyQueryPort | None = None,
    ) -> None:
        self.agent_profiles = agent_profiles
        self.llm_profiles = llm_profiles
        self.tool_catalog = tool_catalog
        self.access_readiness = access_readiness
        self.authorization_policies = authorization_policies

    def resolve(self, profile_id: str) -> AgentProfileResolution:
        profile = self.agent_profiles.get_profile(profile_id)
        runtime = profile.runtime_preferences
        workspace_dir = (
            runtime.workdir
            or runtime.workspace
            or runtime.home_dir
        )

        validation: list[AgentValidationIssue] = []
        trace: list[AgentResolutionTrace] = [
            AgentResolutionTrace(
                source="agent",
                status="resolved",
                detail="profile loaded from Agent owner service",
            ),
        ]

        llm_routes, llm_access = resolve_llm_routes(
            profile,
            llm_profiles=self.llm_profiles,
            validation=validation,
            trace=trace,
        )
        authorization_grants = resolve_authorization_grants(
            profile.id,
            authorization_policies=self.authorization_policies,
            trace=trace,
        )
        tools, tool_access = resolve_tools(
            authorization_grants,
            tool_catalog=self.tool_catalog,
            validation=validation,
            trace=trace,
        )
        access_grants = resolve_access_grants(
            [*llm_access, *tool_access],
            access_readiness=self.access_readiness,
            workspace_dir=workspace_dir,
        )

        status = "valid"
        if any(issue.severity == "error" for issue in validation):
            status = "error"
        elif any(issue.severity == "warning" for issue in validation):
            status = "warning"

        return AgentProfileResolution(
            profile_id=profile.id,
            profile_updated_at=profile.updated_at.isoformat(),
            summary=AgentResolutionSummary(
                status=status,
                llm_routes=len(llm_routes),
                tools=len(tools),
                access_grants=len(access_grants),
                authorization_grants=len(authorization_grants),
                issues=len(validation),
            ),
            llm_routes=tuple(llm_routes),
            tools=tuple(tools),
            access_grants=tuple(access_grants),
            authorization_grants=tuple(authorization_grants),
            validation=tuple(validation),
            trace=tuple(trace),
        )
