"""Error message formatting for user-friendly exception handling."""

from botocore.exceptions import ClientError


def _format_client_error(error) -> str:
    """Format AWS ClientError messages."""
    error_code = error.response.get("Error", {}).get("Code", "Unknown")
    error_msg = error.response.get("Error", {}).get("Message", str(error))
    if error_code == "AccessDeniedException":
        return (
            "AWS Bedrock access denied.\n"
            "Check your AWS credentials and IAM permissions.\n"
            f"Details: {error_msg}"
        )

    return f"AWS error ({error_code}): {error_msg}"


ERROR_TYPES = {
    RuntimeError: lambda e: str(e),
    FileNotFoundError: lambda e: str(e),
    ValueError: lambda e: str(e),
    KeyError: lambda e: f"Missing required field '{str(e).strip('"')}' in configuration.",
    PermissionError: lambda e: f"Permission denied: {e!s}\nCheck file permissions.",
    OSError: lambda e: f"System error: {e!s}",
    ClientError: lambda e: _format_client_error(e),
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
