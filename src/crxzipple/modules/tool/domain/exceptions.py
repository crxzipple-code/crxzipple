class ToolError(Exception):
    """Base class for tool domain errors."""


class ToolValidationError(ToolError, ValueError):
    """Raised when a tool definition or execution request is invalid."""


class ToolNotFoundError(ToolError):
    """Raised when the requested tool does not exist."""


class ToolRunNotFoundError(ToolError):
    """Raised when the requested tool run does not exist."""


class ToolExecutionNotAllowedError(ToolError):
    """Raised when a tool cannot be executed in its current state."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "tool_execution_not_allowed",
        detail: dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.detail = dict(detail or {})

    def to_payload(self) -> dict[str, object]:
        return {
            "message": self.message,
            "code": self.code,
            **self.detail,
        }


class ToolExecutionNotSupportedError(ToolError):
    """Raised when the requested execution target is not supported."""
