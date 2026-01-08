"""Configuration utilities for x2a-convertor.

This module provides backwards-compatible access to configuration values.
New code should use `from src.config import get_settings` directly.
"""

from typing import Literal

from src.config import get_settings


def get_config_int(
    envVar: Literal["RECURSION_LIMIT", "MAX_WRITE_ATTEMPTS", "MAX_VALIDATION_ATTEMPTS"],
) -> int:
    """Get an integer configuration value.

    Args:
        envVar: The configuration variable name

        RECURSION_LIMIT: Maximum recursion limit for LLM calls
        MAX_WRITE_ATTEMPTS: Maximum number of attempts to write all files from checklist
        MAX_VALIDATION_ATTEMPTS: Maximum number of attempts to fix validation errors

    Returns:
        The integer value of the configuration variable
    """
    settings = get_settings()
    mapping = {
        "RECURSION_LIMIT": settings.processing.recursion_limit,
        "MAX_WRITE_ATTEMPTS": settings.processing.max_write_attempts,
        "MAX_VALIDATION_ATTEMPTS": settings.processing.max_validation_attempts,
    }

    if envVar not in mapping:
        raise ValueError(f"Invalid configuration variable: {envVar}")

    return mapping[envVar]
