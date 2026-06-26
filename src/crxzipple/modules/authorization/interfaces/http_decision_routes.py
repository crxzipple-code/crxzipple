from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.interfaces.runtime_container import AppContainer

from .http_models import (
    AuthorizationAuditResponse,
    AuthorizationCheckRequest,
    AuthorizationDecisionResponse,
    AuthorizationDryRunRequest,
    AuthorizationImpactRequest,
    AuthorizationImpactResponse,
)
from .http_payloads import (
    authorization_request_from_payload as _authorization_request_from_payload,
    policy_from_request as _policy_from_request,
    to_audit_response as _to_audit_response,
    to_decision_response as _to_decision_response,
)
from .http_services import authorization_service


router = APIRouter()


@router.post("/policies/dry-run", response_model=AuthorizationDecisionResponse)
def dry_run_authorization(
    payload: AuthorizationDryRunRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> AuthorizationDecisionResponse:
    decision = authorization_service(container).dry_run(
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
    preview = authorization_service(container).preview_policy_impact(
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
        for record in authorization_service(container).list_audit_records(
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
    decision = authorization_service(container).check(
        _authorization_request_from_payload(payload),
    )
    return _to_decision_response(decision)
