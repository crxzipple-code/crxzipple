from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class OcrPoint:
    x: float
    y: float


@dataclass(frozen=True, slots=True)
class OcrTextBlock:
    text: str
    confidence: float | None = None
    polygon: tuple[OcrPoint, ...] = ()
    label: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "text", self.text.strip())
        object.__setattr__(self, "polygon", tuple(self.polygon))
        object.__setattr__(
            self,
            "label",
            (self.label.strip() if isinstance(self.label, str) else None) or None,
        )


@dataclass(frozen=True, slots=True)
class OcrResult:
    backend: str
    language: str
    blocks: tuple[OcrTextBlock, ...] = ()
    layout_blocks: tuple[OcrTextBlock, ...] = ()
    overall_ocr_blocks: tuple[OcrTextBlock, ...] = ()
    artifact_id: str | None = None
    variant: str | None = None
    image_width: int | None = None
    image_height: int | None = None
    metadata: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "backend", self.backend.strip())
        object.__setattr__(self, "language", self.language.strip())
        object.__setattr__(self, "blocks", tuple(self.blocks))
        object.__setattr__(self, "layout_blocks", tuple(self.layout_blocks))
        object.__setattr__(self, "overall_ocr_blocks", tuple(self.overall_ocr_blocks))
        object.__setattr__(
            self,
            "artifact_id",
            (self.artifact_id.strip() if isinstance(self.artifact_id, str) else None)
            or None,
        )
        object.__setattr__(
            self,
            "variant",
            (self.variant.strip() if isinstance(self.variant, str) else None) or None,
        )
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True, slots=True)
class OcrCapacitySnapshot:
    max_concurrent_requests: int
    in_flight_requests: int

    @property
    def available_requests(self) -> int:
        return max(self.max_concurrent_requests - self.in_flight_requests, 0)

    def as_dict(self) -> dict[str, int]:
        return {
            "max_concurrent_requests": max(int(self.max_concurrent_requests), 1),
            "in_flight_requests": max(int(self.in_flight_requests), 0),
            "available_requests": self.available_requests,
        }
