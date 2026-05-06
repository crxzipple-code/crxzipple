from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from crxzipple.modules.ocr.domain import OcrResult

if TYPE_CHECKING:
    from crxzipple.modules.ocr.domain import OcrTextBlock


@dataclass(frozen=True, slots=True)
class VisionLayoutCandidate:
    kind: str
    bounds: tuple[int, int, int, int]
    label: str | None = None
    score: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", self.kind.strip() or "vision.box")
        object.__setattr__(
            self,
            "bounds",
            tuple(int(part) for part in self.bounds),
        )
        normalized_label = self.label.strip() if isinstance(self.label, str) else None
        object.__setattr__(self, "label", normalized_label or None)
        object.__setattr__(self, "score", float(self.score))


@dataclass(frozen=True, slots=True)
class _OcrBoundedBlock:
    text: str
    bounds: tuple[int, int, int, int]


def _polygon_bounds(block: OcrTextBlock) -> tuple[int, int, int, int] | None:
    if not block.polygon:
        return None
    xs = [int(round(point.x)) for point in block.polygon]
    ys = [int(round(point.y)) for point in block.polygon]
    if not xs or not ys:
        return None
    left = min(xs)
    top = min(ys)
    right = max(xs)
    bottom = max(ys)
    if right <= left or bottom <= top:
        return None
    return (left, top, right, bottom)


def _expand_bounds(
    bounds: tuple[int, int, int, int],
    *,
    padding: int,
    max_width: int,
    max_height: int,
) -> tuple[int, int, int, int]:
    left, top, right, bottom = bounds
    return (
        max(left - padding, 0),
        max(top - padding, 0),
        min(right + padding, max_width),
        min(bottom + padding, max_height),
    )


def _intersection_area(
    left: tuple[int, int, int, int],
    right: tuple[int, int, int, int],
) -> int:
    x1 = max(left[0], right[0])
    y1 = max(left[1], right[1])
    x2 = min(left[2], right[2])
    y2 = min(left[3], right[3])
    if x2 <= x1 or y2 <= y1:
        return 0
    return (x2 - x1) * (y2 - y1)


def _iou(left: tuple[int, int, int, int], right: tuple[int, int, int, int]) -> float:
    intersection = _intersection_area(left, right)
    if intersection <= 0:
        return 0.0
    left_area = max((left[2] - left[0]) * (left[3] - left[1]), 1)
    right_area = max((right[2] - right[0]) * (right[3] - right[1]), 1)
    union = left_area + right_area - intersection
    return intersection / max(union, 1)


def _vertical_overlap_ratio(
    left: tuple[int, int, int, int],
    right: tuple[int, int, int, int],
) -> float:
    top = max(left[1], right[1])
    bottom = min(left[3], right[3])
    if bottom <= top:
        return 0.0
    overlap = bottom - top
    base = max(min(left[3] - left[1], right[3] - right[1]), 1)
    return overlap / base


def _find_related_blocks(
    *,
    candidate_bounds: tuple[int, int, int, int],
    blocks: tuple[_OcrBoundedBlock, ...],
) -> tuple[_OcrBoundedBlock, ...]:
    related: list[_OcrBoundedBlock] = []
    left, top, right, bottom = candidate_bounds
    for block in blocks:
        intersection = _intersection_area(candidate_bounds, block.bounds)
        block_area = max((block.bounds[2] - block.bounds[0]) * (block.bounds[3] - block.bounds[1]), 1)
        if intersection >= block_area * 0.45:
            related.append(block)
            continue
        if _vertical_overlap_ratio(candidate_bounds, block.bounds) >= 0.6:
            horizontal_gap = min(abs(block.bounds[0] - right), abs(left - block.bounds[2]))
            if horizontal_gap <= 40:
                related.append(block)
    return tuple(related)


def _label_from_related_blocks(blocks: tuple[_OcrBoundedBlock, ...]) -> str | None:
    if not blocks:
        return None
    ordered = sorted(blocks, key=lambda item: (item.bounds[1], item.bounds[0]))
    parts: list[str] = []
    for block in ordered:
        text = block.text.strip()
        if text and text not in parts:
            parts.append(text)
    if not parts:
        return None
    return " ".join(parts[:3]).strip() or None


