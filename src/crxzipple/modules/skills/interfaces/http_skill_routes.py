from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.interfaces.runtime_container import AppContainer, AppKey
from crxzipple.modules.skills.domain import SkillError
from crxzipple.modules.skills.interfaces.http_errors import raise_skill_http_error
from crxzipple.modules.skills.interfaces.http_models import (
    CreateSkillRequest,
    SkillDetailResponse,
    SkillEnablementRequest,
    SkillMutationResponse,
    SkillReadinessMapResponse,
    SkillReadinessResponse,
    SkillResponse,
    SkillWriteRequest,
    UpdateSkillRequest,
    ValidateSkillRequest,
)

router = APIRouter()


@router.get("", response_model=list[SkillResponse])
def list_skills(
    container: Annotated[AppContainer, Depends(get_container)],
    workspace_dir: str | None = Query(default=None),
    surface: str = Query(default="interactive"),
    source: str | None = Query(default=None),
    include_disabled: bool = Query(default=False),
    include_readiness: bool = Query(default=False),
    include_removed: bool = Query(default=False),
) -> list[SkillResponse]:
    _ = include_removed
    manager = container.require(AppKey.SKILL_MANAGER)
    items = manager.list_available(
        workspace_dir=workspace_dir,
        surface=surface,
        include_disabled=include_disabled,
    )
    if source:
        normalized_source = source.strip()
        items = tuple(item for item in items if item.source == normalized_source)
    readiness = (
        manager.readiness(
            workspace_dir=workspace_dir,
            skill_name=None,
            surface=surface,
        )
        if include_readiness
        else {}
    )
    return [
        SkillResponse.from_entity(
            item,
            enabled=manager.package_enabled(item),
            readiness=readiness.get(item.name),
        )
        for item in items
    ]


@router.get("/readiness", response_model=SkillReadinessMapResponse)
def list_readiness(
    container: Annotated[AppContainer, Depends(get_container)],
    workspace_dir: str | None = Query(default=None),
    surface: str = Query(default="interactive"),
) -> SkillReadinessMapResponse:
    try:
        readiness = container.require(AppKey.SKILL_MANAGER).readiness(
            workspace_dir=workspace_dir,
            skill_name=None,
            surface=surface,
        )
    except SkillError as exc:
        raise_skill_http_error(exc)
    return SkillReadinessMapResponse.from_entities(readiness)


