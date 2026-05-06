from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from crxzipple.modules.ocr.domain import OcrResult, OcrTextBlock


@dataclass(frozen=True, slots=True)
class OcrResultSerializer:
    def serialize(self, result: OcrResult) -> dict[str, Any]:
        return {
            "backend": result.backend,
            "language": result.language,
            "artifact_id": result.artifact_id,
            "variant": result.variant,
            "image_width": result.image_width,
            "image_height": result.image_height,
            "block_count": len(result.blocks),
            "blocks": [self._serialize_block(block) for block in result.blocks],
            "layout_block_count": len(result.layout_blocks),
            "layout_blocks": [self._serialize_block(block) for block in result.layout_blocks],
            "overall_ocr_block_count": len(result.overall_ocr_blocks),
            "overall_ocr_blocks": [
                self._serialize_block(block)
                for block in result.overall_ocr_blocks
            ],
            "metadata": dict(result.metadata),
        }

    @staticmethod
    def _serialize_block(block: OcrTextBlock) -> dict[str, Any]:
        return {
            "text": block.text,
            "label": block.label,
            "confidence": block.confidence,
            "polygon": [
                {"x": point.x, "y": point.y}
                for point in block.polygon
            ],
        }
