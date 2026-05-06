from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from crxzipple.bootstrap import AppContainer
from crxzipple.interfaces.authorization import authorize_tool_run
from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.modules.tool.application import (
    ExecuteToolInput,
)
from crxzipple.modules.tool.domain import (
    ToolEnvironment,
    ToolExecutionStrategy,
    ToolMode,
)
from crxzipple.modules.tool.domain.exceptions import (
    ToolRunNotFoundError,
    ToolValidationError,
)
from crxzipple.shared.time import (
    format_datetime_utc,
    format_optional_datetime_utc,
)


router = APIRouter()


class ToolExecutionPolicyResponse(BaseModel):
    timeout_seconds: int
    requires_confirmation: bool
    mutates_state: bool


class ToolExecutionSupportResponse(BaseModel):
    supported_modes: list[str]
    supported_strategies: list[str]
    supported_environments: list[str]


class ToolDiscoveryProviderResponse(BaseModel):
    name: str
    description: str
    source_kind: str


class ToolExecutionTargetResponse(BaseModel):
    mode: str
    strategy: str
    environment: str


class ToolParameterResponse(BaseModel):
    name: str
    data_type: str
    description: str
    required: bool


class ExecuteToolRunRequest(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict)
    mode: ToolMode = ToolMode.INLINE
    strategy: ToolExecutionStrategy = ToolExecutionStrategy.ASYNC
    environment: ToolEnvironment = ToolEnvironment.LOCAL
    run_id: str | None = None


class ToolResponse(BaseModel):
    id: str
    name: str
    description: str
    kind: str
    parameters: list[ToolParameterResponse]
    tags: list[str]
    required_effect_ids: list[str]
    access_requirements: list[str]
    access_requirement_sets: list[list[str]]
    execution_policy: ToolExecutionPolicyResponse
    execution_support: ToolExecutionSupportResponse
    source_kind: str
    runtime_key: str | None
    enabled: bool


class ToolRootResponse(BaseModel):
    path: str
    exists: bool


class ToolRunResponse(BaseModel):
    id: str
    tool_id: str
    target: ToolExecutionTargetResponse
    status: str
    input_payload: dict[str, Any]
    result: "ToolRunResultResponse | None" = None
    error: "ToolRunErrorResponse | None" = None
    output_payload: Any | None
    error_message: str | None
    created_at: str
    started_at: str | None
    completed_at: str | None
    attempt_count: int
    max_attempts: int
    worker_id: str | None
    heartbeat_at: str | None
    lease_expires_at: str | None
    cancel_requested_at: str | None


class ToolRunResultResponse(BaseModel):
    content: Any | None
    details: Any | None
    metadata: dict[str, Any]


class ToolRunErrorResponse(BaseModel):
    message: str
    code: str
    details: dict[str, Any]


class PruneExpiredToolWorkersResponse(BaseModel):
    pruned_count: int
    worker_ids: list[str]
    cutoff: str


@router.get("/roots", response_model=list[ToolRootResponse])
def list_tool_roots(
    container: Annotated[AppContainer, Depends(get_container)],
) -> list[ToolRootResponse]:
    return [
        ToolRootResponse(path=path, exists=Path(path).exists())
        for path in container.settings.tool_local_paths
    ]


@router.post("/discover-local", response_model=list[ToolResponse])
def discover_local_tools(
    container: Annotated[AppContainer, Depends(get_container)],
) -> list[ToolResponse]:
    tools = container.tool_service.discover_local_tools()
    return [_to_response(tool) for tool in tools]


@router.get("/providers", response_model=list[ToolDiscoveryProviderResponse])
def list_discovery_providers(
    container: Annotated[AppContainer, Depends(get_container)],
) -> list[ToolDiscoveryProviderResponse]:
    providers = container.tool_service.list_discovery_providers()
    return [
        ToolDiscoveryProviderResponse(
            name=provider.name,
            description=provider.description,
            source_kind=provider.source_kind.value,
        )
        for provider in providers
    ]


@router.post("/discover", response_model=list[ToolResponse])
def discover_tools(
    container: Annotated[AppContainer, Depends(get_container)],
    provider: str | None = None,
) -> list[ToolResponse]:
    tools = container.tool_service.discover_tools(provider_name=provider)
    return [_to_response(tool) for tool in tools]


@router.get("", response_model=list[ToolResponse])
def list_tools(
    container: Annotated[AppContainer, Depends(get_container)],
    enabled_only: bool = False,
) -> list[ToolResponse]:
    tools = (
        container.tool_service.list_enabled_tools()
        if enabled_only
        else container.tool_service.list_tools()
    )
    return [_to_response(tool) for tool in tools]


