from __future__ import annotations


class DaemonValidationError(ValueError):
    """Raised when daemon configuration or state is invalid."""


class DaemonNotFoundError(LookupError):
    """Raised when a daemon service, instance, or lease is not present."""
