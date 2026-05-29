from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol

from crxzipple.modules.ocr.domain import OcrResult

if TYPE_CHECKING:
    from crxzipple.modules.artifacts.domain import ArtifactVariant


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


class OcrResolvedArtifactVariantPort(Protocol):
    path: Path
    artifact: Any


class OcrArtifactReadPort(Protocol):
    def resolve_variant(
        self,
        artifact_id: str,
        *,
        variant: "ArtifactVariant",
    ) -> OcrResolvedArtifactVariantPort:
        ...
