from __future__ import annotations

from pathlib import Path

from crxzipple.modules.ocr.domain import (
    OcrCapacityExceededError,
    OcrExecutionError,
    OcrPoint,
    OcrResult,
    OcrTextBlock,
    OcrValidationError,
)
from crxzipple.shared.infrastructure.http import request_url


def _json_payload(response, *, invalid_message: str) -> object:  # noqa: ANN001
    try:
        return response.json()
    except Exception as exc:  # noqa: BLE001
        raise OcrExecutionError(invalid_message) from exc


def _optional_json_payload(response) -> object:  # noqa: ANN001
    try:
        return response.json()
    except Exception:  # noqa: BLE001
        return {}


def _parse_blocks_payload(value: object) -> tuple[OcrTextBlock, ...]:
    raw_blocks = value
    blocks: list[OcrTextBlock] = []
    if not isinstance(raw_blocks, list):
        return ()
    for item in raw_blocks:
        if not isinstance(item, dict):
            continue
        polygon_payload = item.get("polygon")
        polygon: list[OcrPoint] = []
        if isinstance(polygon_payload, list):
            for point in polygon_payload:
                if not isinstance(point, dict):
                    continue
                try:
                    polygon.append(
                        OcrPoint(
                            x=float(point.get("x", 0.0)),
                            y=float(point.get("y", 0.0)),
                        )
                    )
                except (TypeError, ValueError):
                    continue
        confidence = item.get("confidence")
        try:
            normalized_confidence = (
                float(confidence) if confidence is not None else None
            )
        except (TypeError, ValueError):
            normalized_confidence = None
        blocks.append(
            OcrTextBlock(
                text=str(item.get("text", "")),
                label=(str(item["label"]) if isinstance(item.get("label"), str) else None),
                confidence=normalized_confidence,
                polygon=tuple(polygon),
            )
        )
    return tuple(blocks)


def _parse_result_payload(payload: dict[str, object]) -> OcrResult:
    blocks = _parse_blocks_payload(payload.get("blocks"))
    layout_blocks = _parse_blocks_payload(payload.get("layout_blocks"))
    overall_ocr_blocks = _parse_blocks_payload(payload.get("overall_ocr_blocks"))
    return OcrResult(
        backend=str(payload.get("backend", "ocr-host")),
        language=str(payload.get("language", "")),
        artifact_id=(
            str(payload["artifact_id"]) if isinstance(payload.get("artifact_id"), str) else None
        ),
        variant=(
            str(payload["variant"]) if isinstance(payload.get("variant"), str) else None
        ),
        image_width=(
            int(payload["image_width"])
            if isinstance(payload.get("image_width"), int)
            else None
        ),
        image_height=(
            int(payload["image_height"])
            if isinstance(payload.get("image_height"), int)
            else None
        ),
        blocks=blocks,
        layout_blocks=layout_blocks,
        overall_ocr_blocks=overall_ocr_blocks,
        metadata=dict(payload.get("metadata", {}))
        if isinstance(payload.get("metadata"), dict)
        else {},
    )


class OcrHostClient:
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
            raise OcrExecutionError(f"OCR host healthcheck failed: {exc}") from exc
        try:
            response.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            raise OcrExecutionError(f"OCR host healthcheck failed: {exc}") from exc
        payload = _json_payload(
            response,
            invalid_message="OCR host returned an invalid health payload.",
        )
        if not isinstance(payload, dict):
            raise OcrExecutionError("OCR host returned an invalid health payload.")
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
        request_payload = {
            "image_path": str(image_path),
            "language": language,
            "detect_orientation": bool(detect_orientation),
            "artifact_id": artifact_id,
            "variant": variant,
        }
        try:
            response = request_url(
                "POST",
                f"{self.base_url}/analyze",
                json=request_payload,
                timeout=self.timeout_seconds,
            )
        except Exception as exc:  # noqa: BLE001
            raise OcrExecutionError(f"OCR host request failed: {exc}") from exc
        payload = (
            _optional_json_payload(response)
            if response.status_code >= 400
            else _json_payload(
                response,
                invalid_message="OCR host returned an invalid OCR payload.",
            )
        )
        if response.status_code >= 400:
            detail = (
                payload.get("detail")
                if isinstance(payload, dict)
                else None
            )
            message = str(detail or "OCR host request failed.")
            if response.status_code < 500:
                raise OcrValidationError(message)
            if response.status_code == 503:
                raise OcrCapacityExceededError(message)
            raise OcrExecutionError(message)
        if not isinstance(payload, dict):
            raise OcrExecutionError("OCR host returned an invalid OCR payload.")
        return _parse_result_payload(payload)
