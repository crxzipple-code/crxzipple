from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from crxzipple.bootstrap import AppContainer
from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.modules.authorization.domain import (
    AuthorizationContext,
    AuthorizationEffect,
    AuthorizationObligation,
    AuthorizationPolicy,
    AuthorizationPolicyNotFoundError,
    AuthorizationRequest,
    AuthorizationResource,
    AuthorizationSubject,
)
from crxzipple.modules.authorization.infrastructure import YamlAuthorizationPolicyLoader


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


class AuthorizationActorRequest(BaseModel):
    type: str | None = None
    id: str | None = None


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
    proposed_policies: list[AuthorizationPolicyWriteRequest] = Field(default_factory=list)
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


@router.get("/policies", response_model=list[AuthorizationPolicyResponse])
def list_policies(
    container: Annotated[AppContainer, Depends(get_container)],
) -> list[AuthorizationPolicyResponse]:
    return [_to_policy_response(policy) for policy in container.authorization_service.list_policies()]


@router.post(
    "/policies",
    response_model=AuthorizationPolicyResponse,
    status_code=201,
)
def create_policy(
    payload: AuthorizationPolicyWriteRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> AuthorizationPolicyResponse:
    try:
        policy = container.authorization_service.create_policy(
            _policy_from_request(payload),
            actor_type=payload.actor.type,
            actor_id=payload.actor.id,
            reason=payload.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _to_policy_response(policy)


@router.put(
    "/policies/{policy_id}",
    response_model=AuthorizationPolicyResponse,
)
def update_policy(
    policy_id: str,
    payload: AuthorizationPolicyWriteRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> AuthorizationPolicyResponse:
    if payload.id != policy_id:
        raise HTTPException(
            status_code=400,
            detail="Policy id in path and payload must match.",
        )
    try:
        policy = container.authorization_service.update_policy(
            _policy_from_request(payload),
            actor_type=payload.actor.type,
            actor_id=payload.actor.id,
            reason=payload.reason,
        )
    except AuthorizationPolicyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_policy_response(policy)


@router.post(
    "/policies/{policy_id}/enable",
    response_model=AuthorizationPolicyResponse,
)
def enable_policy(
    policy_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
    payload: AuthorizationPolicyStateRequest | None = None,
) -> AuthorizationPolicyResponse:
    return _set_policy_enabled(
        policy_id,
        payload or AuthorizationPolicyStateRequest(),
        container,
        enabled=True,
    )


@router.post(
    "/policies/{policy_id}/disable",
    response_model=AuthorizationPolicyResponse,
)
def disable_policy(
    policy_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
    payload: AuthorizationPolicyStateRequest | None = None,
) -> AuthorizationPolicyResponse:
    return _set_policy_enabled(
        policy_id,
        payload or AuthorizationPolicyStateRequest(),
        container,
        enabled=False,
    )


@router.delete(
    "/policies/{policy_id}",
    response_model=AuthorizationPolicyResponse,
)
def delete_policy(
    policy_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
    payload: AuthorizationPolicyStateRequest | None = None,
) -> AuthorizationPolicyResponse:
    resolved_payload = payload or AuthorizationPolicyStateRequest()
    try:
        policy = container.authorization_service.delete_policy(
            policy_id,
            actor_type=resolved_payload.actor.type,
            actor_id=resolved_payload.actor.id,
            reason=resolved_payload.reason,
        )
    except AuthorizationPolicyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_policy_response(policy)


@router.post(
    "/policies/import",
    response_model=AuthorizationPolicyImportResponse,
)
def import_policies(
    payload: AuthorizationPolicyImportRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> AuthorizationPolicyImportResponse:
    try:
        policies = YamlAuthorizationPolicyLoader().load_text(
            payload.content,
            source_description=payload.source,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    imported = container.authorization_service.import_policies(
        policies,
        actor_type=payload.actor.type,
        actor_id=payload.actor.id,
        reason=payload.reason,
        source=payload.source,
    )
    return AuthorizationPolicyImportResponse(
        imported=len(imported),
        policy_ids=[policy.id for policy in imported],
    )


@router.get("/policies/export", response_model=AuthorizationPolicyExportResponse)
def export_policies(
    container: Annotated[AppContainer, Depends(get_container)],
) -> AuthorizationPolicyExportResponse:
    return AuthorizationPolicyExportResponse(
        **container.authorization_service.export_policy_bundle(),
    )


@router.post("/policies/dry-run", response_model=AuthorizationDecisionResponse)
def dry_run_authorization(
    payload: AuthorizationDryRunRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> AuthorizationDecisionResponse:
    decision = container.authorization_service.dry_run(
        _authorization_request_from_payload(payload.request),
        actor_type=payload.actor.type,
        actor_id=payload.actor.id,
        reason=payload.reason,
    )
    return _to_decision_response(decision)


@router.post("/policies/impact", response_model=AuthorizationImpactResponse)
def preview_policy_impact(
    payload: AuthorizationImpactRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> AuthorizationImpactResponse:
    preview = container.authorization_service.preview_policy_impact(
        _authorization_request_from_payload(payload.request),
        proposed_policies=tuple(
            _policy_from_request(policy_payload)
            for policy_payload in payload.proposed_policies
        ),
        remove_policy_ids=tuple(payload.remove_policy_ids),
        actor_type=payload.actor.type,
        actor_id=payload.actor.id,
        reason=payload.reason,
    )
    return AuthorizationImpactResponse(
        changed=preview.changed,
        before=_to_decision_response(preview.before),
        after=_to_decision_response(preview.after),
        added_policy_ids=list(preview.added_policy_ids),
        updated_policy_ids=list(preview.updated_policy_ids),
        removed_policy_ids=list(preview.removed_policy_ids),
    )


@router.get("/audits", response_model=list[AuthorizationAuditResponse])
def list_audits(
    container: Annotated[AppContainer, Depends(get_container)],
    limit: int = 50,
    offset: int = 0,
    action: str | None = None,
    target_policy_id: str | None = None,
) -> list[AuthorizationAuditResponse]:
    return [
        _to_audit_response(record)
        for record in container.authorization_service.list_audit_records(
            limit=limit,
            offset=offset,
            action=action,
            target_policy_id=target_policy_id,
        )
    ]


@router.post("/check", response_model=AuthorizationDecisionResponse)
def check_authorization(
    payload: AuthorizationCheckRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> AuthorizationDecisionResponse:
    decision = container.authorization_service.check(
        _authorization_request_from_payload(payload),
    )
    return _to_decision_response(decision)


def _set_policy_enabled(
    policy_id: str,
    payload: AuthorizationPolicyStateRequest,
    container: AppContainer,
    *,
    enabled: bool,
) -> AuthorizationPolicyResponse:
    try:
        policy = container.authorization_service.set_policy_enabled(
            policy_id,
            enabled=enabled,
            actor_type=payload.actor.type,
            actor_id=payload.actor.id,
            reason=payload.reason,
        )
    except AuthorizationPolicyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_policy_response(policy)


def _authorization_request_from_payload(
    payload: AuthorizationCheckRequest,
) -> AuthorizationRequest:
    return AuthorizationRequest(
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
    )


def _policy_from_request(payload: AuthorizationPolicyWriteRequest) -> AuthorizationPolicy:
    policy_id = payload.id.strip()
    if not policy_id:
        raise HTTPException(status_code=400, detail="Policy id cannot be empty.")
    actions = tuple(
        dict.fromkeys(
            action.strip()
            for action in payload.actions
            if action.strip()
        ),
    )
    if not actions:
        raise HTTPException(status_code=400, detail="Policy actions cannot be empty.")
    try:
        effect = AuthorizationEffect(payload.effect.strip().lower())
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported authorization effect '{payload.effect}'.",
        ) from exc
    return AuthorizationPolicy(
        id=policy_id,
        description=payload.description.strip(),
        effect=effect,
        actions=actions,
        subject_type=(payload.subject_type or "").strip() or None,
        subject_id=(payload.subject_id or "").strip() or None,
        subject_match=dict(payload.subject_match),
        resource_kind=(payload.resource_kind or "").strip() or None,
        resource_id=(payload.resource_id or "").strip() or None,
        resource_match=dict(payload.resource_match),
        context_match=dict(payload.context_match),
        condition=dict(payload.condition) if payload.condition is not None else None,
        obligations=tuple(
            AuthorizationObligation(name=item.name, params=dict(item.params))
            for item in payload.obligations
        ),
        priority=payload.priority,
        enabled=payload.enabled,
        source_kind=payload.source_kind.strip() or "local_managed",
    )


def _to_decision_response(decision) -> AuthorizationDecisionResponse:
    return AuthorizationDecisionResponse(
        allowed=decision.allowed,
        reason=decision.reason,
        code=decision.code.value,
        matched_policy_ids=list(decision.matched_policy_ids),
        obligations=[
            AuthorizationObligationResponse(name=item.name, params=dict(item.params))
            for item in decision.obligations
        ],
        details=dict(decision.details),
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


def _to_audit_response(record) -> AuthorizationAuditResponse:
    return AuthorizationAuditResponse(
        id=record.id,
        action=record.action,
        status=record.status,
        actor_type=record.actor_type,
        actor_id=record.actor_id,
        target_policy_id=record.target_policy_id,
        reason=record.reason,
        before_payload=dict(record.before_payload),
        after_payload=dict(record.after_payload),
        decision_payload=dict(record.decision_payload),
        metadata=dict(record.metadata),
        created_at=record.created_at.isoformat(),
    )
