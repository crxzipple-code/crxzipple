from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.interfaces.runtime_container import AppContainer, AppKey
from crxzipple.modules.workbench.interfaces.http_models import (
    WorkbenchAgentLlmRoutingPolicyResponse,
    WorkbenchAgentMemoryResponse,
    WorkbenchAgentProfileResponse,
    WorkbenchLlmProfileResponse,
    WorkbenchToolExecutionPolicyResponse,
    WorkbenchToolSummaryResponse,
)


router = APIRouter()


@router.get("/workbench/tools", response_model=list[WorkbenchToolSummaryResponse])
def list_workbench_tools(
    container: Annotated[AppContainer, Depends(get_container)],
    enabled_only: bool = Query(default=True),
) -> list[WorkbenchToolSummaryResponse]:
    tool_query = container.require(AppKey.TOOL_QUERY_SERVICE)
    tools = tool_query.list_enabled_tools() if enabled_only else tool_query.list_tools()
    return [
        WorkbenchToolSummaryResponse(
            id=tool.id,
            name=tool.name,
            description=tool.description,
            kind=tool.kind.value,
            tags=list(tool.tags),
            required_effect_ids=list(tool.required_effect_ids),
            execution_policy=WorkbenchToolExecutionPolicyResponse(
                timeout_seconds=tool.execution_policy.timeout_seconds,
                requires_confirmation=tool.execution_policy.requires_confirmation,
                mutates_state=tool.execution_policy.mutates_state,
            ),
            enabled=tool.enabled,
        )
        for tool in tools
    ]


@router.get("/workbench/agents", response_model=list[WorkbenchAgentProfileResponse])
def list_workbench_agents(
    container: Annotated[AppContainer, Depends(get_container)],
) -> list[WorkbenchAgentProfileResponse]:
    return [
        WorkbenchAgentProfileResponse(
            id=profile.id,
            name=profile.name,
            description="",
            enabled=profile.enabled,
            llm_routing_policy=WorkbenchAgentLlmRoutingPolicyResponse(
                default_llm_id=profile.llm_routing_policy.default_llm_id,
                fallback_llm_ids=list(profile.llm_routing_policy.fallback_llm_ids),
                image_llm_id=profile.llm_routing_policy.image_llm_id,
                document_llm_id=profile.llm_routing_policy.document_llm_id,
            ),
            memory=WorkbenchAgentMemoryResponse(
                enabled=profile.memory.enabled,
                scope_ref=profile.memory.scope_ref,
                access=profile.memory.access,
            ),
        )
        for profile in container.require(AppKey.AGENT_SERVICE).list_profiles()
    ]


@router.get("/workbench/models", response_model=list[WorkbenchLlmProfileResponse])
def list_workbench_models(
    container: Annotated[AppContainer, Depends(get_container)],
) -> list[WorkbenchLlmProfileResponse]:
    return [
        WorkbenchLlmProfileResponse(
            id=profile.id,
            provider=profile.provider.value,
            api_family=profile.api_family.value,
            model_name=profile.model_name,
            model_family=profile.model_family.value,
            capabilities=[capability.value for capability in profile.capabilities],
            enabled=profile.enabled,
        )
        for profile in container.require(AppKey.LLM_SERVICE).list_profiles()
    ]
