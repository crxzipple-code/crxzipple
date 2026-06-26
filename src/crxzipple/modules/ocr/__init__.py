"""OCR bounded context."""

from .application import OcrApplicationService, OcrCapacityLimiter, OcrEngine
from .domain import (
    OcrCapacityExceededError,
    OcrCapacitySnapshot,
    OcrError,
    OcrExecutionError,
    OcrPoint,
    OcrResult,
    OcrTextBlock,
    OcrValidationError,
)
from .infrastructure import (
    OcrHostClient,
    PaddleOcrEngine,
    PPStructureV3Client,
    create_ocr_host_app,
)
from .interfaces import OcrAnalyzeArtifactRequest, OcrResultSerializer

__all__ = [
    "create_ocr_host_app",
    "OcrAnalyzeArtifactRequest",
    "OcrApplicationService",
    "OcrCapacityExceededError",
    "OcrCapacityLimiter",
    "OcrCapacitySnapshot",
    "OcrEngine",
    "OcrError",
    "OcrExecutionError",
    "OcrHostClient",
    "OcrPoint",
    "OcrResult",
    "OcrResultSerializer",
    "OcrTextBlock",
    "OcrValidationError",
    "PaddleOcrEngine",
    "PPStructureV3Client",
]
