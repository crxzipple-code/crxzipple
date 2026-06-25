from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import ClassVar

from crxzipple.modules.artifacts.domain.entities import ArtifactKind, ArtifactVariant
from crxzipple.modules.artifacts.domain.exceptions import ArtifactNotFoundError
from crxzipple.modules.ocr.domain import OcrExecutionError, OcrResult, OcrValidationError

from .ports import OcrArtifactReadPort, OcrEngine


@dataclass(slots=True)
class OcrApplicationService:
    DEFAULT_MAX_RESULT_BLOCKS: ClassVar[int] = 1_000
    DEFAULT_MAX_RESULT_TEXT_CHARS: ClassVar[int] = 200_000

    engine: OcrEngine
    artifact_service: OcrArtifactReadPort
    default_language: str = "ch"
    max_result_blocks: int = DEFAULT_MAX_RESULT_BLOCKS
    max_result_text_chars: int = DEFAULT_MAX_RESULT_TEXT_CHARS

    def health(self) -> dict[str, object]:
        return dict(self.engine.health())

    def capability_metadata(self) -> dict[str, object]:
        health = dict(self.engine.health())
        explicit = health.get("capabilities")
        capabilities = explicit if isinstance(explicit, Mapping) else {}
        languages = _tuple_texts(capabilities.get("languages")) or (
            self.default_language,
        )
        features = _tuple_texts(capabilities.get("features"))
        return {
            "backend": health.get("backend"),
            "status": health.get("status"),
            "languages": languages,
            "features": features,
            "limits": {
                "max_result_blocks": max(int(self.max_result_blocks), 1),
                "max_result_text_chars": max(int(self.max_result_text_chars), 1),
            },
            "large_output_policy": {
                "mode": "reject_until_artifact_externalization",
                "artifact_ref_externalization": False,
            },
            "source": "ocr_engine_health",
        }

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
        self._enforce_result_budget(result)
        return replace(
            result,
            artifact_id=normalized_artifact_id,
            variant=variant.value,
            language=resolved_language,
        )

    def _enforce_result_budget(self, result: OcrResult) -> None:
        max_blocks = max(int(self.max_result_blocks), 1)
        max_text_chars = max(int(self.max_result_text_chars), 1)
        block_groups = (
            result.blocks,
            result.layout_blocks,
            result.overall_ocr_blocks,
        )
        block_count = sum(len(group) for group in block_groups)
        if block_count > max_blocks:
            raise OcrExecutionError(
                "OCR result exceeded block budget "
                f"({block_count} blocks > {max_blocks}).",
            )
        text_chars = sum(len(block.text) for group in block_groups for block in group)
        if text_chars > max_text_chars:
            raise OcrExecutionError(
                "OCR result exceeded text budget "
                f"({text_chars} chars > {max_text_chars}).",
            )


def _tuple_texts(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        values = (value,)
    elif isinstance(value, (list, tuple, set)):
        values = tuple(value)
    else:
        return ()
    return tuple(str(item).strip() for item in values if str(item).strip())
