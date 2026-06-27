from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.interfaces.runtime_container import AppContainer, AppKey
from crxzipple.modules.skills.domain import SkillError
from crxzipple.modules.skills.interfaces.http_errors import raise_skill_http_error
from crxzipple.modules.skills.interfaces.http_models import (
    CreateSkillSourceRequest,
    InstallSkillRequest,
    SkillInstallationResponse,
    SkillInstallResponse,
    SkillSourceMutationResponse,
    SkillSourceResponse,
    SkillSyncRequest,
    SkillSyncResponse,
    UpdateSkillSourceRequest,
)

router = APIRouter()


@router.get("/sources", response_model=list[SkillSourceResponse])
def list_sources(
    container: Annotated[AppContainer, Depends(get_container)],
    workspace_dir: str | None = Query(default=None),
    surface: str = Query(default="interactive"),
) -> list[SkillSourceResponse]:
    try:
        sources = container.require(AppKey.SKILL_MANAGER).list_sources(
            workspace_dir=workspace_dir,
            surface=surface,
        )
    except SkillError as exc:
        raise_skill_http_error(exc)
    return [SkillSourceResponse.from_entity(source) for source in sources]


@router.post(
    "/sources",
    response_model=SkillSourceMutationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_source(
    payload: CreateSkillSourceRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> SkillSourceMutationResponse:
    try:
        result = container.require(AppKey.SKILL_MANAGER).create_source(
            payload.to_application_request(),
        )
    except SkillError as exc:
        raise_skill_http_error(exc)
    return SkillSourceMutationResponse.from_entity(result)


@router.patch("/sources/{source_id}", response_model=SkillSourceMutationResponse)
def update_source(
    source_id: str,
    payload: UpdateSkillSourceRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> SkillSourceMutationResponse:
    try:
        result = container.require(AppKey.SKILL_MANAGER).update_source(
            payload.to_application_request(source_id),
        )
    except SkillError as exc:
        raise_skill_http_error(exc)
    return SkillSourceMutationResponse.from_entity(result)


@router.delete("/sources/{source_id}", response_model=SkillSourceMutationResponse)
def delete_source(
    source_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> SkillSourceMutationResponse:
    try:
        result = container.require(AppKey.SKILL_MANAGER).delete_source(
            source_id=source_id,
        )
    except SkillError as exc:
        raise_skill_http_error(exc)
    return SkillSourceMutationResponse.from_entity(result)


@router.post("/sync", response_model=SkillSyncResponse)
def sync_skills(
    payload: SkillSyncRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> SkillSyncResponse:
    try:
        result = container.require(AppKey.SKILL_MANAGER).sync(
            workspace_dir=payload.workspace_dir,
            source_id=payload.source_id,
            surface=payload.surface,
        )
    except SkillError as exc:
        raise_skill_http_error(exc)
    return SkillSyncResponse.from_entity(result)


@router.get("/installations", response_model=list[SkillInstallationResponse])
def list_installations(
    container: Annotated[AppContainer, Depends(get_container)],
    skill_name: str | None = Query(default=None),
    source_id: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[SkillInstallationResponse]:
    items = container.require(AppKey.SKILL_MANAGER).list_installations(
        skill_name=skill_name,
        source_id=source_id,
        limit=limit,
    )
    return [SkillInstallationResponse.from_entity(item) for item in items]


@router.post(
    "/install",
    response_model=SkillInstallResponse,
    status_code=status.HTTP_201_CREATED,
)
def install_skill(
    payload: InstallSkillRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> SkillInstallResponse:
    try:
        result = container.require(AppKey.SKILL_MANAGER).install(
            source_dir=payload.source_dir,
            scope=payload.scope,
            workspace_dir=payload.workspace_dir,
        )
    except SkillError as exc:
        raise_skill_http_error(exc)
    return SkillInstallResponse.from_entity(result)
