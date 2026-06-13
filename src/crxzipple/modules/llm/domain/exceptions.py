class LlmError(Exception):
    """Base class for llm domain errors."""


class LlmValidationError(LlmError, ValueError):
    """Raised when an llm definition or invocation is invalid."""


class LlmAlreadyExistsError(LlmError):
    """Raised when trying to register a duplicate llm profile."""


class LlmNotFoundError(LlmError):
    """Raised when the requested llm profile does not exist."""


class LlmInvocationNotFoundError(LlmError):
    """Raised when the requested llm invocation does not exist."""


class LlmResponseItemNotFoundError(LlmError):
    """Raised when the requested llm response item does not exist."""


class LlmInvocationNotAllowedError(LlmError):
    """Raised when an llm profile cannot be invoked in its current state."""


class LlmAdapterNotConfiguredError(LlmError):
    """Raised when no adapter is configured for an llm api family."""
