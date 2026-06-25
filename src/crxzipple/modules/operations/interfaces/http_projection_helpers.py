from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from crxzipple.interfaces.runtime_container import AppContainer, AppKey
from crxzipple.modules.operations.application.read_models.projection_payloads import (
    OperationsProjectionNotFoundError,
    OperationsProjectionUnavailableError,
    detail_projection_payload,
    list_module_overview_payloads,
    module_overview_payload,
    module_page_payload,
    module_projection_payload,
)
from crxzipple.modules.operations.interfaces.http_models import (
    OperationsModuleOverviewResponse,
)


def module_overviews_response(
    container: AppContainer,
) -> list[OperationsModuleOverviewResponse]:
    try:
        payloads = list_module_overview_payloads(
            container.require(AppKey.OPERATIONS_PROJECTION_STORE),
        )
    except OperationsProjectionUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return [OperationsModuleOverviewResponse(**payload) for payload in payloads]


def projection_overview_response(
    container: AppContainer,
    module: str,
) -> OperationsModuleOverviewResponse:
    try:
        payload = module_overview_payload(
            container.require(AppKey.OPERATIONS_PROJECTION_STORE),
            module,
        )
    except OperationsProjectionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except OperationsProjectionUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return OperationsModuleOverviewResponse(**payload)


def projection_response(
    container: AppContainer,
    *,
    module: str,
    response_cls: type[Any],
    kind: str = "page",
    table: str | None = None,
    filters: dict[str, Any] | None = None,
) -> Any:
    projection_store = container.require(AppKey.OPERATIONS_PROJECTION_STORE)
    try:
        if kind == "page":
            payload = module_page_payload(
                projection_store,
                module=module,
                table=table,
                filters=filters,
            )
        else:
            payload = module_projection_payload(
                projection_store,
                module=module,
                kind=kind,
            )
    except OperationsProjectionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except OperationsProjectionUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return response_cls(**payload)


def projection_detail_payload(
    container: AppContainer,
    *,
    module: str,
    kind: str,
    query_key: str,
) -> dict[str, Any]:
    try:
        return detail_projection_payload(
            container.require(AppKey.OPERATIONS_PROJECTION_STORE),
            module=module,
            kind=kind,
            query_key=query_key,
        )
    except OperationsProjectionNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
