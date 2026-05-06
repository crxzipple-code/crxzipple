from __future__ import annotations

import base64
from pathlib import Path

from crxzipple.modules.ocr.domain import (
    OcrExecutionError,
    OcrPoint,
    OcrResult,
    OcrTextBlock,
    OcrValidationError,
)
from crxzipple.shared.infrastructure.http import request_url


def _coerce_float(value: object) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _bbox_to_polygon(raw_bbox: object) -> tuple[OcrPoint, ...]:
    if not isinstance(raw_bbox, list) or len(raw_bbox) < 4:
        return ()
    x1 = _coerce_float(raw_bbox[0])
    y1 = _coerce_float(raw_bbox[1])
    x2 = _coerce_float(raw_bbox[2])
    y2 = _coerce_float(raw_bbox[3])
    if None in {x1, y1, x2, y2}:
        return ()
    return (
        OcrPoint(x=x1, y=y1),
        OcrPoint(x=x2, y=y1),
        OcrPoint(x=x2, y=y2),
        OcrPoint(x=x1, y=y2),
    )


def _normalize_orientation_angle(value: object) -> int:
    try:
        normalized = int(value)
    except (TypeError, ValueError):
        return 0
    return normalized % 360


def _rotate_point_to_original(
    point: OcrPoint,
    *,
    width: int,
    height: int,
    angle: int,
) -> OcrPoint:
    normalized_angle = angle % 360
    if normalized_angle == 0:
        return point
    if normalized_angle == 90:
        return OcrPoint(x=point.y, y=height - point.x)
    if normalized_angle == 180:
        return OcrPoint(x=width - point.x, y=height - point.y)
    if normalized_angle == 270:
        return OcrPoint(x=width - point.y, y=point.x)
    return point


def _normalize_polygon_to_original(
    polygon: tuple[OcrPoint, ...],
    *,
    width: int | None,
    height: int | None,
    angle: int,
) -> tuple[OcrPoint, ...]:
    if not polygon or width is None or height is None or angle % 360 == 0:
        return polygon
    rotated = tuple(
        _rotate_point_to_original(point, width=width, height=height, angle=angle)
        for point in polygon
    )
    xs = [point.x for point in rotated]
    ys = [point.y for point in rotated]
    x1 = min(xs)
    y1 = min(ys)
    x2 = max(xs)
    y2 = max(ys)
    return (
        OcrPoint(x=x1, y=y1),
        OcrPoint(x=x2, y=y1),
        OcrPoint(x=x2, y=y2),
        OcrPoint(x=x1, y=y2),
    )


def _normalize_blocks_to_original(
    blocks: tuple[OcrTextBlock, ...],
    *,
    width: int | None,
    height: int | None,
    angle: int,
) -> tuple[OcrTextBlock, ...]:
    if not blocks or width is None or height is None or angle % 360 == 0:
        return blocks
    return tuple(
        OcrTextBlock(
            text=block.text,
            label=block.label,
            confidence=block.confidence,
            polygon=_normalize_polygon_to_original(
                block.polygon,
                width=width,
                height=height,
                angle=angle,
            ),
        )
        for block in blocks
    )


def _extract_result_dimensions(result_payload: dict[str, object]) -> tuple[int | None, int | None]:
    data_info = result_payload.get("dataInfo")
    if isinstance(data_info, dict):
        width = data_info.get("width")
        height = data_info.get("height")
        if isinstance(width, int) and isinstance(height, int):
            return width, height
    layout_results = result_payload.get("layoutParsingResults")
    if not isinstance(layout_results, list):
        return None, None
    for layout_result in layout_results:
        if not isinstance(layout_result, dict):
            continue
        pruned_result = layout_result.get("prunedResult")
        if not isinstance(pruned_result, dict):
            continue
        width = pruned_result.get("width")
        height = pruned_result.get("height")
        if isinstance(width, int) and isinstance(height, int):
            return width, height
    return None, None


def _extract_preprocessor_angle(result_payload: dict[str, object]) -> int:
    layout_results = result_payload.get("layoutParsingResults")
    if not isinstance(layout_results, list):
        return 0
    for layout_result in layout_results:
        if not isinstance(layout_result, dict):
            continue
        pruned_result = layout_result.get("prunedResult")
        if not isinstance(pruned_result, dict):
            continue
        doc_preprocessor = pruned_result.get("doc_preprocessor_res")
        if not isinstance(doc_preprocessor, dict):
            continue
        return _normalize_orientation_angle(doc_preprocessor.get("angle"))
    return 0


