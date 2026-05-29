from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from crxzipple.interfaces.runtime_container import AppContainer, AppKey
from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.modules.mobile.domain import MobileExecutionError, MobileValidationError

from .requests import MobileActionRequest, MobileControlRequest


router = APIRouter()


class MobileControlRequestBody(BaseModel):
    device_name: str | None = None
    kind: str = Field(min_length=1)
    payload: dict[str, Any] = Field(default_factory=dict)
    timeout_ms: int | None = Field(default=None, ge=1)


class MobileActionRequestBody(BaseModel):
    device_name: str | None = None
    kind: str = Field(min_length=1)
    ref: str | None = None
    selector: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    timeout_ms: int | None = Field(default=None, ge=1)


def _default_device(container: AppContainer) -> str | None:
    return container.require(AppKey.MOBILE_SYSTEM_CONFIG_STORE).load().default_device


@router.post("/control")
def execute_control(
    payload: MobileControlRequestBody,
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, Any]:
    try:
        result = container.require(AppKey.MOBILE_FACADE).execute(
            MobileControlRequest(
                device_name=payload.device_name or _default_device(container),
                kind=payload.kind,
                payload=payload.payload,
                timeout_ms=payload.timeout_ms,
            ),
        )
    except (MobileValidationError, MobileExecutionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return container.require(AppKey.MOBILE_RESULT_SERIALIZER).serialize(result)


@router.post("/actions")
def execute_action(
    payload: MobileActionRequestBody,
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, Any]:
    try:
        result = container.require(AppKey.MOBILE_FACADE).execute(
            MobileActionRequest(
                device_name=payload.device_name or _default_device(container),
                kind=payload.kind,
                ref=payload.ref,
                selector=payload.selector,
                payload=payload.payload,
                timeout_ms=payload.timeout_ms,
            ),
        )
    except (MobileValidationError, MobileExecutionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return container.require(AppKey.MOBILE_RESULT_SERIALIZER).serialize(result)
