import os
from typing import Literal

defaults = {
    "RECURSION_LIMIT": 100,
    "MAX_WRITE_ATTEMPTS": 10,
    "MAX_VALIDATION_ATTEMPTS": 5,
}


# Delay os.getnv() in favor of dotenv
def get_config_int(
    envVar: Literal["RECURSION_LIMIT", "MAX_WRITE_ATTEMPTS", "MAX_VALIDATION_ATTEMPTS"],
) -> int:
    """Get an integer configuration value from the environment
    Args:
        envVar: The environment variable to get the value from

        RECURSION_LIMIT: Maximum recursion limit for LLM calls
        MAX_WRITE_ATTEMPTS: Maximum number of attempts to write all files from checklist
        MAX_VALIDATION_ATTEMPTS: Maximum number of attempts to fix validation errors
    Returns:
        The integer value of the environment variable
    """
    if envVar not in defaults:
        raise ValueError(f"Invalid environment variable: {envVar}")

    return int(os.getenv(envVar, default=defaults[envVar]))