def _extract_layout_blocks(
    result_payload: dict[str, object],
) -> tuple[tuple[OcrTextBlock, ...], tuple[str, ...]]:
    layout_results = result_payload.get("layoutParsingResults")
    if not isinstance(layout_results, list):
        return (), ()
    blocks: list[OcrTextBlock] = []
    labels: list[str] = []
    for layout_result in layout_results:
        if not isinstance(layout_result, dict):
            continue
        pruned_result = layout_result.get("prunedResult")
        if not isinstance(pruned_result, dict):
            continue
        parsing_items = pruned_result.get("parsing_res_list")
        if not isinstance(parsing_items, list):
            continue
        for item in parsing_items:
            if not isinstance(item, dict):
                continue
            text = str(item.get("block_content", "")).strip()
            if not text:
                continue
            labels.append(str(item.get("block_label", "")).strip().lower())
            blocks.append(
                OcrTextBlock(
                    text=text,
                    label=(str(item.get("block_label", "")).strip().lower() or None),
                    polygon=_bbox_to_polygon(item.get("block_bbox")),
                )
            )
    return tuple(blocks), tuple(labels)


def _extract_ocr_blocks(
    result_payload: dict[str, object],
) -> tuple[tuple[OcrTextBlock, ...], str]:
    layout_results = result_payload.get("layoutParsingResults")
    if not isinstance(layout_results, list):
        return (), "none"
    blocks: list[OcrTextBlock] = []
    for layout_result in layout_results:
        if not isinstance(layout_result, dict):
            continue
        pruned_result = layout_result.get("prunedResult")
        if not isinstance(pruned_result, dict):
            continue
        overall_ocr = pruned_result.get("overall_ocr_res")
        if not isinstance(overall_ocr, dict):
            continue
        rec_texts = overall_ocr.get("rec_texts")
        rec_boxes = overall_ocr.get("rec_boxes")
        rec_scores = overall_ocr.get("rec_scores")
        if not isinstance(rec_texts, list) or not isinstance(rec_boxes, list):
            continue
        for index, text in enumerate(rec_texts):
            normalized_text = str(text).strip()
            if not normalized_text:
                continue
            confidence = None
            if isinstance(rec_scores, list) and index < len(rec_scores):
                confidence = _coerce_float(rec_scores[index])
            bbox = rec_boxes[index] if index < len(rec_boxes) else None
            blocks.append(
                OcrTextBlock(
                    text=normalized_text,
                    label="text",
                    confidence=confidence,
                    polygon=_bbox_to_polygon(bbox),
                )
            )
    return tuple(blocks), "overall_ocr"


def _extract_markdown_blocks(
    result_payload: dict[str, object],
) -> tuple[tuple[OcrTextBlock, ...], str]:
    layout_results = result_payload.get("layoutParsingResults")
    if not isinstance(layout_results, list):
        return (), "none"
    blocks: list[OcrTextBlock] = []
    for layout_result in layout_results:
        if not isinstance(layout_result, dict):
            continue
        markdown = layout_result.get("markdown")
        if not isinstance(markdown, dict):
            continue
        text = str(markdown.get("text", "")).strip()
        if not text:
            continue
        blocks.append(OcrTextBlock(text=text, label="markdown"))
    return tuple(blocks), "markdown"


def _rectangle_dimensions(
    polygon: tuple[OcrPoint, ...],
) -> tuple[float, float] | None:
    if len(polygon) < 4:
        return None
    xs = [point.x for point in polygon]
    ys = [point.y for point in polygon]
    return max(xs) - min(xs), max(ys) - min(ys)


def _should_prefer_overall_ocr(
    *,
    result_payload: dict[str, object],
    layout_blocks: tuple[OcrTextBlock, ...],
    layout_labels: tuple[str, ...],
    overall_blocks: tuple[OcrTextBlock, ...],
) -> bool:
    if not overall_blocks:
        return False
    if not layout_blocks:
        return True
    if len(overall_blocks) > len(layout_blocks):
        return True
    if len(layout_blocks) != 1:
        return False
    if not any(label == "image" for label in layout_labels):
        return False
    data_info = result_payload.get("dataInfo")
    if not isinstance(data_info, dict):
        return True
    width = data_info.get("width")
    height = data_info.get("height")
    if not isinstance(width, int) or not isinstance(height, int) or width <= 0 or height <= 0:
        return True
    dimensions = _rectangle_dimensions(layout_blocks[0].polygon)
    if dimensions is None:
        return True
    block_width, block_height = dimensions
    area_ratio = (block_width * block_height) / float(width * height)
    return area_ratio >= 0.8


