from __future__ import annotations


class SettingsError(Exception):
    """Base error for settings governance failures."""


class SettingsValidationError(SettingsError):
    """Raised when a settings model is internally invalid."""


class SettingsNotFoundError(SettingsError):
    """Raised when a settings resource, version, or override cannot be found."""


class SettingsAlreadyExistsError(SettingsError):
    """Raised when creating a settings record with an existing identifier."""


class SettingsPublishError(SettingsError):
    """Raised when publishing or rollback cannot complete."""
