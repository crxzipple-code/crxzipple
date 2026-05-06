from __future__ import annotations

from dataclasses import dataclass, replace

from crxzipple.modules.artifacts.application.services import ArtifactApplicationService
from crxzipple.modules.artifacts.domain.entities import ArtifactKind, ArtifactVariant
from crxzipple.modules.artifacts.domain.exceptions import ArtifactNotFoundError
from crxzipple.modules.ocr.domain import OcrExecutionError, OcrResult, OcrValidationError

from .ports import OcrEngine


@dataclass(slots=True)
class OcrApplicationService:
    engine: OcrEngine
    artifact_service: ArtifactApplicationService
    default_language: str = "ch"

    def health(self) -> dict[str, object]:
        return dict(self.engine.health())

    def analyze_artifact(
        self,
        *,
        artifact_id: str,
        variant: ArtifactVariant = ArtifactVariant.ORIGINAL,
        language: str | None = None,
        detect_orientation: bool = True,
    ) -> OcrResult:
        normalized_artifact_id = artifact_id.strip()
        if not normalized_artifact_id:
            raise OcrValidationError("artifact_id must be a non-empty string.")
        resolved_language = (language or self.default_language).strip()
        if not resolved_language:
            raise OcrValidationError("language must be a non-empty string.")
        try:
            binary = self.artifact_service.resolve_variant(
                normalized_artifact_id,
                variant=variant,
            )
        except ArtifactNotFoundError as exc:
            raise OcrValidationError(str(exc)) from exc
        if binary.artifact.kind is not ArtifactKind.IMAGE:
            raise OcrValidationError(
                f"Artifact '{normalized_artifact_id}' is not an image artifact.",
            )
        try:
            result = self.engine.analyze_image(
                image_path=binary.path,
                language=resolved_language,
                detect_orientation=bool(detect_orientation),
                artifact_id=normalized_artifact_id,
                variant=variant.value,
            )
        except OcrValidationError:
            raise
        except OcrExecutionError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise OcrExecutionError(str(exc)) from exc
        return replace(
            result,
            artifact_id=normalized_artifact_id,
            variant=variant.value,
            language=resolved_language,
        )
