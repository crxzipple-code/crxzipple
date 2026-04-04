from __future__ import annotations


class ProcessError(ValueError):
    """Base error for process domain failures."""


class ProcessNotFoundError(ProcessError):
    """Raised when a process session cannot be found."""


class ProcessValidationError(ProcessError):
    """Raised when a process session is invalid."""
