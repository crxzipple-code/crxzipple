from __future__ import annotations

from pydantic import BaseModel, Field

from crxzipple.modules.agent.application import (
    AgentAccessGrant,
    AgentAuthorizationGrant,
    AgentHomeFileSnapshot,
    AgentHomeSnapshot,
    AgentProfileResolution,
    AgentResolvedLlm,
    AgentResolvedTool,
    AgentResolutionSummary,
    AgentResolutionTrace,
    AgentValidationIssue,
)
from crxzipple.modules.agent.interfaces.dto import AgentProfileDTO


class AgentIdentityResponse(BaseModel):
    display_name: str | None = None
    theme: str | None = None
    emoji: str | None = None
    avatar: str | None = None


class AgentInstructionPolicyResponse(BaseModel):
    system_prompt: str
    response_style: str | None = None
    thinking_default: str | None = None
    stream_by_default: bool


class AgentLlmRoutingPolicyResponse(BaseModel):
    default_llm_id: str
    fallback_llm_ids: list[str]
    image_llm_id: str | None = None
    document_llm_id: str | None = None


class AgentLlmPolicyResponse(BaseModel):
    reasoning_summary_policy: str
    raw_reasoning_policy: str
    tool_use_policy: str
    parallel_tool_calls_policy: str
    final_answer_policy: str
    commentary_visibility_policy: str
    provider_external_item_policy: str


class AgentExecutionPolicyResponse(BaseModel):
    timeout_seconds: int
    max_turns: int


class AgentRuntimePreferencesResponse(BaseModel):
    home_dir: str | None = None
    workdir: str | None = None
    workspace: str | None = None
    sandbox_mode: str | None = None
    attrs: dict[str, object] = Field(default_factory=dict)


class AgentMemoryBindingResponse(BaseModel):
    enabled: bool
    scope_ref: str | None = None
    access: str


class AgentProfileResponse(BaseModel):
    id: str
    name: str
    enabled: bool
    created_at: str
    updated_at: str
    identity: AgentIdentityResponse
    instruction_policy: AgentInstructionPolicyResponse
    llm_routing_policy: AgentLlmRoutingPolicyResponse
    llm_policy: AgentLlmPolicyResponse
    execution_policy: AgentExecutionPolicyResponse
    runtime_preferences: AgentRuntimePreferencesResponse
    memory: AgentMemoryBindingResponse


class AgentHomeMigrationResponse(BaseModel):
    source_dir: str | None = None
    home_dir: str | None = None
    workdir: str | None = None
    copied_paths: list[str] = Field(default_factory=list)
    skipped_paths: list[str] = Field(default_factory=list)
    profile: AgentProfileResponse


class AgentHomeConfigResponse(BaseModel):
    home_dir: str
    path: str
    profile: AgentProfileResponse


class AgentHomeFileResponse(BaseModel):
    name: str
    path: str
    exists: bool
    language: str
    content: str


class AgentHomeSnapshotResponse(BaseModel):
    agent_id: str
    agent_name: str
    home_dir: str
    workdir: str | None = None
    files: list[AgentHomeFileResponse]


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


def agent_profile_response(dto: AgentProfileDTO) -> AgentProfileResponse:
    return AgentProfileResponse(
        id=dto.id,
        name=dto.name,
        enabled=dto.enabled,
        created_at=dto.created_at,
        updated_at=dto.updated_at,
        identity=AgentIdentityResponse(
            display_name=dto.identity.display_name,
            theme=dto.identity.theme,
            emoji=dto.identity.emoji,
            avatar=dto.identity.avatar,
        ),
        instruction_policy=AgentInstructionPolicyResponse(
            system_prompt=dto.instruction_policy.system_prompt,
            response_style=dto.instruction_policy.response_style,
            thinking_default=dto.instruction_policy.thinking_default,
            stream_by_default=dto.instruction_policy.stream_by_default,
        ),
        llm_routing_policy=AgentLlmRoutingPolicyResponse(
            default_llm_id=dto.llm_routing_policy.default_llm_id,
            fallback_llm_ids=list(dto.llm_routing_policy.fallback_llm_ids),
            image_llm_id=dto.llm_routing_policy.image_llm_id,
            document_llm_id=dto.llm_routing_policy.document_llm_id,
        ),
        llm_policy=AgentLlmPolicyResponse(
            reasoning_summary_policy=dto.llm_policy.reasoning_summary_policy,
            raw_reasoning_policy=dto.llm_policy.raw_reasoning_policy,
            tool_use_policy=dto.llm_policy.tool_use_policy,
            parallel_tool_calls_policy=dto.llm_policy.parallel_tool_calls_policy,
            final_answer_policy=dto.llm_policy.final_answer_policy,
            commentary_visibility_policy=dto.llm_policy.commentary_visibility_policy,
            provider_external_item_policy=dto.llm_policy.provider_external_item_policy,
        ),
        execution_policy=AgentExecutionPolicyResponse(
            timeout_seconds=dto.execution_policy.timeout_seconds,
            max_turns=dto.execution_policy.max_turns,
        ),
        runtime_preferences=AgentRuntimePreferencesResponse(
            home_dir=dto.runtime_preferences.home_dir,
            workdir=dto.runtime_preferences.workdir,
            workspace=dto.runtime_preferences.workspace,
            sandbox_mode=dto.runtime_preferences.sandbox_mode,
            attrs=dict(dto.runtime_preferences.attrs),
        ),
        memory=AgentMemoryBindingResponse(
            enabled=dto.memory.enabled,
            scope_ref=dto.memory.scope_ref,
            access=dto.memory.access,
        ),
    )


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


def agent_home_snapshot_response(snapshot: AgentHomeSnapshot) -> AgentHomeSnapshotResponse:
    return AgentHomeSnapshotResponse(
        agent_id=snapshot.profile.id,
        agent_name=snapshot.profile.name,
        home_dir=snapshot.home_dir,
        workdir=snapshot.workdir,
        files=[_home_file_response(item) for item in snapshot.files],
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


def _home_file_response(file: AgentHomeFileSnapshot) -> AgentHomeFileResponse:
    return AgentHomeFileResponse(
        name=file.name,
        path=file.path,
        exists=file.exists,
        language=file.language,
        content=file.content,
    )
