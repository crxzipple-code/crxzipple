from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.interfaces.http.ui_models import (
    TraceEventResponse,
    TraceSummaryResponse,
    TurnStepResponse,
    WorkbenchHomeResponse,
    WorkbenchLinkedEntityDetailResponse,
    WorkbenchRunResponse,
)
from crxzipple.interfaces.runtime_container import AppContainer, AppKey
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
from crxzipple.modules.context_workspace.application import ContextActionInput
from crxzipple.modules.context_workspace.domain import (
    ContextActionNotAllowedError,
    ContextActor,
    ContextNodeNotFoundError,
    ContextSnapshotNotFoundError,
    ContextWorkspaceNotFoundError,
)
from crxzipple.modules.context_workspace.interfaces.http import (
    ContextActionRequest,
    _node_payload as context_node_payload,
    _parse_action as parse_context_action,
    _snapshot_payload as context_snapshot_payload,
    _tree_payload as context_tree_payload,
    _workspace_payload as context_workspace_payload,
)
from crxzipple.modules.llm.interfaces.http import (
    LlmInvocationRuntimeRequestPreviewResponse,
    _to_invocation_llm_request_preview_response,
)
from crxzipple.modules.llm.domain import (
    LlmInvocationNotFoundError,
    LlmResponseItemNotFoundError,
)
from crxzipple.modules.orchestration.domain import OrchestrationRunNotFoundError
from crxzipple.modules.orchestration.domain import OrchestrationValidationError
from crxzipple.modules.session.domain import SessionItemNotFoundError
from crxzipple.modules.tool.domain import ToolRunNotFoundError
from crxzipple.modules.events.application import EventTraceReadModelProvider
from crxzipple.modules.workbench.application import (
    WorkbenchReadModelProvider,
    WorkbenchTraceReadModelProvider,
    llm_invocation_detail,
    llm_response_item_detail,
    session_item_detail,
    tool_run_detail,
)


router = APIRouter()


class WorkbenchToolExecutionPolicyResponse(BaseModel):
    timeout_seconds: int
    requires_confirmation: bool
    mutates_state: bool


class WorkbenchToolSummaryResponse(BaseModel):
    id: str
    name: str
    description: str
    kind: str
    tags: list[str] = Field(default_factory=list)
    required_effect_ids: list[str] = Field(default_factory=list)
    execution_policy: WorkbenchToolExecutionPolicyResponse
    enabled: bool


class WorkbenchAgentLlmRoutingPolicyResponse(BaseModel):
    default_llm_id: str
    fallback_llm_ids: list[str] = Field(default_factory=list)
    image_llm_id: str | None = None
    document_llm_id: str | None = None


class WorkbenchAgentMemoryResponse(BaseModel):
    enabled: bool = False
    scope_ref: str | None = None
    access: str = "private"


class WorkbenchAgentProfileResponse(BaseModel):
    id: str
    name: str
    description: str
    enabled: bool
    llm_routing_policy: WorkbenchAgentLlmRoutingPolicyResponse
    memory: WorkbenchAgentMemoryResponse | None = None


class WorkbenchLlmProfileResponse(BaseModel):
    id: str
    provider: str
    api_family: str
    model_name: str
    model_family: str
    capabilities: list[str] = Field(default_factory=list)
    enabled: bool


def _workbench_provider(container: AppContainer) -> WorkbenchReadModelProvider:
    return WorkbenchReadModelProvider(
        run_query=container.require(AppKey.ORCHESTRATION_RUN_QUERY_SERVICE),
        tool_query=container.require(AppKey.TOOL_QUERY_SERVICE),
        artifact_query=container.require(AppKey.ARTIFACT_SERVICE),
        llm_query=container.require(AppKey.LLM_SERVICE),
        agent_query=container.require(AppKey.AGENT_SERVICE),
        session_query=container.require(AppKey.SESSION_SERVICE),
    )


@router.get("/workbench/tools", response_model=list[WorkbenchToolSummaryResponse])
def list_workbench_tools(
    container: Annotated[AppContainer, Depends(get_container)],
    enabled_only: bool = Query(default=True),
) -> list[WorkbenchToolSummaryResponse]:
    tool_query = container.require(AppKey.TOOL_QUERY_SERVICE)
    tools = tool_query.list_enabled_tools() if enabled_only else tool_query.list_tools()
    return [
        WorkbenchToolSummaryResponse(
            id=tool.id,
            name=tool.name,
            description=tool.description,
            kind=tool.kind.value,
            tags=list(tool.tags),
            required_effect_ids=list(tool.required_effect_ids),
            execution_policy=WorkbenchToolExecutionPolicyResponse(
                timeout_seconds=tool.execution_policy.timeout_seconds,
                requires_confirmation=tool.execution_policy.requires_confirmation,
                mutates_state=tool.execution_policy.mutates_state,
            ),
            enabled=tool.enabled,
        )
        for tool in tools
    ]


