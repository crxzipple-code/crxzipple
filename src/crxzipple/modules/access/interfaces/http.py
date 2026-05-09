from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from fastapi import HTTPException
from pydantic import BaseModel, Field

from crxzipple.bootstrap import AppContainer
from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.modules.access.application.actions import (
    AccessActionRequest as AccessActionCommand,
    AccessActionService,
)
from crxzipple.modules.access.application.setup import AccessSetupSessionService
from crxzipple.modules.access.application.settings_integration import (
    AccessSettingsActionAdapter,
    AccessSettingsConfigProvider,
)
from crxzipple.modules.access.interfaces.inventory import collect_access_inventory
from crxzipple.modules.access.interfaces.presenters import (
    present_readiness,
    present_setup_flow,
)


router = APIRouter()


class AccessSetupActionResponse(BaseModel):
    kind: str
    label: str
    description: str | None = None
    command: list[str] = Field(default_factory=list)
    url: str | None = None
    path: str | None = None
    env_vars: list[str] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)


class AccessSetupFlowResponse(BaseModel):
    kind: str
    title: str
    description: str
    action_label: str | None = None
    env_vars: list[str] = Field(default_factory=list)
    path: str | None = None
    command: list[str] = Field(default_factory=list)
    authorize_url: str | None = None
    callback_url: str | None = None
    verification_url: str | None = None
    user_code: str | None = None
    expires_at: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
    actions: list[AccessSetupActionResponse] = Field(default_factory=list)


class AccessReadinessResponse(BaseModel):
    target_type: Literal["requirement", "credential_binding"]
    requirement: str
    provider: str | None = None
    kind: str | None = None
    scopes: list[str] = Field(default_factory=list)
    status: str
    ready: bool
    setup_available: bool
    reason: str
    setup_flow: AccessSetupFlowResponse | None = None


class AccessCheckRequest(BaseModel):
    requirements: list[str] = Field(default_factory=list)
    credential_bindings: list[str] = Field(default_factory=list)
    workspace_dir: str | None = None
    allow_literal_credentials: bool = False


class AccessCheckResponse(BaseModel):
    ready: bool
    checks: list[AccessReadinessResponse] = Field(default_factory=list)


class AccessSetupRequest(BaseModel):
    target: str
    workspace_dir: str | None = None


class AccessActionRequest(BaseModel):
    action_id: str
    resource_kind: str
    target_id: str | None = None
    intent: str
    changes: dict[str, object] = Field(default_factory=dict)
    reason: str
    confirmation: str | None = None
    risk_acknowledged: bool = False
    actor: str | None = None
    trace_context: dict[str, object] = Field(default_factory=dict)


class AccessActionResultResponse(BaseModel):
    status: str
    asset: dict[str, object] | None = None
    audit_ref: str | None = None
    validation: dict[str, object] = Field(default_factory=dict)
    readiness: dict[str, object] | None = None
    warnings: list[str] = Field(default_factory=list)


class AccessRequirementSetResponse(BaseModel):
    ready: bool
    checks: list[AccessReadinessResponse] = Field(default_factory=list)


class AccessTargetReadinessResponse(BaseModel):
    resource_type: str
    resource_id: str
    display_name: str | None = None
    ready: bool
    setup_available: bool
    requirement_sets: list[AccessRequirementSetResponse] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)


class AccessInventoryCountsResponse(BaseModel):
    total: int
    ready: int
    blocked: int


class AccessInventoryResponse(BaseModel):
    ready: bool
    targets: list[AccessTargetReadinessResponse] = Field(default_factory=list)
    counts: AccessInventoryCountsResponse


@router.post("/check", response_model=AccessCheckResponse)
def check_access(
    payload: AccessCheckRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> AccessCheckResponse:
    checks: list[dict[str, object]] = []
    access_service = _access_service(container)
    for requirement in payload.requirements:
        readiness = access_service.check_requirement(
            requirement,
            workspace_dir=payload.workspace_dir,
        )
        checks.append(present_readiness(readiness, target_type="requirement"))
    for binding in payload.credential_bindings:
        readiness = access_service.check_credential_binding(
            binding,
            workspace_dir=payload.workspace_dir,
            allow_literal=payload.allow_literal_credentials,
        )
        checks.append(present_readiness(readiness, target_type="credential_binding"))
    return AccessCheckResponse(
        ready=all(bool(check["ready"]) for check in checks),
        checks=[AccessReadinessResponse.model_validate(check) for check in checks],
    )


@router.post("/setup", response_model=AccessSetupFlowResponse)
def begin_access_setup(
    payload: AccessSetupRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> AccessSetupFlowResponse:
    flow = _access_service(container).begin_setup(
        payload.target,
        workspace_dir=payload.workspace_dir,
    )
    return AccessSetupFlowResponse.model_validate(present_setup_flow(flow))


@router.post("/actions", response_model=AccessActionResultResponse)
def execute_access_action(
    payload: AccessActionRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> AccessActionResultResponse:
    governance_repository = container.access_governance_repository
    audit_repository = container.access_action_audit_repository
    service = AccessActionService(
        binding_repository=governance_repository,
        audit_repository=audit_repository,
        setup_session_service=AccessSetupSessionService(
            repository=governance_repository,
            audit_repository=audit_repository,
        ),
        settings_action_adapter=AccessSettingsActionAdapter(
            action_service=container.settings_action_service,
            query_service=container.settings_query_service,
            environment=container.settings.environment,
        ),
    )
    try:
        result = service.execute(
            AccessActionCommand(
                action_id=payload.action_id,
                resource_kind=payload.resource_kind,
                target_id=payload.target_id,
                intent=payload.intent,
                changes=dict(payload.changes),
                reason=payload.reason,
                confirmation=payload.confirmation,
                risk_acknowledged=payload.risk_acknowledged,
                actor=payload.actor,
                trace_context=dict(payload.trace_context),
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return AccessActionResultResponse(
        status=result.status,
        asset=result.asset,
        audit_ref=result.audit_ref,
        validation=result.validation,
        readiness=result.readiness,
        warnings=list(result.warnings),
    )


@router.get("/inventory", response_model=AccessInventoryResponse)
def access_inventory(
    container: Annotated[AppContainer, Depends(get_container)],
    workspace_dir: Annotated[
        str | None,
        Query(description="Workspace for relative credential files."),
    ] = None,
    include_ready: Annotated[
        bool,
        Query(description="Include targets whose access is already ready."),
    ] = False,
    include_disabled: Annotated[
        bool,
        Query(description="Include disabled model/tool/channel assets."),
    ] = False,
) -> AccessInventoryResponse:
    return AccessInventoryResponse.model_validate(
        collect_access_inventory(
            container,
            workspace_dir=workspace_dir,
            include_ready=include_ready,
            include_disabled=include_disabled,
        ),
    )


@router.get("/setup", response_model=AccessSetupFlowResponse)
def get_access_setup(
    target: Annotated[str, Query(..., description="Access requirement or binding.")],
    container: Annotated[AppContainer, Depends(get_container)],
    workspace_dir: Annotated[
        str | None,
        Query(description="Workspace for relative credential files."),
    ] = None,
) -> AccessSetupFlowResponse:
    flow = _access_service(container).begin_setup(target, workspace_dir=workspace_dir)
    return AccessSetupFlowResponse.model_validate(present_setup_flow(flow))


def _access_service(container: AppContainer):
    service = container.access_service
    service.config_view = AccessSettingsConfigProvider(
        getattr(container, "settings_query_service", None),
        environment=getattr(getattr(container, "settings", None), "environment", None),
    )
    return service
