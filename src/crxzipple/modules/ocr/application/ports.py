from __future__ import annotations

from pathlib import Path
from typing import Protocol

from crxzipple.modules.ocr.domain import OcrResult


class OcrEngine(Protocol):
    def health(self) -> dict[str, object]:
        ...

    def analyze_image(
        self,
        *,
        image_path: Path,
        language: str,
        detect_orientation: bool,
        artifact_id: str | None = None,
        variant: str | None = None,
    ) -> OcrResult:
        ...
