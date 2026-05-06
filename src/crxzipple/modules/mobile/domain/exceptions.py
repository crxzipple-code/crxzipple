from __future__ import annotations


class MobileValidationError(ValueError):
    """Raised when a mobile command or config is invalid."""


class MobileExecutionError(RuntimeError):
    """Raised when mobile execution fails."""


class MobileSessionNotFoundError(MobileExecutionError):
    """Raised when a device session is required but unavailable."""