@router.get("/workbench/agents", response_model=list[WorkbenchAgentProfileResponse])
def list_workbench_agents(
    container: Annotated[AppContainer, Depends(get_container)],
) -> list[WorkbenchAgentProfileResponse]:
    return [
        WorkbenchAgentProfileResponse(
            id=profile.id,
            name=profile.name,
            description="",
            enabled=profile.enabled,
            llm_routing_policy=WorkbenchAgentLlmRoutingPolicyResponse(
                default_llm_id=profile.llm_routing_policy.default_llm_id,
                fallback_llm_ids=list(profile.llm_routing_policy.fallback_llm_ids),
                image_llm_id=profile.llm_routing_policy.image_llm_id,
                document_llm_id=profile.llm_routing_policy.document_llm_id,
            ),
            memory=WorkbenchAgentMemoryResponse(
                enabled=profile.memory.enabled,
                scope_ref=profile.memory.scope_ref,
                access=profile.memory.access,
            ),
        )
        for profile in container.require(AppKey.AGENT_SERVICE).list_profiles()
    ]


@router.get("/workbench/models", response_model=list[WorkbenchLlmProfileResponse])
def list_workbench_models(
    container: Annotated[AppContainer, Depends(get_container)],
) -> list[WorkbenchLlmProfileResponse]:
    return [
        WorkbenchLlmProfileResponse(
            id=profile.id,
            provider=profile.provider.value,
            api_family=profile.api_family.value,
            model_name=profile.model_name,
            model_family=profile.model_family.value,
            capabilities=[capability.value for capability in profile.capabilities],
            enabled=profile.enabled,
        )
        for profile in container.require(AppKey.LLM_SERVICE).list_profiles()
    ]


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


def _not_found(exc: OrchestrationRunNotFoundError) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc))


def _context_not_found(
    exc: (
        ContextSnapshotNotFoundError
        | ContextWorkspaceNotFoundError
        | ContextNodeNotFoundError
    ),
) -> HTTPException:
    return HTTPException(status_code=404, detail=str(exc))


def _trace_provider(container: AppContainer) -> WorkbenchTraceReadModelProvider:
    if container.require(AppKey.EVENTS_SERVICE) is None:
        raise HTTPException(status_code=503, detail="Event service is not available.")
    return WorkbenchTraceReadModelProvider(
        trace_query=EventTraceReadModelProvider(
            events_service=container.require(AppKey.EVENTS_SERVICE),
            definition_registry=container.require(AppKey.EVENT_DEFINITION_REGISTRY),
        ),
        run_query=container.require(AppKey.ORCHESTRATION_RUN_QUERY_SERVICE),
        context_slice_builder=container.require(AppKey.CONTEXT_SLICE_BUILDER),
    )