@router.post(
    "/{tool_id}/runs",
    response_model=ToolRunResponse,
    status_code=status.HTTP_201_CREATED,
)
async def execute_tool(
    tool_id: str,
    payload: ExecuteToolRunRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> ToolRunResponse:
    authorize_tool_run(
        container,
        tool_id=tool_id,
        mode=payload.mode,
        strategy=payload.strategy,
        environment=payload.environment,
        interface_name="http",
    )
    tool_run = await container.tool_service.execute(
        ExecuteToolInput(
            tool_id=tool_id,
            arguments=dict(payload.arguments),
            mode=payload.mode,
            strategy=payload.strategy,
            environment=payload.environment,
            run_id=payload.run_id,
        ),
    )
    return _to_run_response(tool_run)


@router.get("/{tool_id}/runs", response_model=list[ToolRunResponse])
def list_tool_runs(
    tool_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> list[ToolRunResponse]:
    tool_runs = container.tool_service.list_tool_runs(tool_id=tool_id)
    return [_to_run_response(tool_run) for tool_run in tool_runs]


@router.get("/runs/{run_id}", response_model=ToolRunResponse)
def get_tool_run(
    run_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> ToolRunResponse:
    return _to_run_response(container.tool_service.get_tool_run(run_id))


@router.post("/runs/{run_id}/cancel", response_model=ToolRunResponse)
def cancel_tool_run(
    run_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> ToolRunResponse:
    try:
        return _to_run_response(container.tool_service.cancel_tool_run(run_id))
    except ToolRunNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.post(
    "/runs/{run_id}/retry",
    response_model=ToolRunResponse,
    status_code=status.HTTP_201_CREATED,
)
async def retry_tool_run(
    run_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> ToolRunResponse:
    try:
        original = container.tool_service.get_tool_run(run_id)
        authorize_tool_run(
            container,
            tool_id=original.tool_id,
            mode=original.target.mode,
            strategy=original.target.strategy,
            environment=original.target.environment,
            interface_name="http",
        )
        return _to_run_response(await container.tool_service.retry_tool_run(run_id))
    except ToolRunNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except ToolValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.post("/workers/prune-expired", response_model=PruneExpiredToolWorkersResponse)
def prune_expired_tool_workers(
    container: Annotated[AppContainer, Depends(get_container)],
    retention_seconds: int = 3600,
) -> PruneExpiredToolWorkersResponse:
    result = container.tool_service.prune_expired_workers(
        retention_seconds=retention_seconds,
    )
    return PruneExpiredToolWorkersResponse(
        pruned_count=int(result["pruned_count"]),
        worker_ids=[str(item) for item in result["worker_ids"]],
        cutoff=format_datetime_utc(result["cutoff"]),
    )


def _to_response(tool) -> ToolResponse:
    return ToolResponse(
        id=tool.id,
        name=tool.name,
        description=tool.description,
        kind=tool.kind.value,
        parameters=[
            ToolParameterResponse(
                name=parameter.name,
                data_type=parameter.data_type,
                description=parameter.description,
                required=parameter.required,
            )
            for parameter in tool.parameters
        ],
        tags=list(tool.tags),
        required_effect_ids=list(tool.required_effect_ids),
        access_requirements=list(tool.access_requirements),
        access_requirement_sets=[
            list(requirement_set)
            for requirement_set in tool.access_requirement_sets
        ],
        execution_policy=ToolExecutionPolicyResponse(
            timeout_seconds=tool.execution_policy.timeout_seconds,
            requires_confirmation=tool.execution_policy.requires_confirmation,
            mutates_state=tool.execution_policy.mutates_state,
        ),
        execution_support=ToolExecutionSupportResponse(
            supported_modes=[
                mode.value for mode in tool.execution_support.supported_modes
            ],
            supported_strategies=[
                strategy.value
                for strategy in tool.execution_support.supported_strategies
            ],
            supported_environments=[
                environment.value
                for environment in tool.execution_support.supported_environments
            ],
        ),
        source_kind=tool.source_kind.value,
        runtime_key=tool.runtime_key,
        enabled=tool.enabled,
    )


def _to_run_response(tool_run) -> ToolRunResponse:
    return ToolRunResponse(
        id=tool_run.id,
        tool_id=tool_run.tool_id,
        target=ToolExecutionTargetResponse(
            mode=tool_run.target.mode.value,
            strategy=tool_run.target.strategy.value,
            environment=tool_run.target.environment.value,
        ),
        status=tool_run.status.value,
        input_payload=dict(tool_run.input_payload),
        result=(
            ToolRunResultResponse(
                content=[dict(block) for block in tool_run.result.blocks],
                details=tool_run.result.details,
                metadata=dict(tool_run.result.metadata),
            )
            if tool_run.result is not None
            else None
        ),
        error=(
            ToolRunErrorResponse(
                message=tool_run.error.message,
                code=tool_run.error.code,
                details=dict(tool_run.error.details),
            )
            if tool_run.error is not None
            else None
        ),
        output_payload=tool_run.output_payload,
        error_message=tool_run.error_message,
        created_at=format_datetime_utc(tool_run.created_at),
        started_at=format_optional_datetime_utc(tool_run.started_at),
        completed_at=format_optional_datetime_utc(tool_run.completed_at),
        attempt_count=tool_run.attempt_count,
        max_attempts=tool_run.max_attempts,
        worker_id=tool_run.worker_id,
        heartbeat_at=format_optional_datetime_utc(tool_run.heartbeat_at),
        lease_expires_at=format_optional_datetime_utc(
            tool_run.lease_expires_at,
        ),
        cancel_requested_at=format_optional_datetime_utc(
            tool_run.cancel_requested_at,
        ),
    )