def _classify_candidate(
    *,
    bounds: tuple[int, int, int, int],
    related_blocks: tuple[_OcrBoundedBlock, ...],
    image_width: int,
    image_height: int,
) -> VisionLayoutCandidate | None:
    left, top, right, bottom = bounds
    width = right - left
    height = bottom - top
    if width < 64 or height < 28:
        return None
    image_area = max(image_width * image_height, 1)
    area = width * height
    if area > image_area * 0.7:
        return None
    label = _label_from_related_blocks(related_blocks)
    inline_text_length = len(label or "")
    related_text_area = sum(
        max((block.bounds[2] - block.bounds[0]) * (block.bounds[3] - block.bounds[1]), 1)
        for block in related_blocks
    )
    text_fill_ratio = related_text_area / max(area, 1)

    if (
        width >= image_width * 0.42
        and 32 <= height <= min(160, int(image_height * 0.12))
        and text_fill_ratio <= 0.62
    ):
        score = 0.9 + min(len(related_blocks), 3) * 0.03
        return VisionLayoutCandidate(
            kind="vision.input",
            bounds=bounds,
            label=label,
            score=score,
        )

    if (
        72 <= width <= image_width * 0.55
        and 28 <= height <= min(140, int(image_height * 0.12))
        and label
        and inline_text_length <= 16
        and len(related_blocks) <= 2
        and text_fill_ratio <= 0.55
    ):
        score = 0.82 + min(len(related_blocks), 2) * 0.04
        return VisionLayoutCandidate(
            kind="vision.button",
            bounds=bounds,
            label=label,
            score=score,
        )

    if (
        (area >= image_area * 0.04 or len(related_blocks) >= 2)
        and width >= image_width * 0.2
        and text_fill_ratio <= 0.82
    ):
        score = 0.7 + min(len(related_blocks), 4) * 0.03
        return VisionLayoutCandidate(
            kind="vision.card",
            bounds=bounds,
            label=label,
            score=score,
        )
    return None


def _dedupe_candidates(
    candidates: tuple[VisionLayoutCandidate, ...],
) -> tuple[VisionLayoutCandidate, ...]:
    kept: list[VisionLayoutCandidate] = []
    for candidate in sorted(candidates, key=lambda item: (-item.score, item.bounds[1], item.bounds[0])):
        if any(_iou(candidate.bounds, existing.bounds) >= 0.65 for existing in kept):
            continue
        kept.append(candidate)
    return tuple(sorted(kept, key=lambda item: (item.bounds[1], item.bounds[0], -item.score)))


def detect_visual_layout_candidates(
    *,
    image_bytes: bytes,
    ocr_result: OcrResult,
    max_candidates: int = 24,
) -> tuple[VisionLayoutCandidate, ...]:
    try:
        import cv2  # type: ignore[import-not-found]
        import numpy as np  # type: ignore[import-not-found]
    except Exception:
        return ()

    if not image_bytes:
        return ()
    image_array = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(image_array, cv2.IMREAD_COLOR)
    if image is None:
        return ()
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    image_height, image_width = gray.shape[:2]
    if image_width <= 0 or image_height <= 0:
        return ()

    bounded_blocks: list[_OcrBoundedBlock] = []
    text_mask = np.zeros((image_height, image_width), dtype=np.uint8)
    for block in ocr_result.blocks:
        bounds = _polygon_bounds(block)
        if bounds is None:
            continue
        bounded_blocks.append(_OcrBoundedBlock(text=block.text, bounds=bounds))
        masked_bounds = _expand_bounds(
            bounds,
            padding=6,
            max_width=image_width - 1,
            max_height=image_height - 1,
        )
        cv2.rectangle(
            text_mask,
            (masked_bounds[0], masked_bounds[1]),
            (masked_bounds[2], masked_bounds[3]),
            255,
            thickness=-1,
        )
    try:
        processed = cv2.inpaint(gray, text_mask, 3, cv2.INPAINT_NS) if bounded_blocks else gray
    except Exception:
        processed = gray
    processed = cv2.GaussianBlur(processed, (3, 3), 0)
    edges = cv2.Canny(processed, 40, 120)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=2)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    classified: list[VisionLayoutCandidate] = []
    bounded_blocks_tuple = tuple(bounded_blocks)
    for contour in contours:
        x, y, width, height = cv2.boundingRect(contour)
        bounds = (int(x), int(y), int(x + width), int(y + height))
        related_blocks = _find_related_blocks(candidate_bounds=bounds, blocks=bounded_blocks_tuple)
        candidate = _classify_candidate(
            bounds=bounds,
            related_blocks=related_blocks,
            image_width=image_width,
            image_height=image_height,
        )
        if candidate is not None:
            classified.append(candidate)
    deduped = _dedupe_candidates(tuple(classified))
    return deduped[: max(int(max_candidates), 0)]