@router.get("/workbench/home", response_model=WorkbenchHomeResponse)
def get_workbench_home(
    container: Annotated[AppContainer, Depends(get_container)],
    run_id: str | None = Query(default=None),
    session_key: str | None = Query(default=None),
) -> WorkbenchHomeResponse:
    view = _workbench_provider(container).get_home_view(
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
        view = _workbench_provider(container).get_run_view(
            run_id,
            include_timeline=include_timeline,
        )
    except OrchestrationRunNotFoundError as exc:
        raise _not_found(exc) from None
    return WorkbenchRunResponse.from_view(view)


@router.get("/workbench/runs/{run_id}/steps", response_model=list[TurnStepResponse])
def list_workbench_run_steps(
    run_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
    turn_id: str | None = Query(default=None),
) -> list[TurnStepResponse]:
    try:
        views = _workbench_provider(container).list_step_views(
            run_id,
            turn_id=turn_id,
        )
    except OrchestrationRunNotFoundError as exc:
        raise _not_found(exc) from None
    return [TurnStepResponse.from_view(view) for view in views]


@router.get("/workbench/context-tree/by-session/{session_key}")
def get_workbench_context_tree(
    session_key: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, object]:
    try:
        view = container.require(AppKey.CONTEXT_TREE_SERVICE).list_tree(session_key)
    except ContextWorkspaceNotFoundError as exc:
        raise _context_not_found(exc) from None
    return context_tree_payload(view.workspace, view.nodes, view.estimate)


@router.post("/workbench/context-tree/by-session/{session_key}/nodes/{node_id}/actions/{action}")
def apply_workbench_context_action(
    session_key: str,
    node_id: str,
    action: str,
    payload: ContextActionRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, object]:
    resolved_action = parse_context_action(action)
    try:
        result = container.require(AppKey.CONTEXT_TREE_SERVICE).apply_action(
            ContextActionInput(
                session_key=session_key,
                node_id=node_id,
                action=resolved_action,
                actor=ContextActor(
                    kind=payload.actor_kind,
                    actor_id=payload.actor_id,
                ),
                run_id=payload.run_id,
                payload=payload.payload,
            ),
        )
    except (ContextWorkspaceNotFoundError, ContextNodeNotFoundError) as exc:
        raise _context_not_found(exc) from None
    except ContextActionNotAllowedError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return {
        "workspace": context_workspace_payload(result.workspace),
        "node": context_node_payload(result.node),
        "action": result.action.value,
        "operation_id": result.operation_id,
    }


@router.get("/workbench/context-snapshots/runs/{run_id}")
def get_workbench_context_snapshot(
    run_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
    include_debug_body: Annotated[bool, Query()] = False,
) -> dict[str, object]:
    try:
        snapshot = container.require(
            AppKey.CONTEXT_OBSERVATION_SNAPSHOT_SERVICE,
        ).get_snapshot_by_run(run_id)
    except ContextSnapshotNotFoundError as exc:
        raise _context_not_found(exc) from None
    return {
        "snapshot": context_snapshot_payload(
            snapshot,
            include_debug_body=include_debug_body,
        ),
    }


@router.get("/workbench/context-snapshots/{snapshot_id}")
def get_workbench_context_snapshot_by_id(
    snapshot_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
    include_debug_body: Annotated[bool, Query()] = False,
) -> dict[str, object]:
    try:
        snapshot = container.require(
            AppKey.CONTEXT_OBSERVATION_SNAPSHOT_SERVICE,
        ).get_snapshot(snapshot_id)
    except ContextSnapshotNotFoundError as exc:
        raise _context_not_found(exc) from None
    return {
        "snapshot": context_snapshot_payload(
            snapshot,
            include_debug_body=include_debug_body,
        ),
    }


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
        raise _not_found(exc) from None
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
    return _to_invocation_llm_request_preview_response(invocation, run_id=run_id)


@router.get(
    "/workbench/linked-entities/{entity_type}/{entity_id}",
    response_model=WorkbenchLinkedEntityDetailResponse,
)
def get_workbench_linked_entity_detail(
    entity_type: str,
    entity_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> WorkbenchLinkedEntityDetailResponse:
    if entity_type in {"llm_response_item", "llm_response_item_id"}:
        llm_service = container.require(AppKey.LLM_SERVICE)
        try:
            item = llm_service.get_response_item(entity_id)
        except LlmResponseItemNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None
        return WorkbenchLinkedEntityDetailResponse.from_view(
            llm_response_item_detail(item),
        )
    if entity_type in {"llm_invocation", "llm_invocation_id"}:
        llm_service = container.require(AppKey.LLM_SERVICE)
        try:
            invocation = llm_service.get_invocation(entity_id)
        except LlmInvocationNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None
        return WorkbenchLinkedEntityDetailResponse.from_view(
            llm_invocation_detail(invocation, fallback_id=entity_id),
        )
    if entity_type == "session_item":
        session_service = container.require(AppKey.SESSION_SERVICE)
        try:
            item = session_service.get_item(entity_id)
        except SessionItemNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None
        return WorkbenchLinkedEntityDetailResponse.from_view(session_item_detail(item))
    if entity_type == "tool_run":
        tool_query = container.require(AppKey.TOOL_QUERY_SERVICE)
        try:
            tool_run = tool_query.get_tool_run(entity_id)
        except ToolRunNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from None
        return WorkbenchLinkedEntityDetailResponse.from_view(tool_run_detail(tool_run))
    raise HTTPException(status_code=404, detail=f"Unsupported entity type '{entity_type}'.")


@router.get("/trace/{trace_id}", response_model=TraceSummaryResponse)
def get_trace_summary(
    trace_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
    focus_id: str | None = Query(default=None),
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> TraceSummaryResponse:
    view = _trace_provider(container).get_trace_summary(
        trace_id,
        focus_id=focus_id,
        limit=limit,
    )
    return TraceSummaryResponse.from_view(view)


@router.get("/trace/{trace_id}/events", response_model=list[TraceEventResponse])
def list_trace_events(
    trace_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
    focus_id: str | None = Query(default=None),
    limit: Annotated[int, Query(ge=1, le=500)] = 200,
) -> list[TraceEventResponse]:
    views = _trace_provider(container).list_trace_events(
        trace_id,
        focus_id=focus_id,
        limit=limit,
    )
    return [TraceEventResponse.from_view(view) for view in views]
