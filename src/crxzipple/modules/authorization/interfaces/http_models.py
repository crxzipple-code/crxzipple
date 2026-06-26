from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class AuthorizationSubjectRequest(BaseModel):
    type: str = "anonymous"
    id: str | None = None
    attrs: dict[str, Any] = Field(default_factory=dict)


class AuthorizationResourceRequest(BaseModel):
    kind: str
    id: str | None = None
    attrs: dict[str, Any] = Field(default_factory=dict)


class AuthorizationContextRequest(BaseModel):
    attrs: dict[str, Any] = Field(default_factory=dict)


class AuthorizationActorRequest(BaseModel):
    type: str | None = None
    id: str | None = None


class AuthorizationCheckRequest(BaseModel):
    subject: AuthorizationSubjectRequest = Field(
        default_factory=AuthorizationSubjectRequest,
    )
    action: str
    resource: AuthorizationResourceRequest
    context: AuthorizationContextRequest = Field(
        default_factory=AuthorizationContextRequest,
    )


class AuthorizationObligationResponse(BaseModel):
    name: str
    params: dict[str, Any] = Field(default_factory=dict)


class AuthorizationDecisionResponse(BaseModel):
    allowed: bool
    reason: str
    code: str
    matched_policy_ids: list[str] = Field(default_factory=list)
    obligations: list[AuthorizationObligationResponse] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class AuthorizationPolicyResponse(BaseModel):
    id: str
    description: str
    effect: str
    actions: list[str]
    subject_type: str | None = None
    subject_id: str | None = None
    subject_match: dict[str, Any] = Field(default_factory=dict)
    resource_kind: str | None = None
    resource_id: str | None = None
    resource_match: dict[str, Any] = Field(default_factory=dict)
    context_match: dict[str, Any] = Field(default_factory=dict)
    condition: dict[str, Any] | None = None
    obligations: list[AuthorizationObligationResponse] = Field(default_factory=list)
    priority: int
    enabled: bool
    source_kind: str


class AuthorizationPolicyWriteRequest(BaseModel):
    id: str
    description: str = ""
    effect: str = "deny"
    actions: list[str]
    subject_type: str | None = None
    subject_id: str | None = None
    subject_match: dict[str, Any] = Field(default_factory=dict)
    resource_kind: str | None = None
    resource_id: str | None = None
    resource_match: dict[str, Any] = Field(default_factory=dict)
    context_match: dict[str, Any] = Field(default_factory=dict)
    condition: dict[str, Any] | None = None
    obligations: list[AuthorizationObligationResponse] = Field(default_factory=list)
    priority: int = 0
    enabled: bool = True
    source_kind: str = "local_managed"
    actor: AuthorizationActorRequest = Field(default_factory=AuthorizationActorRequest)
    reason: str = ""


class AuthorizationPolicyStateRequest(BaseModel):
    actor: AuthorizationActorRequest = Field(default_factory=AuthorizationActorRequest)
    reason: str = ""


class AuthorizationAgentGrantRequest(BaseModel):
    agent_id: str
    kind: Literal["effect", "tool"]
    id: str
    actor: AuthorizationActorRequest = Field(default_factory=AuthorizationActorRequest)
    reason: str = ""


class AuthorizationAgentGrantResponse(BaseModel):
    agent_id: str
    kind: Literal["effect", "tool"]
    id: str
    policy_id: str
    status: Literal["enabled", "revoked", "not_found"]
    policy: AuthorizationPolicyResponse | None = None


class AuthorizationPolicyImportRequest(BaseModel):
    content: str
    source: str = "inline"
    actor: AuthorizationActorRequest = Field(default_factory=AuthorizationActorRequest)
    reason: str = ""


class AuthorizationPolicyImportResponse(BaseModel):
    imported: int
    policy_ids: list[str]


class AuthorizationPolicyExportResponse(BaseModel):
    kind: str
    version: int
    policies: list[dict[str, Any]]


class AuthorizationDryRunRequest(BaseModel):
    request: AuthorizationCheckRequest
    actor: AuthorizationActorRequest = Field(default_factory=AuthorizationActorRequest)
    reason: str = ""


class AuthorizationImpactRequest(BaseModel):
    request: AuthorizationCheckRequest
    proposed_policies: list[AuthorizationPolicyWriteRequest] = Field(
        default_factory=list,
    )
    remove_policy_ids: list[str] = Field(default_factory=list)
    actor: AuthorizationActorRequest = Field(default_factory=AuthorizationActorRequest)
    reason: str = ""


class AuthorizationImpactResponse(BaseModel):
    changed: bool
    before: AuthorizationDecisionResponse
    after: AuthorizationDecisionResponse
    added_policy_ids: list[str] = Field(default_factory=list)
    updated_policy_ids: list[str] = Field(default_factory=list)
    removed_policy_ids: list[str] = Field(default_factory=list)


class AuthorizationAuditResponse(BaseModel):
    id: str
    action: str
    status: str
    actor_type: str | None = None
    actor_id: str | None = None
    target_policy_id: str | None = None
    reason: str = ""
    before_payload: dict[str, Any] = Field(default_factory=dict)
    after_payload: dict[str, Any] = Field(default_factory=dict)
    decision_payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: str


__all__ = [
    "AuthorizationActorRequest",
    "AuthorizationAgentGrantRequest",
    "AuthorizationAgentGrantResponse",
    "AuthorizationAuditResponse",
    "AuthorizationCheckRequest",
    "AuthorizationContextRequest",
    "AuthorizationDecisionResponse",
    "AuthorizationDryRunRequest",
    "AuthorizationImpactRequest",
    "AuthorizationImpactResponse",
    "AuthorizationObligationResponse",
    "AuthorizationPolicyExportResponse",
    "AuthorizationPolicyImportRequest",
    "AuthorizationPolicyImportResponse",
    "AuthorizationPolicyResponse",
    "AuthorizationPolicyStateRequest",
    "AuthorizationPolicyWriteRequest",
    "AuthorizationResourceRequest",
    "AuthorizationSubjectRequest",
]
