from __future__ import annotations


class AuthorizationError(Exception):
    """Base authorization error."""


class AuthorizationDeniedError(AuthorizationError):
    """Raised when an ABAC decision denies access."""

