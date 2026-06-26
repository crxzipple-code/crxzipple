from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, status

from crxzipple.interfaces.runtime_container import AppContainer, AppKey
from crxzipple.interfaces.authorization import authorize_tool_run
from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.modules.tool.application import (
    ExecuteToolInput,
)
from crxzipple.modules.tool.domain.exceptions import (
    ToolExecutionNotAllowedError,
    ToolExecutionNotSupportedError,
    ToolNotFoundError,
    ToolRunNotFoundError,
    ToolValidationError,
)
from crxzipple.modules.tool.interfaces.http_models import (
    ExecuteToolRunRequest,
    PruneExpiredToolWorkersResponse,
    ToolFunctionPolicyRequest,
    ToolFunctionResponse,
    ToolProviderBackendResponse,
    ToolResponse,
    ToolRootResponse,
    ToolRunResponse,
    ToolSourceDiscoveryRunResponse,
    ToolSourceResponse,
    ToolSourceSyncResponse,
    ToolSourceWriteRequest,
)
from crxzipple.modules.tool.interfaces.http_payloads import (
    provider_backend_readiness_payload,
    tool_discovery_run_response,
    tool_function_response,
    tool_provider_backend_response,
    tool_response,
    tool_run_response,
    tool_source_record_from_request,
    tool_source_response,
    tool_source_sync_response,
)
from crxzipple.shared.time import (
    format_datetime_utc,
)


router = APIRouter()


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
    return [tool_source_response(source) for source in sources]


@router.post("/sources", response_model=ToolSourceResponse)
def create_tool_source(
    payload: ToolSourceWriteRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> ToolSourceResponse:
    try:
        result = container.require(
            AppKey.TOOL_SOURCE_COMMAND_SERVICE,
        ).create_source(tool_source_record_from_request(payload))
    except ToolValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return tool_source_response(result.source)


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
    return tool_source_response(source)


@router.put("/sources/{source_id}", response_model=ToolSourceResponse)
def update_tool_source(
    source_id: str,
    payload: ToolSourceWriteRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> ToolSourceResponse:
    try:
        result = container.require(
            AppKey.TOOL_SOURCE_COMMAND_SERVICE,
        ).update_source(source_id, tool_source_record_from_request(payload))
    except ToolValidationError as exc:
        status_code = 404 if "does not exist" in str(exc) else 400
        raise HTTPException(status_code=status_code, detail=str(exc)) from None
    return tool_source_response(result.source)


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
    return [tool_discovery_run_response(run) for run in runs]


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
    return tool_source_sync_response(result)


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
    return tool_source_response(result.source)


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
    return tool_source_response(result.source)


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
    return tool_source_response(result.source)


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
    return [tool_function_response(function) for function in functions]


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
    return tool_function_response(function)


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
        tool_provider_backend_response(
            backend,
            readiness=provider_backend_readiness_payload(service, backend),
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
    return tool_provider_backend_response(
        backend,
        readiness=provider_backend_readiness_payload(
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
    return tool_function_response(result.function)


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
    return [tool_response(tool) for tool in tools]


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
    return tool_run_response(tool_run)


@router.get("/{tool_id}/runs", response_model=list[ToolRunResponse])
def list_tool_runs(
    tool_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
    limit: Annotated[int, Query(ge=1, le=1000)] = 100,
) -> list[ToolRunResponse]:
    tool_runs = container.require(AppKey.TOOL_SERVICE).list_tool_runs(
        tool_id=tool_id,
        limit=limit,
    )
    return [tool_run_response(tool_run) for tool_run in tool_runs]


@router.get("/runs/{run_id}", response_model=ToolRunResponse)
def get_tool_run(
    run_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> ToolRunResponse:
    try:
        return tool_run_response(container.require(AppKey.TOOL_SERVICE).get_tool_run(run_id))
    except ToolRunNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None


@router.post("/runs/{run_id}/cancel", response_model=ToolRunResponse)
def cancel_tool_run(
    run_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> ToolRunResponse:
    try:
        return tool_run_response(container.require(AppKey.TOOL_SERVICE).cancel_tool_run(run_id))
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
        return tool_run_response(await container.require(AppKey.TOOL_SERVICE).retry_tool_run(run_id))
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
    return tool_function_response(result.function)
