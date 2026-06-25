from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.interfaces.runtime_container import AppContainer
from crxzipple.modules.operations.interfaces.http_models import (
    OperationsModuleOverviewResponse,
    OperationsModulePageResponse,
)
from crxzipple.modules.operations.interfaces.http_projection_helpers import (
    module_overviews_response,
    projection_overview_response,
    projection_response,
)

router = APIRouter()


@router.get(
    "/orchestration/overview",
    response_model=OperationsModuleOverviewResponse,
)
def get_orchestration_operations_overview(
    container: Annotated[AppContainer, Depends(get_container)],
) -> OperationsModuleOverviewResponse:
    return projection_overview_response(container, "orchestration")


@router.get(
    "/browser/overview",
    response_model=OperationsModuleOverviewResponse,
)
def get_browser_operations_overview(
    container: Annotated[AppContainer, Depends(get_container)],
) -> OperationsModuleOverviewResponse:
    return projection_overview_response(container, "browser")


@router.get("/modules", response_model=list[OperationsModuleOverviewResponse])
def list_operations_module_overviews(
    container: Annotated[AppContainer, Depends(get_container)],
) -> list[OperationsModuleOverviewResponse]:
    return module_overviews_response(container)


@router.get("/{module}", response_model=OperationsModulePageResponse)
def get_operations_module(
    module: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> OperationsModulePageResponse:
    return projection_response(
        container,
        module=module,
        response_cls=OperationsModulePageResponse,
    )


@router.get("/{module}/overview", response_model=OperationsModuleOverviewResponse)
def get_operations_module_overview(
    module: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> OperationsModuleOverviewResponse:
    return projection_overview_response(container, module)
