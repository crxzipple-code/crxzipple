from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.interfaces.http.ui_models import WorkbenchLinkedEntityDetailResponse
from crxzipple.interfaces.runtime_container import AppContainer, AppKey
from crxzipple.modules.llm.domain import (
    LlmInvocationNotFoundError,
    LlmResponseItemNotFoundError,
)
from crxzipple.modules.session.domain import SessionItemNotFoundError
from crxzipple.modules.tool.domain import ToolRunNotFoundError
from crxzipple.modules.workbench.application import (
    llm_invocation_detail,
    llm_response_item_detail,
    session_item_detail,
    tool_run_detail,
)


router = APIRouter()


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
