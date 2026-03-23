class ToolError(Exception):
    """Base class for tool domain errors."""


class ToolValidationError(ToolError, ValueError):
    """Raised when a tool definition or execution request is invalid."""


class ToolAlreadyExistsError(ToolError):
    """Raised when trying to register a duplicate tool."""


class ToolNotFoundError(ToolError):
    """Raised when the requested tool does not exist."""


class ToolRunNotFoundError(ToolError):
    """Raised when the requested tool run does not exist."""


class ToolExecutionNotAllowedError(ToolError):
    """Raised when a tool cannot be executed in its current state."""


class ToolExecutionNotSupportedError(ToolError):
    """Raised when the requested execution target is not supported."""


class ToolDiscoveryProviderNotFoundError(ToolError):
    """Raised when the requested tool discovery provider does not exist."""
