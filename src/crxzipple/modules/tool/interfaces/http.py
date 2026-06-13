from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from crxzipple.interfaces.runtime_container import AppContainer, AppKey
from crxzipple.interfaces.authorization import authorize_tool_run
from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.modules.tool.application import (
    ExecuteToolInput,
    ToolFunctionCatalogRecord,
    ToolSourceCatalogRecord,
    ToolSourceDiscoveryRunRecord,
    ToolSourceSyncResult,
)
from crxzipple.modules.tool.domain import (
    ToolEnvironment,
    ToolExecutionStrategy,
    ToolMode,
)
from crxzipple.modules.tool.domain.exceptions import (
    ToolExecutionNotAllowedError,
    ToolExecutionNotSupportedError,
    ToolNotFoundError,
    ToolRunNotFoundError,
    ToolValidationError,
)
from crxzipple.modules.tool.interfaces.dto import _credential_requirement_set_payload
from crxzipple.shared.time import (
    format_datetime_utc,
    format_optional_datetime_utc,
)


router = APIRouter()


class ToolExecutionPolicyResponse(BaseModel):
    timeout_seconds: int
    requires_confirmation: bool
    mutates_state: bool
    supports_parallel: bool
    resource_scope: str | None = None
    serial_group_key: str | None = None


class ToolExecutionSupportResponse(BaseModel):
    supported_modes: list[str]
    supported_strategies: list[str]
    supported_environments: list[str]


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
    source_id: str | None = None
    name: str
    description: str
    kind: str
    parameters: list[ToolParameterResponse]
    tags: list[str]
    required_effect_ids: list[str]
    access_requirements: list[str]
    access_requirement_sets: list[list[str]]
    runtime_requirement_sets: list[list[str]]
    context_requirements: list[str]
    credential_requirements: list[dict[str, Any]]
    execution_policy: ToolExecutionPolicyResponse
    execution_support: ToolExecutionSupportResponse
    definition_origin: str
    runtime_key: str | None
    enabled: bool


class ToolRootResponse(BaseModel):
    path: str
    exists: bool


class ToolSourceResponse(BaseModel):
    source_id: str
    kind: str
    display_name: str
    description: str
    config: dict[str, Any]
    credential_requirements: list[dict[str, Any]]
    runtime_requirements: list[str]
    status: str
    revision: int
    config_hash: str
    last_discovered_at: str | None
    last_discovery_status: str | None
    created_at: str | None
    updated_at: str | None


class ToolSourceDiscoveryRunResponse(BaseModel):
    discovery_run_id: str
    source_id: str
    source_revision: int
    config_hash: str
    status: str
    discovered_at: str
    function_count: int
    provider_backend_count: int
    error_message: str | None
    metadata: dict[str, Any]


class ToolSourceSyncResponse(BaseModel):
    source: ToolSourceResponse
    skipped: bool
    error_message: str | None
    discovery: ToolSourceDiscoveryRunResponse | None


class ToolSourceWriteRequest(BaseModel):
    source_id: str
    kind: str
    display_name: str
    description: str = ""
    config: dict[str, Any] = Field(default_factory=dict)
    credential_requirements: list[dict[str, Any]] = Field(default_factory=list)
    runtime_requirements: list[str] = Field(default_factory=list)
    status: str = "active"


class ToolFunctionResponse(BaseModel):
    function_id: str
    source_id: str
    stable_key: str
    name: str
    description: str
    input_schema: dict[str, Any]
    runtime_kind: str
    handler_ref: str
    capabilities: list[str]
    kind: str
    parameters: list[ToolParameterResponse]
    tags: list[str]
    required_effect_ids: list[str]
    access_requirement_sets: list[list[str]]
    runtime_requirement_sets: list[list[str]]
    context_requirements: list[str]
    credential_requirements: list[dict[str, Any]]
    execution_policy: ToolExecutionPolicyResponse
    execution_support: ToolExecutionSupportResponse
    definition_origin: str
    runtime_key: str | None
    schema_hash: str
    status: str
    enabled: bool
    revision: int
    trust_policy: dict[str, Any]
    approval_policy: dict[str, Any]
    credential_binding_overrides: dict[str, str]
    required_effect_overrides: list[str] | None
    metadata: dict[str, Any]
    created_at: str | None
    updated_at: str | None
    last_seen_at: str | None
    stale_since: str | None
    deprecated_at: str | None


