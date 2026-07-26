"""Error message formatting for user-friendly exception handling."""

from litellm.exceptions import (
    APIConnectionError,
    AuthenticationError,
    BadRequestError,
    RateLimitError,
    ServiceUnavailableError,
)


def _format_litellm_error(error) -> str:
    provider = getattr(error, "llm_provider", "unknown provider")
    model = getattr(error, "model", "unknown model")
    message = getattr(error, "message", str(error))
    return f"LLM error ({provider}/{model}): {message}"


ERROR_TYPES = {
    AuthenticationError: lambda e: (
        f"Authentication failed for {getattr(e, 'llm_provider', 'LLM provider')}.\n"
        f"Check your API key or credentials.\nDetails: {getattr(e, 'message', str(e))}"
    ),
    RateLimitError: lambda e: (
        f"Rate limit exceeded for {getattr(e, 'llm_provider', 'LLM provider')}.\n"
        f"Try reducing RATE_LIMIT_REQUESTS or wait before retrying."
    ),
    ServiceUnavailableError: lambda e: (
        f"LLM provider unavailable ({getattr(e, 'llm_provider', 'unknown')}).\n"
        f"This is usually transient — retry in a moment.\n"
        f"Status: {getattr(e, 'status_code', 'unknown')}"
    ),
    APIConnectionError: _format_litellm_error,
    BadRequestError: _format_litellm_error,
    RuntimeError: lambda e: str(e),
    FileNotFoundError: lambda e: str(e),
    ValueError: lambda e: str(e),
    KeyError: lambda e: (
        f"Missing required field '{str(e).strip('"')}' in configuration."
    ),
    PermissionError: lambda e: f"Permission denied: {e!s}\nCheck file permissions.",
    OSError: lambda e: f"System error: {e!s}",
}


def get_error_human_message(error: Exception) -> str:
    """
    Get user-friendly error message based on exception type.

    Args:
        error: The exception to format

    Returns:
        Formatted error message suitable for end users
    """
    for error_type, handler in ERROR_TYPES.items():
        if isinstance(error, error_type):
            return handler(error)
    return str(error)
