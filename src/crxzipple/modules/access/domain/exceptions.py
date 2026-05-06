from __future__ import annotations


class AccessError(Exception):
    """Base error for external access readiness and credential resolution."""


class CredentialResolutionError(AccessError):
    """Raised when a credential binding cannot be resolved."""
