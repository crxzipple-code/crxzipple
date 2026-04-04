from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from crxzipple.bootstrap import AppContainer
from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.modules.browser.domain import BrowserValidationError

from .profile_payloads import build_profile_diagnostics_payload
from .profile_payloads import build_profiles_payload
from .requests import BrowserControlRequest, BrowserPageActionRequest


router = APIRouter()


class BrowserControlRequestBody(BaseModel):
    profile_name: str | None = None
    kind: str = Field(min_length=1)
    target_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    timeout_ms: int | None = Field(default=None, ge=1)


class BrowserPageActionRequestBody(BaseModel):
    profile_name: str | None = None
    kind: str = Field(min_length=1)
    target_id: str | None = None
    ref: str | None = None
    selector: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    timeout_ms: int | None = Field(default=None, ge=1)


class BrowserProfileCreateRequestBody(BaseModel):
    name: str = Field(min_length=1)
    driver: str = Field(default="managed", min_length=1)
    cdp_url: str | None = None
    cdp_port: int | None = Field(default=None, ge=1)
    user_data_dir: str | None = None
    attach_only: bool = False
    set_as_default: bool = False


class BrowserProfileUpdateRequestBody(BaseModel):
    driver: str | None = Field(default=None, min_length=1)
    cdp_url: str | None = None
    cdp_port: int | None = Field(default=None, ge=1)
    user_data_dir: str | None = None
    attach_only: bool | None = None
    clear_cdp_url: bool = False
    clear_cdp_port: bool = False
    clear_user_data_dir: bool = False
    set_as_default: bool | None = None


class BrowserDefaultProfileRequestBody(BaseModel):
    profile_name: str = Field(min_length=1)


def _default_profile(container: AppContainer) -> str:
    return container.browser_system_config_store.load().default_profile


def _system_config(container: AppContainer):  # noqa: ANN001
    return container.browser_system_config_store.load()


def _profiles_payload(
    container: AppContainer,
    system_config=None,  # noqa: ANN001
) -> dict[str, object]:
    return build_profiles_payload(container, system_config=system_config)


def _profile_update_kwargs(
    payload: BrowserProfileUpdateRequestBody,
) -> dict[str, object]:
    updates: dict[str, object] = {}
    provided_fields = payload.model_fields_set

    if payload.clear_cdp_url and "cdp_url" in provided_fields and payload.cdp_url is not None:
        raise BrowserValidationError("cdp_url cannot be provided together with clear_cdp_url.")
    if payload.clear_cdp_port and "cdp_port" in provided_fields and payload.cdp_port is not None:
        raise BrowserValidationError("cdp_port cannot be provided together with clear_cdp_port.")
    if (
        payload.clear_user_data_dir
        and "user_data_dir" in provided_fields
        and payload.user_data_dir is not None
    ):
        raise BrowserValidationError(
            "user_data_dir cannot be provided together with clear_user_data_dir.",
        )

    if "driver" in provided_fields and payload.driver is not None:
        updates["driver"] = payload.driver
    if "cdp_url" in provided_fields:
        updates["cdp_url"] = payload.cdp_url
    if "cdp_port" in provided_fields:
        updates["cdp_port"] = payload.cdp_port
    if "user_data_dir" in provided_fields:
        updates["user_data_dir"] = payload.user_data_dir
    if "attach_only" in provided_fields and payload.attach_only is not None:
        updates["attach_only"] = payload.attach_only
    if "set_as_default" in provided_fields:
        updates["set_as_default"] = payload.set_as_default

    if payload.clear_cdp_url:
        updates["cdp_url"] = None
    if payload.clear_cdp_port:
        updates["cdp_port"] = None
    if payload.clear_user_data_dir:
        updates["user_data_dir"] = None

    return updates


@router.get("/profiles")
def list_profiles(
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, object]:
    return _profiles_payload(container)


@router.get("/profiles/{profile_name}/diagnostics")
def diagnose_profile(
    profile_name: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, object]:
    try:
        return build_profile_diagnostics_payload(container, profile_name=profile_name)
    except BrowserValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/profiles")
def create_profile(
    payload: BrowserProfileCreateRequestBody,
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, object]:
    try:
        system_config = container.browser_profile_admin_service.create_profile(
            name=payload.name,
            driver=payload.driver,
            cdp_url=payload.cdp_url,
            cdp_port=payload.cdp_port,
            user_data_dir=payload.user_data_dir,
            attach_only=payload.attach_only,
            set_as_default=payload.set_as_default,
        )
    except BrowserValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _profiles_payload(container, system_config=system_config)


@router.post("/profiles/default")
def set_default_profile(
    payload: BrowserDefaultProfileRequestBody,
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, object]:
    try:
        system_config = container.browser_profile_admin_service.set_default_profile(
            profile_name=payload.profile_name,
        )
    except BrowserValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _profiles_payload(container, system_config=system_config)


@router.put("/profiles/{profile_name}")
def update_profile(
    profile_name: str,
    payload: BrowserProfileUpdateRequestBody,
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, object]:
    try:
        system_config = container.browser_profile_admin_service.update_profile(
            profile_name=profile_name,
            **_profile_update_kwargs(payload),
        )
    except BrowserValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _profiles_payload(container, system_config=system_config)


@router.delete("/profiles/{profile_name}")
def delete_profile(
    profile_name: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, object]:
    try:
        system_config = container.browser_profile_admin_service.delete_profile(
            profile_name=profile_name,
        )
    except BrowserValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _profiles_payload(container, system_config=system_config)


@router.post("/control")
def execute_control(
    payload: BrowserControlRequestBody,
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, Any]:
    try:
        result = container.browser_facade.execute(
            BrowserControlRequest(
                profile_name=payload.profile_name or _default_profile(container),
                kind=payload.kind,
                target_id=payload.target_id,
                payload=payload.payload,
                timeout_ms=payload.timeout_ms,
            ),
        )
    except BrowserValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return container.browser_result_serializer.serialize(result)


@router.post("/actions")
def execute_page_action(
    payload: BrowserPageActionRequestBody,
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, Any]:
    try:
        result = container.browser_facade.execute(
            BrowserPageActionRequest(
                profile_name=payload.profile_name or _default_profile(container),
                kind=payload.kind,
                target_id=payload.target_id,
                ref=payload.ref,
                selector=payload.selector,
                payload=payload.payload,
                timeout_ms=payload.timeout_ms,
            ),
        )
    except BrowserValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return container.browser_result_serializer.serialize(result)
