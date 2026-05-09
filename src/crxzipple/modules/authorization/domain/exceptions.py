from __future__ import annotations


class AuthorizationError(Exception):
    """Base authorization error."""


class AuthorizationDeniedError(AuthorizationError):
    """Raised when an ABAC decision denies access."""


class AuthorizationPolicyNotFoundError(AuthorizationError):
    """Raised when a policy governance operation targets a missing policy."""
