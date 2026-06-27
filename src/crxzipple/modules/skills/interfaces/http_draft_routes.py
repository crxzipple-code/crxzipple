from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.interfaces.runtime_container import AppContainer, AppKey
from crxzipple.modules.skills.domain import SkillError
from crxzipple.modules.skills.interfaces.http_errors import raise_skill_http_error
from crxzipple.modules.skills.interfaces.http_models import (
    CreateSkillDraftRequest,
    SkillDraftActionRequest,
    SkillDraftAuditResponse,
    SkillDraftResponse,
    UpdateSkillDraftRequest,
)

router = APIRouter()


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
        raise_skill_http_error(exc)
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
        raise_skill_http_error(exc)
    return [SkillDraftResponse.from_entity(draft) for draft in drafts]


@router.get("/drafts/{draft_id}", response_model=SkillDraftResponse)
def get_skill_draft(
    draft_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> SkillDraftResponse:
    try:
        draft = container.require(AppKey.SKILL_MANAGER).get_draft(draft_id)
    except SkillError as exc:
        raise_skill_http_error(exc)
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
        raise_skill_http_error(exc)
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
        raise_skill_http_error(exc)
    return SkillDraftResponse.from_entity(draft)


@router.post("/drafts/{draft_id}/validate", response_model=SkillDraftResponse)
def validate_skill_draft(
    draft_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> SkillDraftResponse:
    try:
        draft = container.require(AppKey.SKILL_MANAGER).validate_draft(draft_id)
    except SkillError as exc:
        raise_skill_http_error(exc)
    return SkillDraftResponse.from_entity(draft)


@router.post("/drafts/{draft_id}/diff", response_model=SkillDraftResponse)
def diff_skill_draft(
    draft_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> SkillDraftResponse:
    try:
        draft = container.require(AppKey.SKILL_MANAGER).build_draft_diff(draft_id)
    except SkillError as exc:
        raise_skill_http_error(exc)
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
        raise_skill_http_error(exc)
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
        raise_skill_http_error(exc)
    return SkillDraftResponse.from_entity(draft)


@router.delete("/drafts/{draft_id}", response_model=SkillDraftResponse)
def delete_skill_draft(
    draft_id: str,
    container: Annotated[AppContainer, Depends(get_container)],
) -> SkillDraftResponse:
    try:
        draft = container.require(AppKey.SKILL_MANAGER).delete_draft(draft_id)
    except SkillError as exc:
        raise_skill_http_error(exc)
    return SkillDraftResponse.from_entity(draft)
