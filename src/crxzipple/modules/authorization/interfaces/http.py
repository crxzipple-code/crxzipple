from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from crxzipple.bootstrap import AppContainer
from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.modules.authorization.domain import (
    AuthorizationContext,
    AuthorizationRequest,
    AuthorizationResource,
    AuthorizationSubject,
)


router = APIRouter()


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


class AuthorizationCheckRequest(BaseModel):
    subject: AuthorizationSubjectRequest = Field(default_factory=AuthorizationSubjectRequest)
    action: str
    resource: AuthorizationResourceRequest
    context: AuthorizationContextRequest = Field(default_factory=AuthorizationContextRequest)


class AuthorizationObligationResponse(BaseModel):
    name: str
    params: dict[str, Any] = Field(default_factory=dict)


class AuthorizationDecisionResponse(BaseModel):
    allowed: bool
    reason: str
    matched_policy_ids: list[str] = Field(default_factory=list)
    obligations: list[AuthorizationObligationResponse] = Field(default_factory=list)


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


@router.get("/policies", response_model=list[AuthorizationPolicyResponse])
def list_policies(
    container: Annotated[AppContainer, Depends(get_container)],
) -> list[AuthorizationPolicyResponse]:
    return [_to_policy_response(policy) for policy in container.authorization_service.list_policies()]


@router.post("/check", response_model=AuthorizationDecisionResponse)
def check_authorization(
    payload: AuthorizationCheckRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> AuthorizationDecisionResponse:
    decision = container.authorization_service.check(
        AuthorizationRequest(
            subject=AuthorizationSubject(
                type=payload.subject.type,
                id=payload.subject.id,
                attrs=dict(payload.subject.attrs),
            ),
            action=payload.action,
            resource=AuthorizationResource(
                kind=payload.resource.kind,
                id=payload.resource.id,
                attrs=dict(payload.resource.attrs),
            ),
            context=AuthorizationContext(attrs=dict(payload.context.attrs)),
        ),
    )
    return _to_decision_response(decision)


def _to_decision_response(decision) -> AuthorizationDecisionResponse:
    return AuthorizationDecisionResponse(
        allowed=decision.allowed,
        reason=decision.reason,
        matched_policy_ids=list(decision.matched_policy_ids),
        obligations=[
            AuthorizationObligationResponse(name=item.name, params=dict(item.params))
            for item in decision.obligations
        ],
    )


def _to_policy_response(policy) -> AuthorizationPolicyResponse:
    return AuthorizationPolicyResponse(
        id=policy.id,
        description=policy.description,
        effect=policy.effect.value,
        actions=list(policy.actions),
        subject_type=policy.subject_type,
        subject_id=policy.subject_id,
        subject_match=dict(policy.subject_match),
        resource_kind=policy.resource_kind,
        resource_id=policy.resource_id,
        resource_match=dict(policy.resource_match),
        context_match=dict(policy.context_match),
        condition=dict(policy.condition) if policy.condition is not None else None,
        obligations=[
            AuthorizationObligationResponse(name=item.name, params=dict(item.params))
            for item in policy.obligations
        ],
        priority=policy.priority,
        enabled=policy.enabled,
        source_kind=policy.source_kind,
    )

