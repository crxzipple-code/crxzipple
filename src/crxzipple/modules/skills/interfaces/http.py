from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from crxzipple.interfaces.runtime_container import AppContainer, AppKey
from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.modules.skills.application.exceptions import SkillCapabilityUnavailableError
from crxzipple.modules.skills.domain import (
    SkillError,
    SkillNotFoundError,
    SkillValidationError,
)
from crxzipple.modules.skills.interfaces.http_models import (
    CreateSkillDraftRequest,
    CreateSkillRequest,
    CreateSkillSourceRequest,
    InstallSkillRequest,
    SkillDetailResponse,
    SkillDraftActionRequest,
    SkillDraftAuditResponse,
    SkillDraftResponse,
    SkillEnablementRequest,
    SkillInstallationResponse,
    SkillInstallResponse,
    SkillMutationResponse,
    SkillReadinessMapResponse,
    SkillReadinessResponse,
    SkillResponse,
    SkillSourceMutationResponse,
    SkillSourceResponse,
    SkillSyncRequest,
    SkillSyncResponse,
    SkillWriteRequest,
    UpdateSkillDraftRequest,
    UpdateSkillRequest,
    UpdateSkillSourceRequest,
    ValidateSkillRequest,
)

router = APIRouter()


def _raise_skill_http_error(exc: SkillError) -> None:
    if isinstance(exc, SkillNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, SkillValidationError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if isinstance(exc, SkillCapabilityUnavailableError):
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    raise HTTPException(status_code=500, detail=str(exc)) from exc


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
        _raise_skill_http_error(exc)
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
        _raise_skill_http_error(exc)
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
        _raise_skill_http_error(exc)
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
        _raise_skill_http_error(exc)
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
        _raise_skill_http_error(exc)
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
        _raise_skill_http_error(exc)
    return SkillReadinessMapResponse.from_entities(readiness)


@router.post("/validate", response_model=SkillResponse)
def validate_skill(
    payload: ValidateSkillRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> SkillResponse:
    try:
        package = container.require(AppKey.SKILL_MANAGER).validate(path=payload.path)
    except SkillError as exc:
        _raise_skill_http_error(exc)
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
        _raise_skill_http_error(exc)
    return SkillMutationResponse.from_entity(result)


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
        _raise_skill_http_error(exc)
    return SkillInstallResponse.from_entity(result)


@router.post(
    "/drafts",
    response_model=SkillDraftResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_skill_draft(
    payload: CreateSkillDraftRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> SkillDraftResponse:
    try:
        draft = container.require(AppKey.SKILL_MANAGER).create_draft(
            payload.to_application_request(),
        )
    except SkillError as exc:
        _raise_skill_http_error(exc)
    return SkillDraftResponse.from_entity(draft)


@router.get("/drafts", response_model=list[SkillDraftResponse])
def list_skill_drafts(
    container: Annotated[AppContainer, Depends(get_container)],
    status_value: str | None = Query(default=None, alias="status"),
    skill_name: str | None = Query(default=None),
    run_id: str | None = Query(default=None),
    workspace_dir: str | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[SkillDraftResponse]:
    try:
        drafts = container.require(AppKey.SKILL_MANAGER).list_drafts(
            status=status_value,
            skill_name=skill_name,
            run_id=run_id,
            workspace_dir=workspace_dir,
            limit=limit,
        )
    except SkillError as exc:
        _raise_skill_http_error(exc)
    return [SkillDraftResponse.from_entity(draft) for draft in drafts]


@router.get("/drafts/{draft_id}", response_model=SkillDraftResponse)
def get_skill_draft(
    draft_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> SkillDraftResponse:
    try:
        draft = container.require(AppKey.SKILL_MANAGER).get_draft(draft_id)
    except SkillError as exc:
        _raise_skill_http_error(exc)
    return SkillDraftResponse.from_entity(draft)


@router.get("/drafts/{draft_id}/audit", response_model=list[SkillDraftAuditResponse])
def list_skill_draft_audit(
    draft_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
    limit: int = Query(default=100, ge=1, le=500),
) -> list[SkillDraftAuditResponse]:
    try:
        records = container.require(AppKey.SKILL_MANAGER).list_draft_audit(
            draft_id=draft_id,
            limit=limit,
        )
    except SkillError as exc:
        _raise_skill_http_error(exc)
    return [SkillDraftAuditResponse.from_entity(record) for record in records]


@router.patch("/drafts/{draft_id}", response_model=SkillDraftResponse)
def update_skill_draft(
    draft_id: str,
    payload: UpdateSkillDraftRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> SkillDraftResponse:
    try:
        draft = container.require(AppKey.SKILL_MANAGER).update_draft(
            draft_id=draft_id,
            request=payload.to_application_request(),
        )
    except SkillError as exc:
        _raise_skill_http_error(exc)
    return SkillDraftResponse.from_entity(draft)


@router.post("/drafts/{draft_id}/validate", response_model=SkillDraftResponse)
def validate_skill_draft(
    draft_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> SkillDraftResponse:
    try:
        draft = container.require(AppKey.SKILL_MANAGER).validate_draft(draft_id)
    except SkillError as exc:
        _raise_skill_http_error(exc)
    return SkillDraftResponse.from_entity(draft)


@router.post("/drafts/{draft_id}/diff", response_model=SkillDraftResponse)
def diff_skill_draft(
    draft_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> SkillDraftResponse:
    try:
        draft = container.require(AppKey.SKILL_MANAGER).build_draft_diff(draft_id)
    except SkillError as exc:
        _raise_skill_http_error(exc)
    return SkillDraftResponse.from_entity(draft)


@router.post("/drafts/{draft_id}/apply", response_model=SkillDraftResponse)
def apply_skill_draft(
    draft_id: str,
    payload: SkillDraftActionRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> SkillDraftResponse:
    try:
        draft = container.require(AppKey.SKILL_MANAGER).apply_draft(
            draft_id=draft_id,
            reason=payload.reason,
        )
    except SkillError as exc:
        _raise_skill_http_error(exc)
    return SkillDraftResponse.from_entity(draft)


@router.post("/drafts/{draft_id}/reject", response_model=SkillDraftResponse)
def reject_skill_draft(
    draft_id: str,
    payload: SkillDraftActionRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> SkillDraftResponse:
    try:
        draft = container.require(AppKey.SKILL_MANAGER).reject_draft(
            draft_id=draft_id,
            reason=payload.reason,
        )
    except SkillError as exc:
        _raise_skill_http_error(exc)
    return SkillDraftResponse.from_entity(draft)


@router.delete("/drafts/{draft_id}", response_model=SkillDraftResponse)
def delete_skill_draft(
    draft_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> SkillDraftResponse:
    try:
        draft = container.require(AppKey.SKILL_MANAGER).delete_draft(draft_id)
    except SkillError as exc:
        _raise_skill_http_error(exc)
    return SkillDraftResponse.from_entity(draft)


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
        _raise_skill_http_error(exc)


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
        _raise_skill_http_error(exc)
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
        _raise_skill_http_error(exc)
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
        _raise_skill_http_error(exc)
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
        _raise_skill_http_error(exc)
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
        _raise_skill_http_error(exc)
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
        _raise_skill_http_error(exc)
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
        _raise_skill_http_error(exc)
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
        _raise_skill_http_error(exc)
    return SkillMutationResponse.from_entity(result)