class PPStructureV3Client:
    def __init__(
        self,
        *,
        base_url: str,
        timeout_seconds: float = 60.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = max(float(timeout_seconds), 0.1)

    def health(self) -> dict[str, object]:
        try:
            response = request_url(
                "GET",
                f"{self.base_url}/health",
                timeout=self.timeout_seconds,
            )
        except Exception as exc:  # noqa: BLE001
            raise OcrExecutionError(
                f"PP-StructureV3 healthcheck failed: {exc}",
            ) from exc
        try:
            response.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            raise OcrExecutionError(
                f"PP-StructureV3 healthcheck failed: {exc}",
            ) from exc
        payload = response.json()
        if not isinstance(payload, dict):
            raise OcrExecutionError(
                "PP-StructureV3 returned an invalid health payload.",
            )
        return dict(payload)

    def analyze_image(
        self,
        *,
        image_path: Path,
        language: str,
        detect_orientation: bool,
        artifact_id: str | None = None,
        variant: str | None = None,
    ) -> OcrResult:
        image_bytes = image_path.read_bytes()
        request_payload = {
            "file": base64.b64encode(image_bytes).decode("ascii"),
            "fileType": 1,
            "useDocOrientationClassify": bool(detect_orientation),
            # Phone screenshots are already rectified; document unwarping distorts
            # edge geometry and makes OCR boxes drift outward.
            "useDocUnwarping": False,
            "useTextlineOrientation": bool(detect_orientation),
            "logId": artifact_id,
        }
        try:
            response = request_url(
                "POST",
                f"{self.base_url}/layout-parsing",
                json=request_payload,
                timeout=self.timeout_seconds,
            )
        except Exception as exc:  # noqa: BLE001
            raise OcrExecutionError(
                f"PP-StructureV3 request failed: {exc}",
            ) from exc
        payload = response.json()
        if response.status_code >= 400:
            detail = None
            if isinstance(payload, dict):
                detail = payload.get("errorMsg") or payload.get("detail")
            message = str(detail or "PP-StructureV3 request failed.")
            if response.status_code < 500:
                raise OcrValidationError(message)
            raise OcrExecutionError(message)
        if not isinstance(payload, dict):
            raise OcrExecutionError(
                "PP-StructureV3 returned an invalid OCR payload.",
            )
        error_code = payload.get("errorCode")
        if error_code not in (None, 0):
            message = str(payload.get("errorMsg") or "PP-StructureV3 request failed.")
            raise OcrExecutionError(message)
        result_payload = payload.get("result")
        if not isinstance(result_payload, dict):
            raise OcrExecutionError(
                "PP-StructureV3 OCR payload is missing the result body.",
            )
        image_width, image_height = _extract_result_dimensions(result_payload)
        preprocessor_angle = _extract_preprocessor_angle(result_payload)
        layout_blocks, layout_labels = _extract_layout_blocks(result_payload)
        overall_blocks, overall_source = _extract_ocr_blocks(result_payload)
        layout_blocks = _normalize_blocks_to_original(
            layout_blocks,
            width=image_width,
            height=image_height,
            angle=preprocessor_angle,
        )
        overall_blocks = _normalize_blocks_to_original(
            overall_blocks,
            width=image_width,
            height=image_height,
            angle=preprocessor_angle,
        )
        if _should_prefer_overall_ocr(
            result_payload=result_payload,
            layout_blocks=layout_blocks,
            layout_labels=layout_labels,
            overall_blocks=overall_blocks,
        ):
            blocks = overall_blocks
            block_source = overall_source
        elif layout_blocks:
            blocks = layout_blocks
            block_source = "layout"
        elif overall_blocks:
            blocks = overall_blocks
            block_source = overall_source
        else:
            blocks, block_source = _extract_markdown_blocks(result_payload)
        return OcrResult(
            backend="ppstructurev3",
            language=language,
            artifact_id=artifact_id,
            variant=variant,
            image_width=image_width,
            image_height=image_height,
            blocks=blocks,
            layout_blocks=layout_blocks,
            overall_ocr_blocks=overall_blocks,
            metadata={
                "provider": "ppstructurev3",
                "log_id": payload.get("logId"),
                "block_source": block_source,
                "preprocessor_angle": preprocessor_angle,
                "layout_block_count": len(layout_blocks),
                "overall_ocr_block_count": len(overall_blocks),
            },
        )
