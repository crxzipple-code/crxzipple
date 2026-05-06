from __future__ import annotations

from dataclasses import dataclass

from crxzipple.modules.artifacts.domain.entities import ArtifactVariant


@dataclass(frozen=True, slots=True)
class OcrAnalyzeArtifactRequest:
    artifact_id: str
    variant: ArtifactVariant = ArtifactVariant.ORIGINAL
    language: str | None = None
    detect_orientation: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifact_id", self.artifact_id.strip())
        object.__setattr__(
            self,
            "language",
            (self.language.strip() if isinstance(self.language, str) else None) or None,
        )