class ToolProviderBackendResponse(BaseModel):
    backend_id: str
    source_id: str
    capability: str
    display_name: str
    credential_requirements: list[dict[str, Any]]
    runtime_ref: dict[str, Any]
    priority: int
    enabled: bool
    status: str
    readiness: dict[str, Any] | None = None
    created_at: str
    updated_at: str


class ToolFunctionPolicyRequest(BaseModel):
    trust_policy: dict[str, Any] = Field(default_factory=dict)
    approval_policy: dict[str, Any] = Field(default_factory=dict)
    credential_binding_overrides: dict[str, str] = Field(default_factory=dict)
    required_effect_overrides: list[str] | None = None


class ToolRunResponse(BaseModel):
    id: str
    tool_id: str
    call_id: str | None = None
    tool_surface_id: str | None = None
    function_id: str | None
    function_revision: int | None
    source_id: str | None
    source_revision: int | None
    schema_hash: str | None
    target: ToolExecutionTargetResponse
    status: str
    input_payload: dict[str, Any]
    metadata: dict[str, Any]
    result: "ToolRunResultResponse | None" = None
    error: "ToolRunErrorResponse | None" = None
    output_payload: Any | None
    result_envelope_payload: dict[str, Any] | None = None
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
        for path in container.require(AppKey.TOOL_BOOTSTRAP_CONFIG).local_paths
    ]


@router.get("/sources", response_model=list[ToolSourceResponse])
def list_tool_sources(
    container: Annotated[AppContainer, Depends(get_container)],
    kind: str | None = None,
    status: str | None = None,
) -> list[ToolSourceResponse]:
    sources = container.require(AppKey.TOOL_SOURCE_QUERY_SERVICE).list_sources(
        kind=kind,
        status=status,
    )
    return [_source_response(source) for source in sources]


