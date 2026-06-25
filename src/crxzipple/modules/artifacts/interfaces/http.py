from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

from crxzipple.interfaces.runtime_container import AppContainer, AppKey
from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.modules.authorization.domain import (
    AuthorizationContext,
    AuthorizationDeniedError,
    AuthorizationRequest,
    AuthorizationResource,
    AuthorizationSubject,
)
from crxzipple.modules.artifacts.domain.entities import ArtifactVariant
from crxzipple.modules.artifacts.domain.exceptions import (
    ArtifactNotFoundError,
    ArtifactValidationError,
)


router = APIRouter()


class ArtifactResponse(BaseModel):
    id: str
    kind: str
    mime_type: str
    name: str | None
    size_bytes: int
    width: int | None
    height: int | None
    preview_url: str
    original_url: str
    download_url: str
    created_at: str


def _to_response(artifact) -> ArtifactResponse:
    return ArtifactResponse(
        id=artifact.id,
        kind=artifact.kind.value,
        mime_type=artifact.mime_type,
        name=artifact.name,
        size_bytes=artifact.size_bytes,
        width=artifact.width,
        height=artifact.height,
        preview_url=f"/artifacts/{artifact.id}/preview",
        original_url=f"/artifacts/{artifact.id}/original",
        download_url=f"/artifacts/{artifact.id}/download",
        created_at=artifact.created_at.isoformat(),
    )


@router.post("", response_model=ArtifactResponse)
async def upload_artifact(
    request: Request,
    container: Annotated[AppContainer, Depends(get_container)],
    name: Annotated[str | None, Query()] = None,
    mime_type: Annotated[str | None, Query()] = None,
) -> ArtifactResponse:
    raw = await request.body()
    if not raw:
        raise HTTPException(status_code=400, detail="Uploaded artifact cannot be empty.")
    resolved_name = name or request.headers.get("x-artifact-name")
    resolved_mime_type = (
        mime_type
        or request.headers.get("content-type")
        or "application/octet-stream"
    )
    try:
        artifact = container.require(AppKey.ARTIFACT_SERVICE).create_artifact(
            data=raw,
            mime_type=resolved_mime_type,
            name=resolved_name,
        )
    except ArtifactValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return _to_response(artifact)


@router.get("/{artifact_id}", response_model=ArtifactResponse)
def get_artifact(
    artifact_id: str,
    request: Request,
    container: Annotated[AppContainer, Depends(get_container)],
) -> ArtifactResponse:
    _authorize_artifact_read(
        container,
        request=request,
        artifact_id=artifact_id,
        variant=None,
        as_attachment=False,
    )
    try:
        artifact = container.require(AppKey.ARTIFACT_SERVICE).get_artifact(artifact_id)
    except ArtifactNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    return _to_response(artifact)


@router.get("/{artifact_id}/original")
def get_artifact_original(
    artifact_id: str,
    request: Request,
    container: Annotated[AppContainer, Depends(get_container)],
):
    return _variant_response(
        container,
        request=request,
        artifact_id=artifact_id,
        variant=ArtifactVariant.ORIGINAL,
        as_attachment=False,
    )


@router.get("/{artifact_id}/preview")
def get_artifact_preview(
    artifact_id: str,
    request: Request,
    container: Annotated[AppContainer, Depends(get_container)],
):
    return _variant_response(
        container,
        request=request,
        artifact_id=artifact_id,
        variant=ArtifactVariant.PREVIEW,
        as_attachment=False,
    )


@router.get("/{artifact_id}/download")
def download_artifact(
    artifact_id: str,
    request: Request,
    container: Annotated[AppContainer, Depends(get_container)],
):
    return _variant_response(
        container,
        request=request,
        artifact_id=artifact_id,
        variant=ArtifactVariant.ORIGINAL,
        as_attachment=True,
    )


def _variant_response(
    container: AppContainer,
    *,
    request: Request,
    artifact_id: str,
    variant: ArtifactVariant,
    as_attachment: bool,
) -> FileResponse:
    _authorize_artifact_read(
        container,
        request=request,
        artifact_id=artifact_id,
        variant=variant,
        as_attachment=as_attachment,
    )
    try:
        resolved = container.require(AppKey.ARTIFACT_SERVICE).resolve_variant(
            artifact_id,
            variant=variant,
        )
    except ArtifactNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    return FileResponse(
        path=resolved.path,
        media_type=resolved.artifact.mime_type,
        filename=resolved.artifact.name,
        content_disposition_type="attachment" if as_attachment else "inline",
    )


def _authorize_artifact_read(
    container: AppContainer,
    *,
    request: Request,
    artifact_id: str,
    variant: ArtifactVariant | None,
    as_attachment: bool,
) -> None:
    if not container.has(AppKey.AUTHORIZATION_SERVICE):
        return
    subject_type = request.headers.get("x-crxzipple-subject-type") or "anonymous"
    subject_id = request.headers.get("x-crxzipple-subject-id")
    authorization_request = AuthorizationRequest(
        subject=AuthorizationSubject(
            type=subject_type.strip() or "anonymous",
            id=(subject_id or "").strip() or None,
            attrs={"interface": "http"},
        ),
        action="artifact.read",
        resource=AuthorizationResource(
            kind="artifact",
            id=artifact_id,
            attrs={
                "variant": variant.value if variant is not None else "metadata",
                "as_attachment": as_attachment,
            },
        ),
        context=AuthorizationContext(
            attrs={
                "interface": "http",
                "path": request.url.path,
            },
        ),
    )
    try:
        container.require(AppKey.AUTHORIZATION_SERVICE).authorize(authorization_request)
    except AuthorizationDeniedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from None
