from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.interfaces.http.turns import (
    CancelTurnRequest,
    CreateTurnRequest,
    ResolveApprovalRequestRequest,
    RuntimeLlmRequestPreviewDTO,
    RuntimeLlmRequestPreviewResponse,
    TurnResponse,
    cancel_turn,
    create_turn,
    resolve_turn_approval,
)
from crxzipple.interfaces.http.ui_models import (
    TurnStepResponse,
    WorkbenchHomeResponse,
    WorkbenchRunResponse,
)
from crxzipple.interfaces.runtime_container import AppContainer, AppKey
from crxzipple.modules.llm.domain import LlmInvocationNotFoundError
from crxzipple.modules.llm.interfaces.http_models import (
    LlmInvocationRuntimeRequestPreviewResponse,
)
from crxzipple.modules.llm.interfaces.http_response_mapping import (
    to_invocation_llm_request_preview_response,
)
from crxzipple.modules.orchestration.domain import (
    OrchestrationRunNotFoundError,
    OrchestrationValidationError,
)
from crxzipple.modules.workbench.interfaces.http_catalog import (
    router as catalog_router,
)
from crxzipple.modules.workbench.interfaces.http_context import (
    router as context_router,
)
from crxzipple.modules.workbench.interfaces.http_dependencies import (
    not_found,
    workbench_provider,
)
from crxzipple.modules.workbench.interfaces.http_linked_entities import (
    router as linked_entities_router,
)
from crxzipple.modules.workbench.interfaces.http_trace import (
    router as trace_router,
)


router = APIRouter()
router.include_router(catalog_router)
router.include_router(context_router)
router.include_router(linked_entities_router)
router.include_router(trace_router)


@router.post(
    "/workbench/turns",
    response_model=TurnResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_workbench_turn(
    payload: CreateTurnRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> TurnResponse:
    return create_turn(payload, container)


@router.post("/workbench/turns/{run_id}/cancel", response_model=TurnResponse)
def cancel_workbench_turn(
    run_id: str,
    payload: CancelTurnRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> TurnResponse:
    return cancel_turn(run_id, payload, container)


@router.post(
    "/workbench/turns/{run_id}/approvals/{request_id}",
    response_model=TurnResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def resolve_workbench_turn_approval(
    run_id: str,
    request_id: str,
    payload: ResolveApprovalRequestRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> TurnResponse:
    return resolve_turn_approval(run_id, request_id, payload, container)


@router.get("/workbench/home", response_model=WorkbenchHomeResponse)
def get_workbench_home(
    container: Annotated[AppContainer, Depends(get_container)],
    run_id: str | None = Query(default=None),
    session_key: str | None = Query(default=None),
) -> WorkbenchHomeResponse:
    view = workbench_provider(container).get_home_view(
        run_id=run_id,
        session_key=session_key,
    )
    return WorkbenchHomeResponse.from_view(view)


@router.get("/workbench/runs/{run_id}", response_model=WorkbenchRunResponse)
def get_workbench_run(
    run_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
    include_timeline: bool = Query(default=True),
) -> WorkbenchRunResponse:
    try:
        view = workbench_provider(container).get_run_view(
            run_id,
            include_timeline=include_timeline,
        )
    except OrchestrationRunNotFoundError as exc:
        raise not_found(exc) from None
    return WorkbenchRunResponse.from_view(view)


@router.get("/workbench/runs/{run_id}/steps", response_model=list[TurnStepResponse])
def list_workbench_run_steps(
    run_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
    turn_id: str | None = Query(default=None),
) -> list[TurnStepResponse]:
    try:
        views = workbench_provider(container).list_step_views(
            run_id,
            turn_id=turn_id,
        )
    except OrchestrationRunNotFoundError as exc:
        raise not_found(exc) from None
    return [TurnStepResponse.from_view(view) for view in views]


@router.get(
    "/workbench/runs/{run_id}/llm-request-preview",
    response_model=RuntimeLlmRequestPreviewResponse,
)
def get_workbench_run_llm_request_preview(
    run_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> RuntimeLlmRequestPreviewResponse:
    try:
        preview = container.require(
            AppKey.ORCHESTRATION_INSPECTION_SERVICE,
        ).preview_runtime_llm_request(run_id)
    except OrchestrationRunNotFoundError as exc:
        raise not_found(exc) from None
    except OrchestrationValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return RuntimeLlmRequestPreviewResponse.from_dto(
        RuntimeLlmRequestPreviewDTO.from_value(
            run_id=run_id,
            preview=preview,
        ),
    )


@router.get(
    "/workbench/llm-invocations/{invocation_id}/llm-request-preview",
    response_model=LlmInvocationRuntimeRequestPreviewResponse,
)
def get_workbench_invocation_llm_request_preview(
    invocation_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
    run_id: str | None = Query(default=None),
) -> LlmInvocationRuntimeRequestPreviewResponse:
    try:
        invocation = container.require(AppKey.LLM_SERVICE).get_invocation(invocation_id)
    except LlmInvocationNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    return to_invocation_llm_request_preview_response(invocation, run_id=run_id)
