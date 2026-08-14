class AgentError(Exception):
    """Base class for expected agent failures."""


class AgentConfigurationError(AgentError):
    """The service is missing required runtime configuration."""


class AgentLoopError(AgentError):
    """The model exceeded a loop safety boundary."""


class SessionAccessError(AgentError):
    """A session does not belong to the current caller."""


class SessionNotFoundError(AgentError):
    """A requested conversation session no longer exists."""


class BackendToolError(AgentError):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        status_code: int | None = None,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.retryable = retryable
