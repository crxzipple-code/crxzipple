from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.interfaces.runtime_container import AppContainer
from crxzipple.modules.operations.interfaces.http_models import (
    LlmInvocationDetailResponse,
    MemoryFileDetailResponse,
    ToolRunDetailResponse,
)
from crxzipple.modules.operations.interfaces.http_projection_helpers import (
    projection_detail_payload,
)

router = APIRouter()


@router.get(
    "/tool/runs/{run_id}/detail",
    response_model=ToolRunDetailResponse,
)
def get_tool_run_operations_detail(
    run_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> ToolRunDetailResponse:
    return ToolRunDetailResponse(
        **projection_detail_payload(
            container,
            module="tool",
            kind="tool_run_detail",
            query_key=run_id,
        ),
    )


@router.get(
    "/llm/invocations/{invocation_id}/detail",
    response_model=LlmInvocationDetailResponse,
)
def get_llm_invocation_operations_detail(
    invocation_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> LlmInvocationDetailResponse:
    return LlmInvocationDetailResponse(
        **projection_detail_payload(
            container,
            module="llm",
            kind="llm_invocation_detail",
            query_key=invocation_id,
        ),
    )


@router.get(
    "/memory/files/{file_id:path}/detail",
    response_model=MemoryFileDetailResponse,
)
def get_memory_file_operations_detail(
    file_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> MemoryFileDetailResponse:
    return MemoryFileDetailResponse(
        **projection_detail_payload(
            container,
            module="memory",
            kind="memory_file_detail",
            query_key=file_id,
        ),
    )
