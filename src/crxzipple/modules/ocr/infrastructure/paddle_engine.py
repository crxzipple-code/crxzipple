from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from PIL import Image

from crxzipple.modules.ocr.domain import (
    OcrExecutionError,
    OcrPoint,
    OcrResult,
    OcrTextBlock,
)


def _coerce_points(value: object) -> tuple[OcrPoint, ...]:
    points: list[OcrPoint] = []
    if not isinstance(value, list | tuple):
        return ()
    for item in value:
        if not isinstance(item, list | tuple) or len(item) < 2:
            continue
        try:
            points.append(OcrPoint(x=float(item[0]), y=float(item[1])))
        except (TypeError, ValueError):
            continue
    return tuple(points)


def _coerce_blocks(raw_result: object) -> tuple[OcrTextBlock, ...]:
    items = raw_result
    if isinstance(items, list | tuple) and len(items) == 1 and isinstance(items[0], list | tuple):
        items = items[0]
    blocks: list[OcrTextBlock] = []
    if not isinstance(items, list | tuple):
        return ()
    for item in items:
        if not isinstance(item, list | tuple) or len(item) < 2:
            continue
        polygon = _coerce_points(item[0])
        text = ""
        confidence: float | None = None
        text_payload = item[1]
        if isinstance(text_payload, list | tuple):
            if text_payload:
                text = str(text_payload[0]).strip()
            if len(text_payload) > 1:
                try:
                    confidence = float(text_payload[1])
                except (TypeError, ValueError):
                    confidence = None
        else:
            text = str(text_payload).strip()
        if not text:
            continue
        blocks.append(
            OcrTextBlock(
                text=text,
                confidence=confidence,
                polygon=polygon,
                label="text",
            )
        )
    return tuple(blocks)


@dataclass(slots=True)
class PaddleOcrEngine:
    default_language: str = "ch"
    use_gpu: bool = False
    _engines: dict[str, Any] = field(default_factory=dict, init=False, repr=False)

    def health(self) -> dict[str, object]:
        return {
            "status": "ok",
            "backend": "paddleocr",
            "default_language": self.default_language,
            "use_gpu": self.use_gpu,
        }

    def analyze_image(
        self,
        *,
        image_path: Path,
        language: str,
        detect_orientation: bool,
        artifact_id: str | None = None,
        variant: str | None = None,
    ) -> OcrResult:
        engine = self._engine_for_language(language)
        try:
            raw_result = engine.ocr(str(image_path), cls=bool(detect_orientation))
        except Exception as exc:  # noqa: BLE001
            raise OcrExecutionError(f"PaddleOCR analysis failed: {exc}") from exc
        width: int | None = None
        height: int | None = None
        try:
            with Image.open(image_path) as image:
                width, height = image.size
        except Exception:  # noqa: BLE001
            width = None
            height = None
        return OcrResult(
            backend="paddleocr",
            language=language,
            artifact_id=artifact_id,
            variant=variant,
            image_width=width,
            image_height=height,
            blocks=_coerce_blocks(raw_result),
        )

    def _engine_for_language(self, language: str):
        normalized_language = language.strip() or self.default_language
        if normalized_language in self._engines:
            return self._engines[normalized_language]
        try:
            from paddleocr import PaddleOCR
        except Exception as exc:  # noqa: BLE001
            raise OcrExecutionError(
                "PaddleOCR is not available. Install the 'paddleocr' dependency to run the OCR host.",
            ) from exc
        try:
            engine = PaddleOCR(
                use_angle_cls=True,
                lang=normalized_language,
                use_gpu=self.use_gpu,
                show_log=False,
            )
        except TypeError:
            engine = PaddleOCR(
                lang=normalized_language,
                use_gpu=self.use_gpu,
            )
        self._engines[normalized_language] = engine
        return engine
