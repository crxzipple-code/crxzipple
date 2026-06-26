from __future__ import annotations

from pydantic import BaseModel, Field

from crxzipple.modules.agent.application import (
    AgentAccessGrant,
    AgentAuthorizationGrant,
    AgentProfileResolution,
    AgentResolvedLlm,
    AgentResolvedTool,
    AgentResolutionSummary,
    AgentResolutionTrace,
    AgentValidationIssue,
)


class AgentResolutionSummaryResponse(BaseModel):
    status: str
    llm_routes: int
    tools: int
    access_grants: int
    authorization_grants: int
    issues: int


class AgentResolvedLlmResponse(BaseModel):
    slot: str
    llm_id: str
    resolved: bool
    enabled: bool
    provider: str | None = None
    model_name: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    context_window_tokens: int | None = None
    credential_binding_id: str | None = None


class AgentResolvedToolResponse(BaseModel):
    tool_id: str
    resolved: bool
    enabled: bool
    name: str | None = None
    kind: str | None = None
    definition_origin: str | None = None
    access_requirements: list[str] = Field(default_factory=list)
    access_requirement_sets: list[list[str]] = Field(default_factory=list)
    required_effect_ids: list[str] = Field(default_factory=list)
    requires_confirmation: bool = False
    mutates_state: bool = False


class AgentAccessGrantResponse(BaseModel):
    source_type: str
    source_id: str
    requirement: str
    grant_kind: str
    status: str
    ready: bool
    setup_available: bool
    reason: str | None = None


class AgentAuthorizationGrantResponse(BaseModel):
    policy_id: str
    effect: str
    action: str
    status: str
    effect_ids: list[str] = Field(default_factory=list)
    tool_ids: list[str] = Field(default_factory=list)
    source_kind: str | None = None
    description: str = ""


class AgentValidationIssueResponse(BaseModel):
    severity: str
    code: str
    message: str
    ref: str | None = None


class AgentResolutionTraceResponse(BaseModel):
    source: str
    status: str
    detail: str


class AgentProfileResolutionResponse(BaseModel):
    profile_id: str
    profile_updated_at: str
    summary: AgentResolutionSummaryResponse
    llm_routes: list[AgentResolvedLlmResponse] = Field(default_factory=list)
    tools: list[AgentResolvedToolResponse] = Field(default_factory=list)
    access_grants: list[AgentAccessGrantResponse] = Field(default_factory=list)
    authorization_grants: list[AgentAuthorizationGrantResponse] = Field(
        default_factory=list,
    )
    validation: list[AgentValidationIssueResponse] = Field(default_factory=list)
    trace: list[AgentResolutionTraceResponse] = Field(default_factory=list)


def agent_profile_resolution_response(
    resolution: AgentProfileResolution,
) -> AgentProfileResolutionResponse:
    return AgentProfileResolutionResponse(
        profile_id=resolution.profile_id,
        profile_updated_at=resolution.profile_updated_at,
        summary=_resolution_summary_response(resolution.summary),
        llm_routes=[_resolved_llm_response(item) for item in resolution.llm_routes],
        tools=[_resolved_tool_response(item) for item in resolution.tools],
        access_grants=[
            _access_grant_response(item) for item in resolution.access_grants
        ],
        authorization_grants=[
            _authorization_grant_response(item)
            for item in resolution.authorization_grants
        ],
        validation=[_validation_issue_response(item) for item in resolution.validation],
        trace=[_resolution_trace_response(item) for item in resolution.trace],
    )


def _resolution_summary_response(
    summary: AgentResolutionSummary,
) -> AgentResolutionSummaryResponse:
    return AgentResolutionSummaryResponse(
        status=summary.status,
        llm_routes=summary.llm_routes,
        tools=summary.tools,
        access_grants=summary.access_grants,
        authorization_grants=summary.authorization_grants,
        issues=summary.issues,
    )


def _resolved_llm_response(item: AgentResolvedLlm) -> AgentResolvedLlmResponse:
    return AgentResolvedLlmResponse(
        slot=item.slot,
        llm_id=item.llm_id,
        resolved=item.resolved,
        enabled=item.enabled,
        provider=item.provider,
        model_name=item.model_name,
        capabilities=list(item.capabilities),
        context_window_tokens=item.context_window_tokens,
        credential_binding_id=item.credential_binding_id,
    )


def _resolved_tool_response(item: AgentResolvedTool) -> AgentResolvedToolResponse:
    return AgentResolvedToolResponse(
        tool_id=item.tool_id,
        resolved=item.resolved,
        enabled=item.enabled,
        name=item.name,
        kind=item.kind,
        definition_origin=item.definition_origin,
        access_requirements=list(item.access_requirements),
        access_requirement_sets=[list(group) for group in item.access_requirement_sets],
        required_effect_ids=list(item.required_effect_ids),
        requires_confirmation=item.requires_confirmation,
        mutates_state=item.mutates_state,
    )


def _access_grant_response(item: AgentAccessGrant) -> AgentAccessGrantResponse:
    return AgentAccessGrantResponse(
        source_type=item.source_type,
        source_id=item.source_id,
        requirement=item.requirement,
        grant_kind=item.grant_kind,
        status=item.status,
        ready=item.ready,
        setup_available=item.setup_available,
        reason=item.reason,
    )


def _authorization_grant_response(
    item: AgentAuthorizationGrant,
) -> AgentAuthorizationGrantResponse:
    return AgentAuthorizationGrantResponse(
        policy_id=item.policy_id,
        effect=item.effect,
        action=item.action,
        status=item.status,
        effect_ids=list(item.effect_ids),
        tool_ids=list(item.tool_ids),
        source_kind=item.source_kind,
        description=item.description,
    )


def _validation_issue_response(
    item: AgentValidationIssue,
) -> AgentValidationIssueResponse:
    return AgentValidationIssueResponse(
        severity=item.severity,
        code=item.code,
        message=item.message,
        ref=item.ref,
    )


def _resolution_trace_response(
    item: AgentResolutionTrace,
) -> AgentResolutionTraceResponse:
    return AgentResolutionTraceResponse(
        source=item.source,
        status=item.status,
        detail=item.detail,
    )


__all__ = [
    "AgentAccessGrantResponse",
    "AgentAuthorizationGrantResponse",
    "AgentProfileResolutionResponse",
    "AgentResolutionSummaryResponse",
    "AgentResolutionTraceResponse",
    "AgentResolvedLlmResponse",
    "AgentResolvedToolResponse",
    "AgentValidationIssueResponse",
    "agent_profile_resolution_response",
]
