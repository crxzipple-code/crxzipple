from __future__ import annotations

from fastapi import HTTPException

from crxzipple.modules.authorization.application import AuthorizationApplicationService
from crxzipple.modules.authorization.domain import AuthorizationPolicyNotFoundError
from crxzipple.modules.authorization.infrastructure import YamlAuthorizationPolicyLoader

from .http_models import (
    AuthorizationPolicyExportResponse,
    AuthorizationPolicyImportRequest,
    AuthorizationPolicyImportResponse,
    AuthorizationPolicyResponse,
    AuthorizationPolicyStateRequest,
    AuthorizationPolicyWriteRequest,
)
from .http_payloads import (
    policy_from_request,
    to_policy_response,
)


def list_policy_responses(
    service: AuthorizationApplicationService,
) -> list[AuthorizationPolicyResponse]:
    return [to_policy_response(policy) for policy in service.list_policies()]


def create_policy_response(
    payload: AuthorizationPolicyWriteRequest,
    service: AuthorizationApplicationService,
) -> AuthorizationPolicyResponse:
    try:
        policy = service.create_policy(
            policy_from_request(payload),
            actor_type=payload.actor.type,
            actor_id=payload.actor.id,
            reason=payload.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return to_policy_response(policy)


def update_policy_response(
    policy_id: str,
    payload: AuthorizationPolicyWriteRequest,
    service: AuthorizationApplicationService,
) -> AuthorizationPolicyResponse:
    if payload.id != policy_id:
        raise HTTPException(
            status_code=400,
            detail="Policy id in path and payload must match.",
        )
    try:
        policy = service.update_policy(
            policy_from_request(payload),
            actor_type=payload.actor.type,
            actor_id=payload.actor.id,
            reason=payload.reason,
        )
    except AuthorizationPolicyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return to_policy_response(policy)


def set_policy_enabled_response(
    policy_id: str,
    payload: AuthorizationPolicyStateRequest,
    service: AuthorizationApplicationService,
    *,
    enabled: bool,
) -> AuthorizationPolicyResponse:
    try:
        policy = service.set_policy_enabled(
            policy_id,
            enabled=enabled,
            actor_type=payload.actor.type,
            actor_id=payload.actor.id,
            reason=payload.reason,
        )
    except AuthorizationPolicyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return to_policy_response(policy)


def delete_policy_response(
    policy_id: str,
    payload: AuthorizationPolicyStateRequest,
    service: AuthorizationApplicationService,
) -> AuthorizationPolicyResponse:
    try:
        policy = service.delete_policy(
            policy_id,
            actor_type=payload.actor.type,
            actor_id=payload.actor.id,
            reason=payload.reason,
        )
    except AuthorizationPolicyNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return to_policy_response(policy)


def import_policy_response(
    payload: AuthorizationPolicyImportRequest,
    service: AuthorizationApplicationService,
) -> AuthorizationPolicyImportResponse:
    try:
        policies = YamlAuthorizationPolicyLoader().load_text(
            payload.content,
            source_description=payload.source,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    imported = service.import_policies(
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


def export_policy_response(
    service: AuthorizationApplicationService,
) -> AuthorizationPolicyExportResponse:
    return AuthorizationPolicyExportResponse(**service.export_policy_bundle())


__all__ = [
    "create_policy_response",
    "delete_policy_response",
    "export_policy_response",
    "import_policy_response",
    "list_policy_responses",
    "set_policy_enabled_response",
    "update_policy_response",
]
