class OrchestrationError(Exception):
    """Base class for orchestration domain errors."""


class OrchestrationValidationError(OrchestrationError, ValueError):
    """Raised when an orchestration run definition is invalid."""


class OrchestrationRunNotFoundError(OrchestrationError):
    """Raised when the requested orchestration run does not exist."""
