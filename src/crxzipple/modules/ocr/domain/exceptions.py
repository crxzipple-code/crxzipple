from __future__ import annotations


class OcrError(Exception):
    """Base exception for the OCR module."""


class OcrValidationError(OcrError):
    """Raised when OCR inputs are invalid."""


class OcrExecutionError(OcrError):
    """Raised when OCR execution fails."""


class OcrCapacityExceededError(OcrExecutionError):
    """Raised when OCR execution cannot start because local capacity is full."""
