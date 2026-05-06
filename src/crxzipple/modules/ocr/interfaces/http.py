from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from crxzipple.bootstrap import AppContainer
from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.modules.artifacts.domain.entities import ArtifactVariant
from crxzipple.modules.ocr.domain import OcrExecutionError, OcrValidationError


router = APIRouter()


class OcrAnalyzeArtifactRequestBody(BaseModel):
    artifact_id: str = Field(min_length=1)
    variant: str = Field(default=ArtifactVariant.ORIGINAL.value, min_length=1)
    language: str | None = None
    detect_orientation: bool = True


@router.get("/health")
def health(
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, object]:
    try:
        return container.ocr_service.health()
    except (OcrValidationError, OcrExecutionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/analyze-artifact")
def analyze_artifact(
    payload: OcrAnalyzeArtifactRequestBody,
    container: Annotated[AppContainer, Depends(get_container)],
) -> dict[str, object]:
    try:
        variant = ArtifactVariant(payload.variant.strip().lower())
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail="variant must be one of: original, preview, llm.",
        ) from exc
    try:
        result = container.ocr_service.analyze_artifact(
            artifact_id=payload.artifact_id,
            variant=variant,
            language=payload.language,
            detect_orientation=payload.detect_orientation,
        )
    except (OcrValidationError, OcrExecutionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return container.ocr_result_serializer.serialize(result)
