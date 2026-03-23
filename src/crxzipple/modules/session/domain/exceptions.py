class SessionError(Exception):
    """Base class for session domain errors."""


class SessionValidationError(SessionError, ValueError):
    """Raised when a session definition or message is invalid."""


class SessionNotFoundError(SessionError):
    """Raised when the requested session does not exist."""


class SessionInstanceNotFoundError(SessionError):
    """Raised when the requested session instance does not exist."""
