from __future__ import annotations


class ContextWorkspaceError(Exception):
    """Base exception for Context Workspace failures."""


class ContextWorkspaceValidationError(ContextWorkspaceError, ValueError):
    """Raised when a context workspace entity is invalid."""


class ContextWorkspaceNotFoundError(ContextWorkspaceError, LookupError):
    """Raised when a context workspace cannot be found."""


class ContextNodeNotFoundError(ContextWorkspaceError, LookupError):
    """Raised when a context tree node cannot be found."""


class ContextActionNotAllowedError(ContextWorkspaceError, PermissionError):
    """Raised when a context tree action is not supported by the node."""


class ContextSnapshotNotFoundError(ContextWorkspaceError, LookupError):
    """Raised when a snapshot cannot be found."""


__all__ = [
    "ContextActionNotAllowedError",
    "ContextNodeNotFoundError",
    "ContextSnapshotNotFoundError",
    "ContextWorkspaceError",
    "ContextWorkspaceNotFoundError",
    "ContextWorkspaceValidationError",
]