@router.post("/sources", response_model=ToolSourceResponse)
def create_tool_source(
    payload: ToolSourceWriteRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> ToolSourceResponse:
    try:
        result = container.require(
            AppKey.TOOL_SOURCE_COMMAND_SERVICE,
        ).create_source(_source_record_from_request(payload))
    except ToolValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return _source_response(result.source)


@router.get("/sources/{source_id}", response_model=ToolSourceResponse)
def get_tool_source(
    source_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> ToolSourceResponse:
    source = container.require(AppKey.TOOL_SOURCE_QUERY_SERVICE).get_source(source_id)
    if source is None:
        raise HTTPException(
            status_code=404,
            detail=f"Tool source '{source_id}' was not found.",
        )
    return _source_response(source)


@router.put("/sources/{source_id}", response_model=ToolSourceResponse)
def update_tool_source(
    source_id: str,
    payload: ToolSourceWriteRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> ToolSourceResponse:
    try:
        result = container.require(
            AppKey.TOOL_SOURCE_COMMAND_SERVICE,
        ).update_source(source_id, _source_record_from_request(payload))
    except ToolValidationError as exc:
        status_code = 404 if "does not exist" in str(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from None
    return _source_response(result.source)


@router.get(
    "/sources/{source_id}/discovery-runs",
    response_model=list[ToolSourceDiscoveryRunResponse],
)
def list_tool_source_discovery_runs(
    source_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
    limit: int = 20,
) -> list[ToolSourceDiscoveryRunResponse]:
    runs = container.require(
        AppKey.TOOL_SOURCE_QUERY_SERVICE,
    ).list_discovery_runs(source_id, limit=limit)
    return [_discovery_run_response(run) for run in runs]


@router.post("/sources/{source_id}/refresh", response_model=ToolSourceSyncResponse)
def refresh_tool_source(
    source_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> ToolSourceSyncResponse:
    source = container.require(AppKey.TOOL_SOURCE_QUERY_SERVICE).get_source(source_id)
    if source is None:
        raise HTTPException(
            status_code=404,
            detail=f"Tool source '{source_id}' was not found.",
        )
    result = container.require(AppKey.TOOL_SOURCE_COMMAND_SERVICE).sync_source(
        source,
        discovery_service=container.require(AppKey.TOOL_SOURCE_DISCOVERY_SERVICE),
    )
    container.require(AppKey.TOOL_CONFIGURED_RUNTIME_ACTIVATOR).activate_source(
        result.source.source_id,
    )
    return _sync_response(result)


@router.post("/sources/{source_id}/disable", response_model=ToolSourceResponse)
def disable_tool_source(
    source_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> ToolSourceResponse:
    try:
        result = container.require(
            AppKey.TOOL_SOURCE_COMMAND_SERVICE,
        ).disable_source(source_id)
    except ToolValidationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    return _source_response(result.source)


@router.post("/sources/{source_id}/restore", response_model=ToolSourceResponse)
def restore_tool_source(
    source_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> ToolSourceResponse:
    try:
        result = container.require(
            AppKey.TOOL_SOURCE_COMMAND_SERVICE,
        ).restore_source(source_id)
    except ToolValidationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    return _source_response(result.source)


@router.delete("/sources/{source_id}", response_model=ToolSourceResponse)
def delete_tool_source(
    source_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> ToolSourceResponse:
    try:
        result = container.require(
            AppKey.TOOL_SOURCE_COMMAND_SERVICE,
        ).delete_source(source_id)
    except ToolValidationError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    return _source_response(result.source)


@router.get("/functions", response_model=list[ToolFunctionResponse])
def list_tool_functions(
    container: Annotated[AppContainer, Depends(get_container)],
    source_id: str | None = None,
    status: str | None = None,
) -> list[ToolFunctionResponse]:
    functions = container.require(AppKey.TOOL_SOURCE_QUERY_SERVICE).list_functions(
        source_id=source_id,
        status=status,
    )
    return [_function_response(function) for function in functions]


@router.get("/functions/{function_id}", response_model=ToolFunctionResponse)
def get_tool_function(
    function_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> ToolFunctionResponse:
    function = container.require(AppKey.TOOL_SOURCE_QUERY_SERVICE).get_function(
        function_id,
    )
    if function is None:
        raise HTTPException(
            status_code=404,
            detail=f"Tool function '{function_id}' was not found.",
        )
    return _function_response(function)


@router.get("/provider-backends", response_model=list[ToolProviderBackendResponse])
def list_tool_provider_backends(
    container: Annotated[AppContainer, Depends(get_container)],
    source_id: str | None = None,
    capability: str | None = None,
    status: str | None = None,
) -> list[ToolProviderBackendResponse]:
    backends = container.require(
        AppKey.TOOL_SOURCE_QUERY_SERVICE,
    ).list_provider_backends(
        source_id=source_id,
        capability=capability,
        status=status,
    )
    service = container.require(AppKey.TOOL_SERVICE)
    return [
        _provider_backend_response(
            backend,
            readiness=_provider_backend_readiness_payload(service, backend),
        )
        for backend in backends
    ]


@router.get(
    "/provider-backends/{backend_id}",
    response_model=ToolProviderBackendResponse,
)
def get_tool_provider_backend(
    backend_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> ToolProviderBackendResponse:
    backend = container.require(
        AppKey.TOOL_SOURCE_QUERY_SERVICE,
    ).get_provider_backend(backend_id)
    if backend is None:
        raise HTTPException(
            status_code=404,
            detail=f"Tool provider backend '{backend_id}' was not found.",
        )
    return _provider_backend_response(
        backend,
        readiness=_provider_backend_readiness_payload(
            container.require(AppKey.TOOL_SERVICE),
            backend,
        ),
    )


@router.post("/functions/{function_id}/enable", response_model=ToolFunctionResponse)
def enable_tool_function(
    function_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> ToolFunctionResponse:
    return _set_tool_function_enabled(
        container,
        function_id=function_id,
        enabled=True,
    )


@router.post("/functions/{function_id}/disable", response_model=ToolFunctionResponse)
def disable_tool_function(
    function_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> ToolFunctionResponse:
    return _set_tool_function_enabled(
        container,
        function_id=function_id,
        enabled=False,
    )


@router.put("/functions/{function_id}/policy", response_model=ToolFunctionResponse)
def update_tool_function_policy(
    function_id: str,
    payload: ToolFunctionPolicyRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> ToolFunctionResponse:
    try:
        result = container.require(
            AppKey.TOOL_FUNCTION_COMMAND_SERVICE,
        ).update_function_policy(
            function_id,
            trust_policy=payload.trust_policy,
            approval_policy=payload.approval_policy,
            credential_binding_overrides=payload.credential_binding_overrides,
            required_effect_overrides=(
                tuple(payload.required_effect_overrides)
                if payload.required_effect_overrides is not None
                else None
            ),
        )
    except ToolValidationError as exc:
        status_code = 404 if "does not exist" in str(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from None
    return _function_response(result.function)


@router.get("", response_model=list[ToolResponse])
def list_tools(
    container: Annotated[AppContainer, Depends(get_container)],
    enabled_only: bool = False,
) -> list[ToolResponse]:
    tools = (
        container.require(AppKey.TOOL_SERVICE).list_enabled_tools()
        if enabled_only
        else container.require(AppKey.TOOL_SERVICE).list_tools()
    )
    return [_to_response(tool) for tool in tools]


@router.get("/{tool_id}/readiness")
def get_tool_readiness(
    tool_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
    agent_id: str | None = Query(default=None),
    run_id: str | None = Query(default=None),
    session_key: str | None = Query(default=None),
    active_session_id: str | None = Query(default=None),
    workspace_dir: str | None = Query(default=None),
) -> dict[str, Any]:
    try:
        return dict(
            container.require(AppKey.TOOL_SERVICE).check_readiness(
                tool_id,
                agent_id=agent_id,
                run_id=run_id,
                session_key=session_key,
                active_session_id=active_session_id,
                workspace_dir=workspace_dir,
            ),
        )
    except ToolNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


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
        arguments=payload.arguments,
    )
    try:
        tool_run = await container.require(AppKey.TOOL_SERVICE).execute(
            ExecuteToolInput(
                tool_id=tool_id,
                arguments=dict(payload.arguments),
                mode=payload.mode,
                strategy=payload.strategy,
                environment=payload.environment,
                run_id=payload.run_id,
            ),
        )
    except ToolNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except ToolExecutionNotAllowedError as exc:
        raise HTTPException(status_code=409, detail=exc.to_payload()) from None
    except (ToolExecutionNotSupportedError, ToolValidationError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return _to_run_response(tool_run)


@router.get("/{tool_id}/runs", response_model=list[ToolRunResponse])
def list_tool_runs(
    tool_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> list[ToolRunResponse]:
    tool_runs = container.require(AppKey.TOOL_SERVICE).list_tool_runs(tool_id=tool_id)
    return [_to_run_response(tool_run) for tool_run in tool_runs]


@router.get("/runs/{run_id}", response_model=ToolRunResponse)
def get_tool_run(
    run_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> ToolRunResponse:
    try:
        return _to_run_response(container.require(AppKey.TOOL_SERVICE).get_tool_run(run_id))
    except ToolRunNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.post("/runs/{run_id}/cancel", response_model=ToolRunResponse)
def cancel_tool_run(
    run_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> ToolRunResponse:
    try:
        return _to_run_response(container.require(AppKey.TOOL_SERVICE).cancel_tool_run(run_id))
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
        original = container.require(AppKey.TOOL_SERVICE).get_tool_run(run_id)
        authorize_tool_run(
            container,
            tool_id=original.tool_id,
            mode=original.target.mode,
            strategy=original.target.strategy,
            environment=original.target.environment,
            interface_name="http",
            arguments=original.input_payload,
        )
        return _to_run_response(await container.require(AppKey.TOOL_SERVICE).retry_tool_run(run_id))
    except ToolRunNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except ToolValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None


@router.post("/workers/prune-expired", response_model=PruneExpiredToolWorkersResponse)
def prune_expired_tool_workers(
    container: Annotated[AppContainer, Depends(get_container)],
    retention_seconds: int = 3600,
) -> PruneExpiredToolWorkersResponse:
    result = container.require(AppKey.TOOL_SERVICE).prune_expired_workers(
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
        source_id=tool.source_id,
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
        runtime_requirement_sets=[
            list(requirement_set)
            for requirement_set in tool.runtime_requirement_sets
        ],
        context_requirements=list(tool.context_requirements),
        credential_requirements=[
            _credential_requirement_set_payload(requirement_set)
            for requirement_set in tool.credential_requirements
        ],
        execution_policy=ToolExecutionPolicyResponse(
            timeout_seconds=tool.execution_policy.timeout_seconds,
            requires_confirmation=tool.execution_policy.requires_confirmation,
            mutates_state=tool.execution_policy.mutates_state,
            supports_parallel=tool.execution_policy.supports_parallel,
            resource_scope=tool.execution_policy.resource_scope,
            serial_group_key=tool.execution_policy.serial_group_key,
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
        definition_origin=tool.definition_origin.value,
        runtime_key=tool.runtime_key,
        enabled=tool.enabled,
    )


def _source_response(source: ToolSourceCatalogRecord) -> ToolSourceResponse:
    return ToolSourceResponse(
        source_id=source.source_id,
        kind=source.kind.value,
        display_name=source.display_name,
        description=source.description,
        config=dict(source.config),
        credential_requirements=[
            _source_credential_requirement_payload(requirement)
            for requirement in source.credential_requirements
        ],
        runtime_requirements=list(source.runtime_requirements),
        status=source.status.value,
        revision=source.revision,
        config_hash=source.config_hash,
        last_discovered_at=format_optional_datetime_utc(source.last_discovered_at),
        last_discovery_status=(
            source.last_discovery_status.value
            if source.last_discovery_status is not None
            else None
        ),
        created_at=format_optional_datetime_utc(source.created_at),
        updated_at=format_optional_datetime_utc(source.updated_at),
    )


def _source_record_from_request(payload: ToolSourceWriteRequest) -> ToolSourceCatalogRecord:
    return ToolSourceCatalogRecord(
        source_id=payload.source_id,
        kind=payload.kind,
        display_name=payload.display_name,
        description=payload.description,
        config=payload.config,
        credential_requirements=tuple(payload.credential_requirements),  # type: ignore[arg-type]
        runtime_requirements=tuple(payload.runtime_requirements),
        status=payload.status,
    )


def _source_credential_requirement_payload(requirement: object) -> dict[str, Any]:
    if isinstance(requirement, dict):
        return dict(requirement)
    return _credential_requirement_set_payload(requirement)  # type: ignore[arg-type]


def _function_response(function: ToolFunctionCatalogRecord) -> ToolFunctionResponse:
    return ToolFunctionResponse(
        function_id=function.function_id,
        source_id=function.source_id,
        stable_key=function.stable_key,
        name=function.name,
        description=function.description,
        input_schema=dict(function.input_schema),
        runtime_kind=function.runtime_kind.value,
        handler_ref=function.handler_ref,
        capabilities=list(function.capabilities),
        kind=_function_kind(function),
        parameters=_function_parameters(function.input_schema),
        tags=_function_tags(function),
        required_effect_ids=list(
            function.required_effect_overrides
            if function.required_effect_overrides is not None
            else function.requirements.required_effect_ids,
        ),
        access_requirement_sets=[
            list(requirement_set)
            for requirement_set in function.requirements.access_requirement_sets
        ],
        runtime_requirement_sets=[
            list(requirement_set)
            for requirement_set in function.requirements.runtime_requirement_sets
        ],
        context_requirements=_function_context_requirements(function),
        credential_requirements=[
            _credential_requirement_set_payload(requirement_set)
            for requirement_set in function.requirements.credential_requirements
        ],
        execution_policy=_function_execution_policy(function),
        execution_support=_function_execution_support(function),
        definition_origin=_function_definition_origin(function),
        runtime_key=_function_runtime_key(function),
        schema_hash=function.schema_hash,
        status=function.status.value,
        enabled=function.enabled,
        revision=function.revision,
        trust_policy=dict(function.trust_policy),
        approval_policy=dict(function.approval_policy),
        credential_binding_overrides=dict(function.credential_binding_overrides),
        required_effect_overrides=(
            list(function.required_effect_overrides)
            if function.required_effect_overrides is not None
            else None
        ),
        metadata=dict(function.metadata),
        created_at=format_optional_datetime_utc(function.created_at),
        updated_at=format_optional_datetime_utc(function.updated_at),
        last_seen_at=format_optional_datetime_utc(function.last_seen_at),
        stale_since=format_optional_datetime_utc(function.stale_since),
        deprecated_at=format_optional_datetime_utc(function.deprecated_at),
    )


def _function_kind(function: ToolFunctionCatalogRecord) -> str:
    return str(function.metadata.get("tool_kind") or "function")


def _function_tags(function: ToolFunctionCatalogRecord) -> list[str]:
    raw_tags = function.metadata.get("tags")
    if not isinstance(raw_tags, list | tuple):
        return []
    return [str(tag).strip() for tag in raw_tags if str(tag).strip()]


def _function_context_requirements(function: ToolFunctionCatalogRecord) -> list[str]:
    raw_values = function.metadata.get("context_requirements")
    if not isinstance(raw_values, list | tuple):
        return []
    return [str(value).strip() for value in raw_values if str(value).strip()]


def _function_parameters(input_schema: dict[str, Any]) -> list[ToolParameterResponse]:
    raw_properties = input_schema.get("properties")
    properties = raw_properties if isinstance(raw_properties, dict) else {}
    raw_required = input_schema.get("required")
    required = {
        str(item).strip()
        for item in raw_required
        if str(item).strip()
    } if isinstance(raw_required, list | tuple) else set()
    parameters: list[ToolParameterResponse] = []
    for name, raw_schema in properties.items():
        if not isinstance(name, str) or not name.strip():
            continue
        schema = raw_schema if isinstance(raw_schema, dict) else {}
        data_type = schema.get("x-crxzipple-data-type") or schema.get("type")
        parameters.append(
            ToolParameterResponse(
                name=name,
                data_type=str(data_type or "string"),
                description=str(schema.get("description") or ""),
                required=name in required,
            ),
        )
    return parameters


def _function_execution_policy(
    function: ToolFunctionCatalogRecord,
) -> ToolExecutionPolicyResponse:
    raw_policy = function.metadata.get("execution_policy")
    policy = raw_policy if isinstance(raw_policy, dict) else {}
    return ToolExecutionPolicyResponse(
        timeout_seconds=max(_optional_int(policy.get("timeout_seconds"), 30), 1),
        requires_confirmation=bool(policy.get("requires_confirmation", False)),
        mutates_state=bool(policy.get("mutates_state", False)),
        supports_parallel=bool(policy.get("supports_parallel", True)),
        resource_scope=_optional_policy_text(policy.get("resource_scope")),
        serial_group_key=_optional_policy_text(policy.get("serial_group_key")),
    )


def _function_execution_support(
    function: ToolFunctionCatalogRecord,
) -> ToolExecutionSupportResponse:
    raw_support = function.metadata.get("execution_support")
    support = raw_support if isinstance(raw_support, dict) else {}
    return ToolExecutionSupportResponse(
        supported_modes=_metadata_string_list(
            support.get("supported_modes"),
            fallback=("inline",),
        ),
        supported_strategies=_metadata_string_list(
            support.get("supported_strategies"),
            fallback=("async",),
        ),
        supported_environments=_metadata_string_list(
            support.get("supported_environments"),
            fallback=("local",),
        ),
    )


def _metadata_string_list(value: object, *, fallback: tuple[str, ...]) -> list[str]:
    if not isinstance(value, list | tuple):
        return list(fallback)
    normalized = [str(item).strip() for item in value if str(item).strip()]
    return list(dict.fromkeys(normalized)) or list(fallback)


def _optional_int(value: object, default: int) -> int:
    try:
        return int(value) if value is not None and value != "" else default
    except (TypeError, ValueError):
        return default


def _optional_policy_text(value: object | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def _function_definition_origin(function: ToolFunctionCatalogRecord) -> str:
    return str(function.metadata.get("definition_origin") or "local_discovery")


def _function_runtime_key(function: ToolFunctionCatalogRecord) -> str | None:
    runtime_key = function.metadata.get("runtime_key")
    if isinstance(runtime_key, str) and runtime_key.strip():
        return runtime_key.strip()
    handler_ref = function.handler_ref.strip()
    return handler_ref or None


def _provider_backend_response(
    backend,
    *,
    readiness: dict[str, Any] | None = None,
) -> ToolProviderBackendResponse:
    return ToolProviderBackendResponse(
        backend_id=backend.backend_id,
        source_id=backend.source_id,
        capability=backend.capability.value,
        display_name=backend.display_name,
        credential_requirements=[
            dict(requirement)
            for requirement in backend.credential_requirements
        ],
        runtime_ref=dict(backend.runtime_ref),
        priority=backend.priority,
        enabled=backend.enabled,
        status=backend.status.value,
        readiness=readiness,
        created_at=format_datetime_utc(backend.created_at),
        updated_at=format_datetime_utc(backend.updated_at),
    )


def _provider_backend_readiness_payload(service: Any, backend: Any) -> dict[str, Any] | None:
    check_readiness = getattr(service, "check_provider_backend_readiness", None)
    if not callable(check_readiness):
        return None
    readiness = check_readiness(backend)
    to_payload = getattr(readiness, "to_payload", None)
    if callable(to_payload):
        payload = to_payload()
        if isinstance(payload, dict):
            return payload
    return None


def _set_tool_function_enabled(
    container: AppContainer,
    *,
    function_id: str,
    enabled: bool,
) -> ToolFunctionResponse:
    try:
        result = container.require(
            AppKey.TOOL_FUNCTION_COMMAND_SERVICE,
        ).set_function_enabled(function_id, enabled=enabled)
    except ToolValidationError as exc:
        status_code = 404 if "does not exist" in str(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from None
    return _function_response(result.function)


def _discovery_run_response(
    run: ToolSourceDiscoveryRunRecord,
) -> ToolSourceDiscoveryRunResponse:
    return ToolSourceDiscoveryRunResponse(
        discovery_run_id=run.discovery_run_id,
        source_id=run.source_id,
        source_revision=run.source_revision,
        config_hash=run.config_hash,
        status=run.status.value,
        discovered_at=format_datetime_utc(run.discovered_at),
        function_count=run.function_count,
        provider_backend_count=run.provider_backend_count,
        error_message=run.error_message,
        metadata=dict(run.metadata),
    )


def _sync_response(result: ToolSourceSyncResult) -> ToolSourceSyncResponse:
    discovery = None
    if result.discovery is not None:
        discovery = ToolSourceDiscoveryRunResponse(
            discovery_run_id="",
            source_id=result.discovery.source_id,
            source_revision=result.source.revision,
            config_hash=result.source.config_hash,
            status=result.discovery.status.value,
            discovered_at=format_datetime_utc(result.discovery.discovered_at),
            function_count=len(result.discovery.candidates),
            provider_backend_count=len(result.discovery.provider_backend_candidates),
            error_message=result.discovery.error_message,
            metadata=dict(result.discovery.metadata),
        )
    return ToolSourceSyncResponse(
        source=_source_response(result.source),
        skipped=result.skipped,
        error_message=result.error_message,
        discovery=discovery,
    )


def _to_run_response(tool_run) -> ToolRunResponse:
    return ToolRunResponse(
        id=tool_run.id,
        tool_id=tool_run.tool_id,
        call_id=tool_run.call_id,
        tool_surface_id=tool_run.tool_surface_id,
        function_id=tool_run.function_id,
        function_revision=tool_run.function_revision,
        source_id=tool_run.source_id,
        source_revision=tool_run.source_revision,
        schema_hash=tool_run.schema_hash,
        target=ToolExecutionTargetResponse(
            mode=tool_run.target.mode.value,
            strategy=tool_run.target.strategy.value,
            environment=tool_run.target.environment.value,
        ),
        status=tool_run.status.value,
        input_payload=dict(tool_run.input_payload),
        metadata=dict(tool_run.metadata),
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
        result_envelope_payload=(
            dict(tool_run.result_envelope_payload)
            if tool_run.result_envelope_payload is not None
            else None
        ),
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
