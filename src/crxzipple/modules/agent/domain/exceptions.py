class AgentError(Exception):
    """Base class for agent domain errors."""


class AgentValidationError(AgentError, ValueError):
    """Raised when an agent profile definition is invalid."""


class AgentAlreadyExistsError(AgentError):
    """Raised when trying to register a duplicate agent profile."""


class AgentNotFoundError(AgentError):
    """Raised when the requested agent profile does not exist."""