@router.post("/validate", response_model=SkillResponse)
def validate_skill(
    payload: ValidateSkillRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> SkillResponse:
    try:
        package = container.require(AppKey.SKILL_MANAGER).validate(path=payload.path)
    except SkillError as exc:
        raise_skill_http_error(exc)
    return SkillResponse.from_entity(package)


@router.post("", response_model=SkillMutationResponse, status_code=status.HTTP_201_CREATED)
def create_skill(
    payload: CreateSkillRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> SkillMutationResponse:
    try:
        result = container.require(AppKey.SKILL_MANAGER).create(
            payload.to_application_request(),
        )
    except SkillError as exc:
        raise_skill_http_error(exc)
    return SkillMutationResponse.from_entity(result)


@router.get("/{skill_name}", response_model=SkillDetailResponse)
def get_skill(
    skill_name: str,
    container: Annotated[AppContainer, Depends(get_container)],
    workspace_dir: str | None = Query(default=None),
    surface: str = Query(default="interactive"),
    include_instructions: bool = Query(default=False),
    include_readiness: bool = Query(default=True),
    include_disabled: bool = Query(default=False),
) -> SkillDetailResponse:
    manager = container.require(AppKey.SKILL_MANAGER)
    try:
        package = manager.get(
            workspace_dir=workspace_dir,
            skill_name=skill_name,
            surface=surface,
            include_disabled=include_disabled,
        )
        readiness = None
        if include_readiness:
            readiness = manager.readiness(
                workspace_dir=workspace_dir,
                skill_name=skill_name,
                surface=surface,
            ).get(skill_name)
        response = SkillDetailResponse(
            **SkillResponse.from_entity(
                package,
                enabled=manager.package_enabled(package),
                readiness=readiness,
            ).model_dump(),
        )
        if include_instructions:
            response.instructions = manager.read(
                workspace_dir=workspace_dir,
                skill_name=skill_name,
                path=None,
                surface=surface,
            ).content
        return response
    except SkillError as exc:
        raise_skill_http_error(exc)


@router.patch("/{skill_name}", response_model=SkillMutationResponse)
def update_skill(
    skill_name: str,
    payload: UpdateSkillRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> SkillMutationResponse:
    try:
        result = container.require(AppKey.SKILL_MANAGER).update(
            payload.to_application_request(skill_name),
        )
    except SkillError as exc:
        raise_skill_http_error(exc)
    return SkillMutationResponse.from_entity(result)


@router.put("/{skill_name}/instructions", response_model=SkillMutationResponse)
def write_skill_instructions(
    skill_name: str,
    payload: SkillWriteRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> SkillMutationResponse:
    try:
        result = container.require(AppKey.SKILL_MANAGER).write_instructions(
            workspace_dir=payload.workspace_dir,
            skill_name=skill_name,
            content=payload.content,
        )
    except SkillError as exc:
        raise_skill_http_error(exc)
    return SkillMutationResponse.from_entity(result)


@router.put("/{skill_name}/files/{file_path:path}", response_model=SkillMutationResponse)
def write_skill_file(
    skill_name: str,
    file_path: str,
    payload: SkillWriteRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> SkillMutationResponse:
    try:
        result = container.require(AppKey.SKILL_MANAGER).write_file(
            workspace_dir=payload.workspace_dir,
            skill_name=skill_name,
            path=file_path,
            content=payload.content,
        )
    except SkillError as exc:
        raise_skill_http_error(exc)
    return SkillMutationResponse.from_entity(result)


@router.delete("/{skill_name}/files/{file_path:path}", response_model=SkillMutationResponse)
def delete_skill_file(
    skill_name: str,
    file_path: str,
    container: Annotated[AppContainer, Depends(get_container)],
    workspace_dir: str | None = Query(default=None),
) -> SkillMutationResponse:
    try:
        result = container.require(AppKey.SKILL_MANAGER).delete_file(
            workspace_dir=workspace_dir,
            skill_name=skill_name,
            path=file_path,
        )
    except SkillError as exc:
        raise_skill_http_error(exc)
    return SkillMutationResponse.from_entity(result)


@router.get("/{skill_name}/readiness", response_model=SkillReadinessResponse)
def get_skill_readiness(
    skill_name: str,
    container: Annotated[AppContainer, Depends(get_container)],
    workspace_dir: str | None = Query(default=None),
    surface: str = Query(default="interactive"),
) -> SkillReadinessResponse:
    try:
        readiness = container.require(AppKey.SKILL_MANAGER).readiness(
            workspace_dir=workspace_dir,
            skill_name=skill_name,
            surface=surface,
        )[skill_name]
    except SkillError as exc:
        raise_skill_http_error(exc)
    return SkillReadinessResponse.from_entity(readiness)


@router.post("/{skill_name}/enable", response_model=SkillMutationResponse)
def enable_skill(
    skill_name: str,
    payload: SkillEnablementRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> SkillMutationResponse:
    try:
        result = container.require(AppKey.SKILL_MANAGER).enable(
            workspace_dir=payload.workspace_dir,
            skill_name=skill_name,
            reason=payload.reason,
            surface=payload.surface,
        )
    except SkillError as exc:
        raise_skill_http_error(exc)
    return SkillMutationResponse.from_entity(result)


@router.post("/{skill_name}/disable", response_model=SkillMutationResponse)
def disable_skill(
    skill_name: str,
    payload: SkillEnablementRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> SkillMutationResponse:
    try:
        result = container.require(AppKey.SKILL_MANAGER).disable(
            workspace_dir=payload.workspace_dir,
            skill_name=skill_name,
            reason=payload.reason,
            surface=payload.surface,
        )
    except SkillError as exc:
        raise_skill_http_error(exc)
    return SkillMutationResponse.from_entity(result)


@router.delete("/{skill_name}", response_model=SkillMutationResponse)
def delete_skill(
    skill_name: str,
    container: Annotated[AppContainer, Depends(get_container)],
    workspace_dir: str | None = Query(default=None),
    surface: str = Query(default="interactive"),
) -> SkillMutationResponse:
    try:
        result = container.require(AppKey.SKILL_MANAGER).uninstall(
            workspace_dir=workspace_dir,
            skill_name=skill_name,
            surface=surface,
        )
    except SkillError as exc:
        raise_skill_http_error(exc)
    return SkillMutationResponse.from_entity(result)
