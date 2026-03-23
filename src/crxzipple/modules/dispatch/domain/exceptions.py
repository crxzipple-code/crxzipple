class DispatchError(Exception):
    """Base class for dispatch domain errors."""


class DispatchValidationError(DispatchError, ValueError):
    """Raised when a dispatch task or policy is invalid."""


class DispatchTaskNotFoundError(DispatchError):
    """Raised when the requested dispatch task does not exist."""
