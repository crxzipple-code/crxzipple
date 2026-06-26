from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from crxzipple.interfaces.runtime_container import AppContainer
from crxzipple.interfaces.http.dependencies import get_container

from .http_agent_grants import (
    grant_agent_authorization_response,
    revoke_agent_authorization_response,
)
from .http_decision_routes import router as decision_router
from .http_models import (
    AuthorizationAgentGrantRequest,
    AuthorizationAgentGrantResponse,
    AuthorizationPolicyExportResponse,
    AuthorizationPolicyImportRequest,
    AuthorizationPolicyImportResponse,
    AuthorizationPolicyResponse,
    AuthorizationPolicyStateRequest,
    AuthorizationPolicyWriteRequest,
)
from .http_policy_handlers import (
    create_policy_response,
    delete_policy_response,
    export_policy_response,
    import_policy_response,
    list_policy_responses,
    set_policy_enabled_response,
    update_policy_response,
)
from .http_services import authorization_service


router = APIRouter()
router.include_router(decision_router)


@router.get("/policies", response_model=list[AuthorizationPolicyResponse])
def list_policies(
    container: Annotated[AppContainer, Depends(get_container)],
) -> list[AuthorizationPolicyResponse]:
    return list_policy_responses(authorization_service(container))


@router.post(
    "/policies",
    response_model=AuthorizationPolicyResponse,
    status_code=201,
)
def create_policy(
    payload: AuthorizationPolicyWriteRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> AuthorizationPolicyResponse:
    return create_policy_response(payload, authorization_service(container))


@router.post(
    "/agent-grants",
    response_model=AuthorizationAgentGrantResponse,
)
def grant_agent_authorization(
    payload: AuthorizationAgentGrantRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> AuthorizationAgentGrantResponse:
    return grant_agent_authorization_response(
        payload,
        authorization_service(container),
    )


@router.post(
    "/agent-grants/revoke",
    response_model=AuthorizationAgentGrantResponse,
)
def revoke_agent_authorization(
    payload: AuthorizationAgentGrantRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> AuthorizationAgentGrantResponse:
    return revoke_agent_authorization_response(
        payload,
        authorization_service(container),
    )


@router.put(
    "/policies/{policy_id}",
    response_model=AuthorizationPolicyResponse,
)
def update_policy(
    policy_id: str,
    payload: AuthorizationPolicyWriteRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> AuthorizationPolicyResponse:
    return update_policy_response(policy_id, payload, authorization_service(container))


@router.post(
    "/policies/{policy_id}/enable",
    response_model=AuthorizationPolicyResponse,
)
def enable_policy(
    policy_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
    payload: AuthorizationPolicyStateRequest | None = None,
) -> AuthorizationPolicyResponse:
    return set_policy_enabled_response(
        policy_id,
        payload or AuthorizationPolicyStateRequest(),
        authorization_service(container),
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
    return set_policy_enabled_response(
        policy_id,
        payload or AuthorizationPolicyStateRequest(),
        authorization_service(container),
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
    return delete_policy_response(
        policy_id,
        payload or AuthorizationPolicyStateRequest(),
        authorization_service(container),
    )


@router.post(
    "/policies/import",
    response_model=AuthorizationPolicyImportResponse,
)
def import_policies(
    payload: AuthorizationPolicyImportRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> AuthorizationPolicyImportResponse:
    return import_policy_response(payload, authorization_service(container))


@router.get("/policies/export", response_model=AuthorizationPolicyExportResponse)
def export_policies(
    container: Annotated[AppContainer, Depends(get_container)],
) -> AuthorizationPolicyExportResponse:
    return export_policy_response(authorization_service(container))
