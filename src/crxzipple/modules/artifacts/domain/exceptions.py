from __future__ import annotations


class ArtifactError(Exception):
    """Base artifact module error."""


class ArtifactValidationError(ArtifactError):
    """Raised when artifact input is invalid."""


class ArtifactNotFoundError(ArtifactError):
    """Raised when an artifact cannot be found."""
