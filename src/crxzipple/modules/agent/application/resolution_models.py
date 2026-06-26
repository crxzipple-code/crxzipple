from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class AgentResolvedLlm:
    slot: str
    llm_id: str
    resolved: bool
    enabled: bool
    provider: str | None = None
    model_name: str | None = None
    capabilities: tuple[str, ...] = ()
    context_window_tokens: int | None = None
    credential_binding_id: str | None = None


@dataclass(frozen=True, slots=True)
class AgentResolvedTool:
    tool_id: str
    resolved: bool
    enabled: bool
    name: str | None = None
    kind: str | None = None
    definition_origin: str | None = None
    access_requirements: tuple[str, ...] = ()
    access_requirement_sets: tuple[tuple[str, ...], ...] = ()
    required_effect_ids: tuple[str, ...] = ()
    requires_confirmation: bool = False
    mutates_state: bool = False


@dataclass(frozen=True, slots=True)
class AgentAccessGrant:
    source_type: str
    source_id: str
    requirement: str
    grant_kind: str
    status: str = "unknown"
    ready: bool = False
    setup_available: bool = False
    reason: str | None = None
    _raw_requirement: str = field(default="", repr=False, compare=False)


@dataclass(frozen=True, slots=True)
class AgentAuthorizationGrant:
    policy_id: str
    effect: str
    action: str
    status: str
    effect_ids: tuple[str, ...] = ()
    tool_ids: tuple[str, ...] = ()
    source_kind: str | None = None
    description: str = ""


@dataclass(frozen=True, slots=True)
class AgentValidationIssue:
    severity: str
    code: str
    message: str
    ref: str | None = None


@dataclass(frozen=True, slots=True)
class AgentResolutionTrace:
    source: str
    status: str
    detail: str


@dataclass(frozen=True, slots=True)
class AgentResolutionSummary:
    status: str
    llm_routes: int
    tools: int
    access_grants: int
    authorization_grants: int
    issues: int


@dataclass(frozen=True, slots=True)
class AgentProfileResolution:
    profile_id: str
    profile_updated_at: str
    summary: AgentResolutionSummary
    llm_routes: tuple[AgentResolvedLlm, ...] = ()
    tools: tuple[AgentResolvedTool, ...] = ()
    access_grants: tuple[AgentAccessGrant, ...] = ()
    authorization_grants: tuple[AgentAuthorizationGrant, ...] = ()
    validation: tuple[AgentValidationIssue, ...] = ()
    trace: tuple[AgentResolutionTrace, ...] = ()


__all__ = [
    "AgentAccessGrant",
    "AgentAuthorizationGrant",
    "AgentProfileResolution",
    "AgentResolutionSummary",
    "AgentResolutionTrace",
    "AgentResolvedLlm",
    "AgentResolvedTool",
    "AgentValidationIssue",
]
