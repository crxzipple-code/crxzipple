from __future__ import annotations

from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel, Field

from crxzipple.modules.ocr.domain import OcrExecutionError, OcrValidationError
from crxzipple.modules.ocr.infrastructure.paddle_engine import PaddleOcrEngine
from crxzipple.modules.ocr.interfaces.serializers import OcrResultSerializer


class OcrHostAnalyzeRequestBody(BaseModel):
    image_path: str = Field(min_length=1)
    language: str = Field(default="ch", min_length=1)
    detect_orientation: bool = True
    artifact_id: str | None = None
    variant: str | None = None


def create_ocr_host_app(
    *,
    engine=None,  # noqa: ANN001
    default_language: str = "ch",
    use_gpu: bool = False,
) -> FastAPI:
    resolved_engine = engine or PaddleOcrEngine(
        default_language=default_language,
        use_gpu=use_gpu,
    )
    serializer = OcrResultSerializer()
    router = APIRouter()

    @router.get("/health")
    def health() -> dict[str, object]:
        return dict(resolved_engine.health())

    @router.post("/analyze")
    def analyze(
        payload: Annotated[OcrHostAnalyzeRequestBody, ...],
    ) -> dict[str, object]:
        image_path = Path(payload.image_path).expanduser()
        if not image_path.is_file():
            raise HTTPException(
                status_code=400,
                detail=f"Image path '{image_path}' was not found.",
            )
        try:
            result = resolved_engine.analyze_image(
                image_path=image_path,
                language=payload.language,
                detect_orientation=payload.detect_orientation,
                artifact_id=payload.artifact_id,
                variant=payload.variant,
            )
        except OcrValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except OcrExecutionError as exc:
            raise HTTPException(status_code=500, detail=str(exc)) from exc
        return serializer.serialize(result)

    app = FastAPI(title="crxzipple OCR Host")
    app.include_router(router)
    return app
